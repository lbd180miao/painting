"""
涂装双层滚动排产算法核心模块
"""
import math
from typing import Dict, List
from data.models import (
    Product, Inventory, SafetyStock,
    AssemblyPullData, SystemParameter
)
from schedule.models import (
    ScheduleRecord, DemandRecord, RiskRecord,
    SchedulePlan, FormationSlot
)


class SchedulingAlgorithm:
    """
    涂装双层滚动排产算法
    """

    # Position type constants
    POSITION_FRONT = 'front'
    POSITION_REAR = 'rear'
    POSITION_TYPES = [POSITION_FRONT, POSITION_REAR]

    def __init__(self):
        self.params = self._load_parameters()
        self.products = Product.objects.filter(is_active=True)
        self.inventory_data = self._load_inventory()
        self.safety_stock_data = self._load_safety_stock()
        self.assembly_data = AssemblyPullData.objects.all().order_by('sequence')

    def _load_parameters(self) -> Dict:
        """加载系统参数"""
        params = SystemParameter.objects.all()
        return {p.param_key: p.get_float_value() if 'CAPACITY' in p.param_key or 'LIMIT' in p.param_key
                else p.get_int_value() for p in params}

    def _load_inventory(self) -> Dict:
        """加载库存数据"""
        inventory = {}
        for inv in Inventory.objects.select_related('product').all():
            product_key = self._get_product_key(inv.product)
            inventory[product_key] = {
                'current': inv.current_quantity,
                'product': inv.product
            }
        return inventory

    def _load_safety_stock(self) -> Dict:
        """加载安全库存"""
        safety_stock = {}
        for ss in SafetyStock.objects.select_related('product').all():
            product_key = self._get_product_key(ss.product)
            safety_stock[product_key] = ss.quantity
        return safety_stock

    def _get_product_key(self, product: Product) -> str:
        """获取产品唯一标识"""
        return f"{product.vehicle_model.name}_{product.color.name}_{product.position_type.name}"

    def calculate_short_term_demand_quantity(self) -> int:
        """
        计算短期需求数量（台）
        公式：涂装线一圈车数 × 每车平均挂数 × 短期产能百分比 / 2
        """
        total = (self.params['TOTAL_VEHICLES'] *
                self.params['AVG_HANGING_COUNT'] *
                self.params['SHORT_TERM_CAPACITY'] / 100 / 2)
        return math.ceil(total)

    def calculate_long_term_demand_quantity(self) -> int:
        """
        计算长期需求数量（台）
        公式：涂装线一圈车数 × 每车平均挂数 × 长期产能百分比 / 2
        """
        total = (self.params['TOTAL_VEHICLES'] *
                self.params['AVG_HANGING_COUNT'] *
                self.params['LONG_TERM_CAPACITY'] / 100 / 2)
        return math.ceil(total)

    def calculate_production_quantity(self, demand_quantity: int, yield_rate: float) -> int:
        """
        计算生产数量
        公式：需求数量 / 合格率（向上取整）
        """
        return math.ceil(demand_quantity / yield_rate * 100)

    def calculate(self) -> Dict:
        """
        主计算入口
        """
        results = {}

        # Step 1: 读取基础数据（已在初始化时完成）

        # Step 2: 生成提前期需求
        results['short_term'] = self.calculate_short_term_demand()
        results['long_term'] = self.calculate_long_term_demand()

        # Step 3: 计算短期风险表
        results['short_risk'] = self.calculate_short_term_risk(results['short_term'])

        # Step 4: 计算长期风险表
        results['long_risk'] = self.calculate_long_term_risk(results['long_term'])

        # Step 5: 计算短期计划表
        results['short_plan'] = self.calculate_short_term_plan(results['short_risk'])

        # Step 6: 计算长期计划表
        results['long_plan'] = self.calculate_long_term_plan(results['long_risk'])

        # Step 7: 阵型结构约束优化
        results['formation'] = self.optimize_formation(results['short_plan'], results['long_plan'])

        # Step 8: 延迟更新库存
        results['updated_inventory'] = self.update_inventory(results['formation'])

        return results

    def calculate_short_term_demand(self) -> List[Dict]:
        """
        计算短期需求
        """
        quantity = self.calculate_short_term_demand_quantity()
        assembly_list = list(self.assembly_data[:quantity])

        demand_summary = {}
        for assembly in assembly_list:
            # 前后各需一台
            for position in self.POSITION_TYPES:
                key = f"{assembly.vehicle_model.name}_{assembly.color.name}_{position}"
                if key not in demand_summary:
                    demand_summary[key] = {
                        'vehicle_model': assembly.vehicle_model,
                        'color': assembly.color,
                        'position': position,
                        'demand_quantity': 0
                    }
                demand_summary[key]['demand_quantity'] += 1

        # 转换为列表并计算生产数量
        result = []
        for key, data in demand_summary.items():
            product = self._get_product_by_key(key)
            if product:
                production_qty = self.calculate_production_quantity(
                    data['demand_quantity'],
                    float(product.yield_rate)
                )
                result.append({
                    'product': product,
                    'demand_quantity': data['demand_quantity'],
                    'production_quantity': production_qty
                })

        return result

    def calculate_long_term_demand(self) -> List[Dict]:
        """
        计算长期需求
        从短期读取完的位置继续往后读
        """
        short_qty = self.calculate_short_term_demand_quantity()
        long_qty = self.calculate_long_term_demand_quantity()

        start_idx = short_qty
        end_idx = start_idx + long_qty

        assembly_list = list(self.assembly_data[start_idx:end_idx])

        demand_summary = {}
        for assembly in assembly_list:
            for position in self.POSITION_TYPES:
                key = f"{assembly.vehicle_model.name}_{assembly.color.name}_{position}"
                if key not in demand_summary:
                    demand_summary[key] = {
                        'vehicle_model': assembly.vehicle_model,
                        'color': assembly.color,
                        'position': position,
                        'demand_quantity': 0
                    }
                demand_summary[key]['demand_quantity'] += 1

        result = []
        for key, data in demand_summary.items():
            product = self._get_product_by_key(key)
            if product:
                production_qty = self.calculate_production_quantity(
                    data['demand_quantity'],
                    float(product.yield_rate)
                )
                result.append({
                    'product': product,
                    'demand_quantity': data['demand_quantity'],
                    'production_quantity': production_qty
                })

        return result

    def _get_product_by_key(self, key: str) -> Product:
        """根据key获取产品对象"""
        parts = key.split('_')
        if len(parts) == 3:
            try:
                return Product.objects.get(
                    vehicle_model__name=parts[0],
                    color__name=parts[1],
                    position_type__name=parts[2]
                )
            except Product.DoesNotExist:
                pass
        return None

    def calculate_short_term_risk(self, short_term_demand: List[Dict]) -> List[Dict]:
        """
        计算短期风险表
        终值 = 当前库存 - 短期需求生产数量
        """
        risks = []
        for item in short_term_demand:
            product = item['product']
            key = self._get_product_key(product)
            current_stock = self.inventory_data.get(key, {}).get('current', 0)
            safety_stock = self.safety_stock_data.get(key, 0)

            final_value = current_stock - item['production_quantity']

            risks.append({
                'product': product,
                'final_value': final_value,
                'safety_stock': safety_stock,
                'is_shortage': final_value < 0
            })

        # 按终值排序（越小优先级越高）
        risks.sort(key=lambda x: x['final_value'])

        # 添加排名
        for i, risk in enumerate(risks, 1):
            risk['rank'] = i

        return risks

    def calculate_long_term_risk(self, long_term_demand: List[Dict]) -> List[Dict]:
        """
        计算长期风险表
        风险值 = 安全库存 - 长期终值
        组风险 = max(front风险, rear风险)
        """
        risks = []
        for item in long_term_demand:
            product = item['product']
            key = self._get_product_key(product)
            current_stock = self.inventory_data.get(key, {}).get('current', 0)
            safety_stock = self.safety_stock_data.get(key, 0)

            final_value = current_stock - item['production_quantity']
            risk_value = safety_stock - final_value

            risks.append({
                'product': product,
                'final_value': final_value,
                'safety_stock': safety_stock,
                'risk_value': risk_value
            })

        # 计算组风险并排序
        vehicle_color_groups = {}
        for risk in risks:
            product = risk['product']
            group_key = f"{product.vehicle_model.name}_{product.color.name}"
            if group_key not in vehicle_color_groups:
                vehicle_color_groups[group_key] = {
                    self.POSITION_FRONT: None,
                    self.POSITION_REAR: None
                }
            vehicle_color_groups[group_key][product.position_type.name] = risk

        # 计算每组风险
        for group_key, group_data in vehicle_color_groups.items():
            front_risk = group_data.get(self.POSITION_FRONT, {}).get('risk_value', 0) if group_data.get(self.POSITION_FRONT) else 0
            rear_risk = group_data.get(self.POSITION_REAR, {}).get('risk_value', 0) if group_data.get(self.POSITION_REAR) else 0
            group_risk_value = max(front_risk, rear_risk)

            if group_data.get(self.POSITION_FRONT):
                group_data[self.POSITION_FRONT]['group_risk_value'] = group_risk_value
            if group_data.get(self.POSITION_REAR):
                group_data[self.POSITION_REAR]['group_risk_value'] = group_risk_value

        # 按组风险值排序
        risks.sort(key=lambda x: x.get('group_risk_value', 0), reverse=True)

        # 添加排名
        for i, risk in enumerate(risks, 1):
            risk['rank'] = i

        return risks

    def calculate_short_term_plan(self, short_risks: List[Dict]) -> List[Dict]:
        """
        计算短期计划表
        根据短期风险和可用车数分配生产
        """
        # 计算短期可用车数
        total_vehicles = int(self.params['TOTAL_VEHICLES'] * self.params['SHORT_TERM_CAPACITY'] / 100)

        # 为终值 < 0 的产品分配车数
        plans = []
        remaining_vehicles = total_vehicles

        for risk in short_risks:
            if risk['final_value'] < 0 and remaining_vehicles > 0:
                product = risk['product']
                hanging_count = product.hanging_count_per_vehicle

                # 计算需要生产的车数（抵消终值）
                needed_production = abs(risk['final_value'])
                needed_vehicles = math.ceil(needed_production / hanging_count)

                # 分配车数
                allocated_vehicles = min(needed_vehicles, remaining_vehicles)

                plans.append({
                    'product': product,
                    'vehicle_count': allocated_vehicles
                })

                remaining_vehicles -= allocated_vehicles

        return plans

    def calculate_long_term_plan(self, long_risks: List[Dict]) -> List[Dict]:
        """
        计算长期计划表
        规则：
        1. 分配front/rear约束
        2. 长期前后平衡约束：|front车数 - rear车数| ≤ D
        3. 总车数约束
        4. 组车数平衡约束
        """
        # 计算长期可用车数
        total_vehicles = int(self.params['TOTAL_VEHICLES'] * self.params['LONG_TERM_CAPACITY'] / 100)

        plans = []
        front_count = 0
        rear_count = 0

        # 按组风险从高到低分配
        for risk in long_risks:
            if risk.get('group_risk_value', 0) > 0:
                product = risk['product']
                position = product.position_type.name
                hanging_count = product.hanging_count_per_vehicle

                # 计算建议车数
                suggested_vehicles = max(1, math.ceil(abs(risk['final_value']) / hanging_count))

                # 检查前后平衡
                if position == self.POSITION_FRONT:
                    if abs((front_count + suggested_vehicles) - rear_count) <= self.params['FRONT_REAR_BALANCE_D']:
                        plans.append({
                            'product': product,
                            'vehicle_count': suggested_vehicles
                        })
                        front_count += suggested_vehicles
                else:  # POSITION_REAR
                    if abs(front_count - (rear_count + suggested_vehicles)) <= self.params['FRONT_REAR_BALANCE_D']:
                        plans.append({
                            'product': product,
                            'vehicle_count': suggested_vehicles
                        })
                        rear_count += suggested_vehicles

        return plans

    def optimize_formation(self, short_plan: List[Dict], long_plan: List[Dict]) -> List[Dict]:
        """
        阵型结构约束优化
        合并短期和长期计划，生成最终阵型
        """
        formation = []

        # 合并计划
        all_plans = []
        for plan in short_plan:
            all_plans.append({**plan, 'plan_type': 'short'})
        for plan in long_plan:
            all_plans.append({**plan, 'plan_type': 'long'})

        # 分配槽位
        slot_number = 1
        total_slots = int(self.params['TOTAL_VEHICLES'])

        for plan in all_plans:
            product = plan['product']
            vehicle_count = plan['vehicle_count']

            for _ in range(vehicle_count):
                if slot_number > total_slots:
                    break
                formation.append({
                    'slot_number': slot_number,
                    'product': product,
                    'plan_type': plan['plan_type']
                })
                slot_number += 1

        return formation

    def update_inventory(self, formation: List[Dict]) -> Dict:
        """
        根据阵型更新库存
        """
        updated_inventory = {}

        # 按产品统计生产数量
        production_by_product = {}
        for slot in formation:
            product = slot['product']
            key = self._get_product_key(product)
            if key not in production_by_product:
                production_by_product[key] = 0
            production_by_product[key] += product.hanging_count_per_vehicle

        # 更新库存
        for key, produced_qty in production_by_product.items():
            current_stock = self.inventory_data.get(key, {}).get('current', 0)
            updated_inventory[key] = {
                'current': current_stock,
                'produced': produced_qty,
                'updated': current_stock + produced_qty
            }

        return updated_inventory

    def save_results(self, results: Dict, record: ScheduleRecord):
        """
        保存计算结果到数据库
        """
        # 保存需求记录
        for demand_type in ['short_term', 'long_term']:
            for item in results[demand_type]:
                DemandRecord.objects.create(
                    record=record,
                    product=item['product'],
                    demand_type='short' if demand_type == 'short_term' else 'long',
                    demand_quantity=item['demand_quantity'],
                    production_quantity=item['production_quantity']
                )

        # 保存风险记录
        for risk_type in ['short_risk', 'long_risk']:
            for item in results[risk_type]:
                RiskRecord.objects.create(
                    record=record,
                    product=item['product'],
                    risk_type='short' if risk_type == 'short_risk' else 'long',
                    final_value=item['final_value'],
                    safety_stock=item['safety_stock'],
                    risk_value=item.get('risk_value'),
                    group_risk_value=item.get('group_risk_value'),
                    rank=item.get('rank')
                )

        # 保存计划
        for plan_type in ['short_plan', 'long_plan']:
            for item in results[plan_type]:
                SchedulePlan.objects.create(
                    record=record,
                    product=item['product'],
                    plan_type='short' if plan_type == 'short_plan' else 'long',
                    vehicle_count=item['vehicle_count']
                )

        # 保存阵型
        for slot in results['formation']:
            FormationSlot.objects.create(
                record=record,
                slot_number=slot['slot_number'],
                product=slot['product'],
                plan_type=slot['plan_type']
            )
