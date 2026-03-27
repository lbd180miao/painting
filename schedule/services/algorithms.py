"""
涂装双层滚动排产算法核心模块
"""
import math
from collections import defaultdict
from typing import Dict, List

from django.contrib.auth.models import User
from django.utils import timezone

from data.models import (
    AssemblyPullData,
    InjectionInventory,
    Inventory,
    Product,
    SafetyStock,
    SystemParameter,
)
from schedule.models import (
    DemandRecord,
    FormationSlot,
    InventorySnapshot,
    RiskRecord,
    SchedulePlan,
    ScheduleRecord,
)


class SchedulingAlgorithm:
    """
    涂装双层滚动排产算法
    """

    POSITION_FRONT = "front"
    POSITION_REAR = "rear"
    POSITION_TYPES = [POSITION_FRONT, POSITION_REAR]

    def __init__(self, short_term_duration=None, long_term_duration=None, record_time=None):
        self.params = self._load_parameters()
        self.short_term_duration = short_term_duration
        self.long_term_duration = long_term_duration
        self.record_time = record_time or timezone.now()
        self.products = list(
            Product.objects.filter(is_active=True).select_related(
                "vehicle_model",
                "color",
                "position_type",
            )
        )
        # Pre-build product cache: key -> Product, avoids N+1 DB hits in _get_product_by_key
        self._product_cache: Dict[str, Product] = {
            self._make_product_key(p.vehicle_model.name, p.color.name, p.position_type.name): p
            for p in self.products
        }
        self.inventory_data = self._load_paint_inventory()
        self.injection_inventory_data = self._load_injection_inventory()
        self.safety_stock_data = self._load_safety_stock()
        self.assembly_data = list(
            AssemblyPullData.objects.select_related("vehicle_model", "color").order_by("sequence")
        )
        self.previous_formation_slots = self._load_previous_formation_slots()

    def _load_parameters(self) -> Dict:
        params = SystemParameter.objects.all()
        return {
            p.param_key: (
                p.get_float_value()
                if "CAPACITY" in p.param_key or "LIMIT" in p.param_key
                else p.get_int_value()
            )
            for p in params
        }

    def _load_paint_inventory(self) -> Dict:
        inventory = {}
        for inv in Inventory.objects.select_related("product__vehicle_model", "product__color", "product__position_type"):
            product_key = self._get_product_key(inv.product)
            inventory[product_key] = {
                "current": inv.current_quantity,
                "inventory": inv,
                "product": inv.product,
            }
        return inventory

    def _load_injection_inventory(self) -> Dict:
        inventory = {}
        for inv in InjectionInventory.objects.select_related("product__vehicle_model", "product__color", "product__position_type"):
            product_key = self._get_product_key(inv.product)
            inventory[product_key] = {
                "current": inv.current_quantity,
                "inventory": inv,
                "product": inv.product,
            }
        return inventory

    def _load_safety_stock(self) -> Dict:
        safety_stock = {}
        for ss in SafetyStock.objects.select_related("product"):
            product_key = self._get_product_key(ss.product)
            safety_stock[product_key] = ss.quantity
        return safety_stock

    def _load_previous_formation_slots(self):
        previous_record = ScheduleRecord.objects.filter(status="completed").order_by("-record_time", "-id").first()
        if not previous_record:
            return []
        return list(
            previous_record.formation_slots.select_related(
                "product__vehicle_model",
                "product__color",
                "product__position_type",
            ).order_by("slot_number")
        )

    @staticmethod
    def _make_product_key(model_name: str, color_name: str, position_name: str) -> str:
        return f"{model_name}_{color_name}_{position_name}"

    def _get_product_key(self, product: Product) -> str:
        return self._make_product_key(
            product.vehicle_model.name,
            product.color.name,
            product.position_type.name,
        )

    def calculate_short_term_demand_quantity(self) -> int:
        if self.short_term_duration is not None:
            return max(int(self.short_term_duration), 0)
        total = (
            self.params["TOTAL_VEHICLES"]
            * self.params["AVG_HANGING_COUNT"]
            * self.params["SHORT_TERM_CAPACITY"]
            / 100
            / 2
        )
        return math.ceil(total)

    def calculate_long_term_demand_quantity(self) -> int:
        if self.long_term_duration is not None:
            return max(int(self.long_term_duration), 0)
        forecast_hours = int(self.params.get("LONG_TERM_FORECAST_HOURS", 0))
        if forecast_hours > 0:
            return forecast_hours * 60
        total = (
            self.params["TOTAL_VEHICLES"]
            * self.params["AVG_HANGING_COUNT"]
            * self.params["LONG_TERM_CAPACITY"]
            / 100
            / 2
        )
        return math.ceil(total)

    def calculate_production_quantity(self, demand_quantity: int, yield_rate: float) -> int:
        return math.ceil(demand_quantity / yield_rate * 100)

    def calculate(self) -> Dict:
        results = {}
        short_qty = self.calculate_short_term_demand_quantity()
        long_qty = self.calculate_long_term_demand_quantity()
        remaining_injection_inventory = self._build_remaining_injection_inventory()

        results["short_window"] = {"start": 1, "end": short_qty}
        results["long_window"] = {"start": short_qty + 1, "end": short_qty + long_qty}
        results["short_term"] = self.calculate_short_term_demand()
        results["long_term"] = self.calculate_long_term_demand()
        results["short_risk"] = self.calculate_short_term_risk(results["short_term"])
        results["long_risk"] = self.calculate_long_term_risk(results["long_term"])
        results["short_plan"] = self.calculate_short_term_plan(
            results["short_risk"],
            remaining_injection_inventory=remaining_injection_inventory,
        )
        results["long_plan"] = self.calculate_long_term_plan(
            results["long_risk"],
            remaining_injection_inventory=remaining_injection_inventory,
        )
        results["formation"] = self.optimize_formation(
            results["short_plan"],
            results["long_plan"],
            remaining_injection_inventory=remaining_injection_inventory,
        )
        results["inventory_updates"] = self.update_inventory(results)
        return results

    def _build_remaining_injection_inventory(self) -> Dict[str, int]:
        return {
            key: max(snapshot.get("current", 0), 0)
            for key, snapshot in self.injection_inventory_data.items()
        }

    def _calculate_demand_window(self, start_idx: int, quantity: int) -> List[Dict]:
        if quantity <= 0:
            return []

        assembly_list = self.assembly_data[start_idx:start_idx + quantity]
        demand_summary = {}

        for assembly in assembly_list:
            for position in self.POSITION_TYPES:
                key = f"{assembly.vehicle_model.name}_{assembly.color.name}_{position}"
                if key not in demand_summary:
                    demand_summary[key] = {
                        "vehicle_model": assembly.vehicle_model,
                        "color": assembly.color,
                        "position": position,
                        "demand_quantity": 0,
                    }
                demand_summary[key]["demand_quantity"] += 1

        result = []
        for key, data in demand_summary.items():
            product = self._get_product_by_key(key)
            if not product:
                continue
            result.append(
                {
                    "product": product,
                    "demand_quantity": data["demand_quantity"],
                    "production_quantity": self.calculate_production_quantity(
                        data["demand_quantity"],
                        float(product.yield_rate),
                    ),
                }
            )
        return result

    def calculate_short_term_demand(self) -> List[Dict]:
        return self._calculate_demand_window(0, self.calculate_short_term_demand_quantity())

    def calculate_long_term_demand(self) -> List[Dict]:
        short_qty = self.calculate_short_term_demand_quantity()
        long_qty = self.calculate_long_term_demand_quantity()
        return self._calculate_demand_window(short_qty, long_qty)

    def _get_product_by_key(self, key: str) -> Product | None:
        """O(1) lookup from pre-built cache — no DB hit."""
        return self._product_cache.get(key)

    def calculate_short_term_risk(self, short_term_demand: List[Dict]) -> List[Dict]:
        risks = []
        for item in short_term_demand:
            product = item["product"]
            key = self._get_product_key(product)
            current_stock = self.inventory_data.get(key, {}).get("current", 0)
            safety_stock = self.safety_stock_data.get(key, 0)
            final_value = current_stock - item["production_quantity"]
            risks.append(
                {
                    "product": product,
                    "final_value": final_value,
                    "safety_stock": safety_stock,
                    "is_shortage": final_value < 0,
                }
            )

        risks.sort(key=lambda x: x["final_value"])
        for index, risk in enumerate(risks, start=1):
            risk["rank"] = index
        return risks

    def calculate_long_term_risk(self, long_term_demand: List[Dict]) -> List[Dict]:
        risks = []
        group_map = {}

        for item in long_term_demand:
            product = item["product"]
            key = self._get_product_key(product)
            current_stock = self.inventory_data.get(key, {}).get("current", 0)
            safety_stock = self.safety_stock_data.get(key, 0)
            final_value = current_stock - item["production_quantity"]
            risk_value = safety_stock - final_value
            risk = {
                "product": product,
                "final_value": final_value,
                "safety_stock": safety_stock,
                "risk_value": risk_value,
            }
            risks.append(risk)
            group_key = f"{product.vehicle_model.name}_{product.color.name}"
            group_map.setdefault(group_key, {})[product.position_type.name] = risk

        for group_data in group_map.values():
            front_risk = group_data.get(self.POSITION_FRONT, {}).get("risk_value", 0)
            rear_risk = group_data.get(self.POSITION_REAR, {}).get("risk_value", 0)
            group_risk = max(front_risk, rear_risk)
            for position in self.POSITION_TYPES:
                if position in group_data:
                    group_data[position]["group_risk_value"] = group_risk

        risks.sort(
            key=lambda x: (x.get("group_risk_value", 0), x.get("risk_value", 0)),
            reverse=True,
        )
        for index, risk in enumerate(risks, start=1):
            risk["rank"] = index
        return risks

    def calculate_short_term_plan(
        self,
        short_risks: List[Dict],
        remaining_injection_inventory: Dict[str, int] | None = None,
    ) -> List[Dict]:
        total_vehicles = math.ceil(
            self.params["TOTAL_VEHICLES"] * self.params["SHORT_TERM_CAPACITY"] / 100
        )
        remaining_vehicles = total_vehicles
        remaining_injection_inventory = remaining_injection_inventory or self._build_remaining_injection_inventory()
        plans = []

        for risk in short_risks:
            if risk["final_value"] >= 0:
                continue
            product = risk["product"]
            needed_vehicles = math.ceil(abs(risk["final_value"]) / product.hanging_count_per_vehicle)
            product_key = self._get_product_key(product)
            available_pieces = max(remaining_injection_inventory.get(product_key, 0), 0)
            available_vehicles = available_pieces // product.hanging_count_per_vehicle
            allocated = min(needed_vehicles, remaining_vehicles, available_vehicles)
            note_parts = [f"短期止血，终值 {risk['final_value']}"]
            if available_vehicles < needed_vehicles:
                note_parts.append("受注塑库存限制")
            if remaining_vehicles < needed_vehicles:
                note_parts.append("受短期产能限制")
            note_parts = list(dict.fromkeys(note_parts))
            if allocated <= 0:
                plans.append(
                    {
                        "product": product,
                        "vehicle_count": 0,
                        "note": "，".join(note_parts),
                    }
                )
                continue
            plans.append(
                {
                    "product": product,
                    "vehicle_count": allocated,
                    "note": "，".join(note_parts),
                }
            )
            remaining_vehicles -= allocated
            remaining_injection_inventory[product_key] = max(
                available_pieces - allocated * product.hanging_count_per_vehicle,
                0,
            )

        return plans

    def calculate_long_term_plan(
        self,
        long_risks: List[Dict],
        remaining_injection_inventory: Dict[str, int] | None = None,
    ) -> List[Dict]:
        total_vehicles = math.ceil(
            self.params["TOTAL_VEHICLES"] * self.params["LONG_TERM_CAPACITY"] / 100
        )
        group_capacity_limit = math.ceil(
            total_vehicles * self.params.get("GROUP_CAPACITY_LIMIT", 0) / 100
        )
        balance_limit = int(self.params.get("FRONT_REAR_BALANCE_D", 0))
        remaining_injection_inventory = remaining_injection_inventory or self._build_remaining_injection_inventory()
        grouped_risks = self._group_long_risks(long_risks)

        plan_map = {}
        front_count = 0
        rear_count = 0
        used_vehicles = 0
        model_usage: Dict[str, int] = defaultdict(int)

        for group in grouped_risks:
            primary_position = self._get_primary_position(group["positions"])

            # 产能已满：标注所有有风险的 position 并跳过
            if used_vehicles >= total_vehicles:
                self._annotate_group_capacity_shortage(
                    plan_map=plan_map,
                    group=group,
                    primary_position=primary_position,
                )
                continue

            # 计算每个 position 的需求车数（批量，不逐车循环）
            needs: Dict[str, int] = {}
            for position, risk in group["positions"].items():
                if not risk or risk.get("risk_value", 0) <= 0:
                    needs[position] = 0
                else:
                    needed_pieces = max(risk["risk_value"], 0)
                    needs[position] = math.ceil(
                        needed_pieces / risk["product"].hanging_count_per_vehicle
                    )

            group_limit_hit = False
            balance_blocked = False
            injection_blocked = False

            # 按风险从大到小排序 position，先补高风险侧
            ordered_positions = sorted(
                self.POSITION_TYPES,
                key=lambda pos: (
                    group["positions"].get(pos, {}).get("risk_value", 0),
                    1 if pos == self.POSITION_REAR else 0,
                ),
                reverse=True,
            )

            for position in ordered_positions:
                if needs.get(position, 0) <= 0:
                    continue
                risk = group["positions"].get(position)
                if not risk:
                    continue

                product = risk["product"]
                model_name = product.vehicle_model.name
                product_key = self._get_product_key(product)
                requested = needs[position]

                # ── 约束1：注塑库存上限 ──
                available_pieces = max(remaining_injection_inventory.get(product_key, 0), 0)
                available_by_injection = available_pieces // product.hanging_count_per_vehicle
                if available_by_injection <= 0:
                    # 确保 plan_map 中有这个 entry（0车）便于后续注释
                    self._ensure_long_plan_entry(plan_map, product, group["group_risk_value"], primary_position)
                    injection_blocked = True
                    continue

                # ── 约束2：车型组产能上限 ──
                model_remain = (
                    max(group_capacity_limit - model_usage[model_name], 0)
                    if group_capacity_limit > 0
                    else requested
                )
                if model_remain <= 0:
                    group_limit_hit = True
                    # 同样确保 entry 存在
                    self._ensure_long_plan_entry(plan_map, product, group["group_risk_value"], primary_position)
                    continue

                # ── 约束3：前后平衡约束 ──
                # 计算在平衡约束下，本 position 最多能分配多少辆
                if position == self.POSITION_FRONT:
                    # 分配 k 辆后：|front_count+k - rear_count| <= balance_limit
                    # => front_count+k <= rear_count + balance_limit
                    max_by_balance = max(rear_count + balance_limit - front_count, 0)
                else:
                    max_by_balance = max(front_count + balance_limit - rear_count, 0)

                if max_by_balance <= 0:
                    balance_blocked = True
                    self._ensure_long_plan_entry(plan_map, product, group["group_risk_value"], primary_position)
                    continue

                # ── 约束4：总产能剩余 ──
                capacity_remain = total_vehicles - used_vehicles

                # 批量确定本次实际分配车数（取所有约束的最小值）
                allocated = min(
                    requested,
                    available_by_injection,
                    model_remain,
                    max_by_balance,
                    capacity_remain,
                )

                if allocated <= 0:
                    continue

                # 执行分配
                plan_item = self._ensure_long_plan_entry(
                    plan_map, product, group["group_risk_value"], primary_position
                )
                plan_item["vehicle_count"] += allocated
                used_vehicles += allocated
                model_usage[model_name] += allocated
                remaining_injection_inventory[product_key] = max(
                    available_pieces - allocated * product.hanging_count_per_vehicle, 0
                )
                if position == self.POSITION_FRONT:
                    front_count += allocated
                else:
                    rear_count += allocated

                # 若分配量小于需求，标注是哪个约束截断了
                if allocated < requested:
                    if available_by_injection < requested:
                        injection_blocked = True
                    if group_capacity_limit > 0 and model_usage[model_name] >= group_capacity_limit:
                        group_limit_hit = True
                    if allocated == max_by_balance:
                        balance_blocked = True
                    if used_vehicles >= total_vehicles:
                        pass  # capacity shortage handled below

            # 产能满了但还有剩余需求 → 标注产能不足
            if used_vehicles >= total_vehicles and any(needs.values()):
                self._annotate_group_capacity_shortage(
                    plan_map=plan_map,
                    group=group,
                    primary_position=primary_position,
                )

            if group_limit_hit or balance_blocked or injection_blocked:
                self._annotate_group_plan_notes(
                    plan_map=plan_map,
                    group=group,
                    group_limit_hit=group_limit_hit,
                    balance_blocked=balance_blocked,
                    injection_blocked=injection_blocked,
                )

        plans = [
            {
                "product": item["product"],
                "vehicle_count": item["vehicle_count"],
                "note": "，".join(item["note_parts"]),
            }
            for item in plan_map.values()
        ]
        return plans

    def _get_primary_position(self, positions: Dict) -> str:
        front_risk = positions.get(self.POSITION_FRONT, {}).get("risk_value", 0)
        rear_risk = positions.get(self.POSITION_REAR, {}).get("risk_value", 0)
        return self.POSITION_REAR if rear_risk > front_risk else self.POSITION_FRONT

    def _ensure_long_plan_entry(self, plan_map: Dict, product: Product, group_risk_value: int, primary_position: str) -> Dict:
        product_id = product.id
        if product_id not in plan_map:
            plan_map[product_id] = {
                "product": product,
                "vehicle_count": 0,
                "note_parts": [
                    f"长期组风险 {group_risk_value}",
                    f"优先补{'后件' if primary_position == self.POSITION_REAR else '前件'}",
                ],
            }
        return plan_map[product_id]

    def _annotate_group_plan_notes(
        self,
        plan_map: Dict,
        group: Dict,
        group_limit_hit: bool,
        balance_blocked: bool,
        injection_blocked: bool,
    ):
        for risk in group["positions"].values():
            if not risk:
                continue
            item = plan_map.get(risk["product"].id)
            if not item:
                continue
            if group_limit_hit and "受车型上限截断" not in item["note_parts"]:
                item["note_parts"].append("受车型上限截断")
            if balance_blocked and "受前后平衡约束截断" not in item["note_parts"]:
                item["note_parts"].append("受前后平衡约束截断")
            if injection_blocked and "受注塑库存限制" not in item["note_parts"]:
                item["note_parts"].append("受注塑库存限制")

    def _annotate_group_capacity_shortage(self, plan_map: Dict, group: Dict, primary_position: str):
        for risk in group["positions"].values():
            if not risk or risk.get("risk_value", 0) <= 0:
                continue
            item = self._ensure_long_plan_entry(
                plan_map,
                risk["product"],
                group.get("group_risk_value", 0),
                primary_position,
            )
            if "受长期产能限制" not in item["note_parts"]:
                item["note_parts"].append("受长期产能限制")

    def _group_long_risks(self, long_risks: List[Dict]) -> List[Dict]:
        groups = {}
        for risk in long_risks:
            product = risk["product"]
            group_key = f"{product.vehicle_model.name}_{product.color.name}"
            groups.setdefault(
                group_key,
                {
                    "group_key": group_key,
                    "group_risk_value": risk.get("group_risk_value", 0),
                    "positions": {},
                },
            )
            groups[group_key]["positions"][product.position_type.name] = risk
            groups[group_key]["group_risk_value"] = max(
                groups[group_key]["group_risk_value"],
                risk.get("group_risk_value", 0),
            )

        return sorted(groups.values(), key=lambda item: item["group_risk_value"], reverse=True)

    def optimize_formation(
        self,
        short_plan: List[Dict],
        long_plan: List[Dict],
        remaining_injection_inventory: Dict[str, int] | None = None,
    ) -> List[Dict]:
        total_slots = int(self.params["TOTAL_VEHICLES"])
        pending_slots = []
        for plan_type, plans in [("short", short_plan), ("long", long_plan)]:
            for plan in plans:
                for _ in range(plan["vehicle_count"]):
                    pending_slots.append(
                        {
                            "product": plan["product"],
                            "plan_type": plan_type,
                            "note": plan.get("note", ""),
                        }
                    )

        formation = []
        used_slot_numbers = set()
        remaining_injection_inventory = remaining_injection_inventory or self._build_remaining_injection_inventory()
        previous_slot_map = {
            slot.slot_number: slot
            for slot in self.previous_formation_slots
            if slot.slot_number <= total_slots and slot.product_id is not None
        }

        for previous_slot in self.previous_formation_slots:
            if previous_slot.slot_number > total_slots or previous_slot.product_id is None:
                continue
            match_index = next(
                (
                    index
                    for index, candidate in enumerate(pending_slots)
                    if candidate["product"].id == previous_slot.product_id
                ),
                None,
            )
            if match_index is None:
                continue
            candidate = pending_slots.pop(match_index)
            formation.append(
                {
                    "slot_number": previous_slot.slot_number,
                    "product": candidate["product"],
                    "plan_type": candidate["plan_type"],
                    "is_reused": True,
                }
            )
            used_slot_numbers.add(previous_slot.slot_number)

        next_slot = 1
        for candidate in pending_slots:
            while next_slot in used_slot_numbers:
                next_slot += 1
            if next_slot > total_slots:
                break
            formation.append(
                {
                    "slot_number": next_slot,
                    "product": candidate["product"],
                    "plan_type": candidate["plan_type"],
                    "is_reused": False,
                }
            )
            used_slot_numbers.add(next_slot)

        fallback_products = self._build_backfill_products(formation, previous_slot_map)
        fallback_index = 0
        for slot_number in range(1, total_slots + 1):
            if slot_number in used_slot_numbers:
                continue
            preferred_product = previous_slot_map.get(slot_number).product if slot_number in previous_slot_map else None
            product, is_reused, fallback_index = self._select_backfill_product(
                preferred_product=preferred_product,
                fallback_products=fallback_products,
                fallback_index=fallback_index,
                remaining_injection_inventory=remaining_injection_inventory,
            )
            if not product:
                continue
            formation.append(
                {
                    "slot_number": slot_number,
                    "product": product,
                    "plan_type": "long",
                    "is_reused": is_reused,
                }
            )

        formation.sort(key=lambda slot: slot["slot_number"])
        return formation

    def _build_backfill_products(self, formation: List[Dict], previous_slot_map: Dict[int, FormationSlot]) -> List[Product]:
        products = []
        seen = set()
        for slot_number in sorted(previous_slot_map):
            product = previous_slot_map[slot_number].product
            if product and product.id not in seen:
                products.append(product)
                seen.add(product.id)
        for slot in formation:
            product = slot["product"]
            if product and product.id not in seen:
                products.append(product)
                seen.add(product.id)
        for product in self.products:
            if product.id not in seen:
                products.append(product)
                seen.add(product.id)
        return products

    def _select_backfill_product(
        self,
        preferred_product: Product | None,
        fallback_products: List[Product],
        fallback_index: int,
        remaining_injection_inventory: Dict[str, int],
    ) -> tuple[Product | None, bool, int]:
        preferred_candidates = [preferred_product] if preferred_product else []
        for product in preferred_candidates:
            if self._consume_backfill_inventory(product, remaining_injection_inventory):
                return product, True, fallback_index

        if not fallback_products:
            return None, False, fallback_index

        for offset in range(len(fallback_products)):
            index = (fallback_index + offset) % len(fallback_products)
            product = fallback_products[index]
            if preferred_product and product.id == preferred_product.id:
                continue
            if self._consume_backfill_inventory(product, remaining_injection_inventory):
                return product, False, (index + 1) % len(fallback_products)

        return None, False, fallback_index

    def _consume_backfill_inventory(
        self,
        product: Product,
        remaining_injection_inventory: Dict[str, int],
    ) -> bool:
        product_key = self._get_product_key(product)
        available_pieces = max(remaining_injection_inventory.get(product_key, 0), 0)
        if available_pieces < product.hanging_count_per_vehicle:
            return False
        remaining_injection_inventory[product_key] = (
            available_pieces - product.hanging_count_per_vehicle
        )
        return True

    def update_inventory(self, results: Dict) -> Dict:
        demand_by_product = defaultdict(int)
        for demand_type in ("short_term", "long_term"):
            for item in results[demand_type]:
                demand_by_product[self._get_product_key(item["product"])] += item["demand_quantity"]

        raw_output_by_product = defaultdict(int)
        good_output_by_product = defaultdict(int)
        for slot in results["formation"]:
            product = slot["product"]
            key = self._get_product_key(product)
            raw_output = product.hanging_count_per_vehicle
            good_output = math.floor(raw_output * float(product.yield_rate) / 100)
            raw_output_by_product[key] += raw_output
            good_output_by_product[key] += good_output

        updates = {"paint": {}, "injection": {}}

        all_paint_keys = set(self.inventory_data.keys()) | set(demand_by_product.keys()) | set(good_output_by_product.keys())
        for key in all_paint_keys:
            current_quantity = self.inventory_data.get(key, {}).get("current", 0)
            updated_quantity = max(
                current_quantity - demand_by_product.get(key, 0) + good_output_by_product.get(key, 0),
                0,
            )
            updates["paint"][key] = {
                "product": self.inventory_data.get(key, {}).get("product") or self._get_product_by_key(key),
                "current": current_quantity,
                "delta": updated_quantity - current_quantity,
                "updated": updated_quantity,
            }

        all_injection_keys = set(self.injection_inventory_data.keys()) | set(raw_output_by_product.keys())
        for key in all_injection_keys:
            current_quantity = self.injection_inventory_data.get(key, {}).get("current", 0)
            updated_quantity = max(current_quantity - raw_output_by_product.get(key, 0), 0)
            updates["injection"][key] = {
                "product": self.injection_inventory_data.get(key, {}).get("product") or self._get_product_by_key(key),
                "current": current_quantity,
                "delta": updated_quantity - current_quantity,
                "updated": updated_quantity,
            }

        return updates

    def save_results(self, results: Dict, record: ScheduleRecord):
        # DemandRecord bulk insert
        demand_objs = []
        for demand_type in ["short_term", "long_term"]:
            dtype = "short" if demand_type == "short_term" else "long"
            for item in results[demand_type]:
                demand_objs.append(DemandRecord(
                    record=record,
                    product=item["product"],
                    demand_type=dtype,
                    demand_quantity=item["demand_quantity"],
                    production_quantity=item["production_quantity"],
                ))
        DemandRecord.objects.bulk_create(demand_objs)

        # RiskRecord bulk insert
        risk_objs = []
        for risk_type in ["short_risk", "long_risk"]:
            rtype = "short" if risk_type == "short_risk" else "long"
            for item in results[risk_type]:
                risk_objs.append(RiskRecord(
                    record=record,
                    product=item["product"],
                    risk_type=rtype,
                    final_value=item["final_value"],
                    safety_stock=item["safety_stock"],
                    risk_value=item.get("risk_value"),
                    group_risk_value=item.get("group_risk_value"),
                    rank=item.get("rank"),
                ))
        RiskRecord.objects.bulk_create(risk_objs)

        # SchedulePlan bulk insert
        plan_objs = []
        for plan_type in ["short_plan", "long_plan"]:
            ptype = "short" if plan_type == "short_plan" else "long"
            for item in results[plan_type]:
                plan_objs.append(SchedulePlan(
                    record=record,
                    product=item["product"],
                    plan_type=ptype,
                    vehicle_count=item["vehicle_count"],
                    note=item.get("note", ""),
                ))
        SchedulePlan.objects.bulk_create(plan_objs)

        # FormationSlot bulk insert
        slot_objs = [
            FormationSlot(
                record=record,
                slot_number=slot["slot_number"],
                product=slot["product"],
                plan_type=slot["plan_type"],
                is_reused=slot.get("is_reused", False),
            )
            for slot in results["formation"]
        ]
        FormationSlot.objects.bulk_create(slot_objs)

        self._persist_inventory_updates(record, results["inventory_updates"])
        self.send_risk_notifications(results, record)

    def _persist_inventory_updates(self, record: ScheduleRecord, inventory_updates: Dict):
        # Collect all snapshot objects for bulk insert
        snapshot_objs = []
        paint_updates: Dict[int, int] = {}    # product_id -> updated_quantity
        injection_updates: Dict[int, int] = {}

        for inventory_type, updates in inventory_updates.items():
            for key, snapshot in updates.items():
                product = snapshot["product"]
                if not product:
                    continue
                snapshot_objs.append(InventorySnapshot(
                    record=record,
                    product=product,
                    inventory_type=inventory_type,
                    current_quantity=snapshot["current"],
                    delta_quantity=snapshot["delta"],
                    updated_quantity=snapshot["updated"],
                ))
                if inventory_type == "paint":
                    paint_updates[product.id] = snapshot["updated"]
                else:
                    injection_updates[product.id] = snapshot["updated"]

        InventorySnapshot.objects.bulk_create(snapshot_objs)

        # Bulk-update paint inventory (load all at once, set, bulk_update)
        if paint_updates:
            paint_rows = list(Inventory.objects.filter(product_id__in=paint_updates.keys()))
            for row in paint_rows:
                row.current_quantity = paint_updates[row.product_id]
            Inventory.objects.bulk_update(paint_rows, ["current_quantity"])

        # Bulk-update injection inventory
        if injection_updates:
            injection_rows = list(InjectionInventory.objects.filter(product_id__in=injection_updates.keys()))
            for row in injection_rows:
                row.current_quantity = injection_updates[row.product_id]
            InjectionInventory.objects.bulk_update(injection_rows, ["current_quantity"])

    def send_risk_notifications(self, results: Dict, record: ScheduleRecord):
        from notifications.models import Notification

        users = list(User.objects.filter(is_active=True))
        short_term_risks = [risk for risk in results.get("short_risk", []) if risk["final_value"] < 0]
        long_term_risks = [risk for risk in results.get("long_risk", []) if risk.get("risk_value", 0) > 0]

        if not short_term_risks and not long_term_risks:
            return

        notification_objs = []
        for user in users:
            if short_term_risks:
                short_items = [
                    f"- {risk['product'].vehicle_model.name} {risk['product'].color.name} "
                    f"{risk['product'].position_type.name}: 终值 {risk['final_value']}"
                    for risk in short_term_risks[:5]
                ]
                notification_objs.append(Notification(
                    user=user,
                    title=f"短期库存风险预警 - 排产记录 #{record.id}",
                    content=(
                        "检测到短期库存风险，以下产品库存不足：\n\n"
                        f"{chr(10).join(short_items)}\n\n请及时关注并安排生产。"
                    ),
                    related_record=record,
                ))

            if long_term_risks:
                long_items = [
                    f"- {risk['product'].vehicle_model.name} {risk['product'].color.name} "
                    f"{risk['product'].position_type.name}: 风险值 {risk.get('risk_value', 0)}"
                    for risk in long_term_risks[:5]
                ]
                notification_objs.append(Notification(
                    user=user,
                    title=f"长期库存风险预警 - 排产记录 #{record.id}",
                    content=(
                        "检测到长期库存风险，以下产品存在库存隐患：\n\n"
                        f"{chr(10).join(long_items)}\n\n请及时关注并安排生产。"
                    ),
                    related_record=record,
                ))

        if notification_objs:
            Notification.objects.bulk_create(notification_objs)
