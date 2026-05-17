# Scheduling Rule Closed-Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the documented scheduling workflow work as a reliable closed loop from sample Excel import through calculation, inventory update, rollback, and audit output.

**Architecture:** Keep the existing Django app structure and improve the current import helpers, scheduling service, schedule views, and export utilities in place. Add small helper functions only where they clarify material parsing, raw injection bucket lookup, early-trigger decisions, or transactional persistence.

**Tech Stack:** Django, Django ORM, Django TestCase, SQLite test database, pandas/openpyxl for Excel import/export.

---

## File Structure

- `data/views.py`: keep current import endpoints; add tolerant column detection and raw injection material parsing.
- `data/tests.py`: add import regression tests for documented workbook shapes and raw injection material names.
- `schedule/services/algorithms.py`: keep `SchedulingAlgorithm`; add raw injection bucket support and tighten allocation inventory consumption.
- `schedule/views.py`: add backend early-trigger guard and make schedule creation transactional.
- `schedule/tests.py`: add scheduling tests for raw injection sharing, early trigger confirmation, transaction rollback, and rollback guard.
- `schedule/utils.py`: add or adjust export assertions only if new audit fields are missing from Excel output.
- `templates/schedule/calculate.html`: show early-trigger confirmation state if backend context requires it.

## Task 1: Import Documented Injection Workbook Shapes

**Files:**
- Modify: `data/views.py`
- Test: `data/tests.py`

- [ ] **Step 1: Write failing tests for raw injection import**

Append these tests to `BaseConfigCrudTests` in `data/tests.py`:

```python
def test_injection_import_accepts_doc_sample_raw_material_format(self):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from io import BytesIO
    import pandas as pd
    from data.models import InjectionInventory, Product

    buffer = BytesIO()
    pd.DataFrame({
        "物料": ["A0front_raw", "A0rear_raw"],
        "当前注塑库存": [2000, 1800],
    }).to_excel(buffer, index=False)
    buffer.seek(0)

    response = self.client.post(
        "/data/import/",
        {
            "import_type": "injection",
            "file": SimpleUploadedFile(
                "injection.xlsx",
                buffer.getvalue(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        },
        follow=True,
    )

    self.assertContains(response, "成功导入注塑库存数据")
    self.assertEqual(InjectionInventory.objects.count(), 2)
    self.assertTrue(Product.objects.filter(vehicle_model__name="A0", position_type__name="front").exists())
    self.assertEqual(
        InjectionInventory.objects.get(product__vehicle_model__name="A0", product__position_type__name="front").current_quantity,
        2000,
    )
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```powershell
python manage.py test data.tests.BaseConfigCrudTests.test_injection_import_accepts_doc_sample_raw_material_format -v 2
```

Expected: FAIL because the import helper rejects `当前注塑库存` or cannot parse `A0front_raw`.

- [ ] **Step 3: Add raw material parsing helpers**

In `data/views.py`, replace `_parse_material_info` with:

```python
def _parse_material_info(material_name):
    """Parse finished or raw material names.

    Supported examples:
    - A0front red
    - A0rear blue
    - A0front_raw
    - A0rear_raw
    """
    material_name = str(material_name or "").strip()
    if not material_name:
        return None, None, None

    raw_name = material_name.replace("_raw", "").strip()
    parts = raw_name.split()
    vehicle_position_part = parts[0] if parts else ""
    color_name = parts[-1] if len(parts) >= 2 else "raw"

    lowered = vehicle_position_part.lower()
    if "front" in lowered:
        position_str = "front"
        vehicle_model_str = lowered.replace("front", "").replace("rear", "").strip().upper()
    elif "rear" in lowered:
        position_str = "rear"
        vehicle_model_str = lowered.replace("rear", "").replace("front", "").strip().upper()
    else:
        position_str = "front"
        vehicle_model_str = vehicle_position_part.strip()

    return vehicle_model_str, position_str, color_name
```

- [ ] **Step 4: Accept both injection quantity columns**

In `_import_injection_inventory`, replace the fixed expected-column block with:

```python
quantity_column = "当前库存"
if "当前注塑库存" in df.columns:
    quantity_column = "当前注塑库存"
elif "当前库存" not in df.columns:
    return _build_import_result(
        False,
        "Excel文件缺少必要列: 当前库存 或 当前注塑库存",
        errors=[{"row": "表头", "reason": "缺少必要列: 当前库存 或 当前注塑库存"}],
    )

if "物料" not in df.columns:
    return _build_import_result(
        False,
        "Excel文件缺少必要列: 物料",
        errors=[{"row": "表头", "reason": "缺少必要列: 物料"}],
    )
```

Then change:

```python
quantity = pd.to_numeric(row['当前库存'], errors='coerce')
```

to:

```python
quantity = pd.to_numeric(row[quantity_column], errors='coerce')
```

- [ ] **Step 5: Run the test and verify it passes**

Run:

```powershell
python manage.py test data.tests.BaseConfigCrudTests.test_injection_import_accepts_doc_sample_raw_material_format -v 2
```

Expected: PASS.

- [ ] **Step 6: Run data tests**

Run:

```powershell
python manage.py test data.tests -v 2
```

Expected: all data tests pass.

- [ ] **Step 7: Commit**

```powershell
git add -- data/views.py data/tests.py
git commit -m "feat: import documented injection inventory format"
```

## Task 2: Share Raw Injection Inventory Across Colors

**Files:**
- Modify: `schedule/services/algorithms.py`
- Test: `schedule/tests.py`

- [ ] **Step 1: Write failing test for raw bucket sharing**

Append this test to `SchedulingRuleAlignmentTests` in `schedule/tests.py`:

```python
def test_injection_inventory_is_shared_by_model_and_position_when_raw_color_exists(self):
    red_front = self.create_product(
        self.a0,
        self.red,
        self.front,
        hanging_count=2,
        yield_rate=100,
        inventory=0,
        injection_inventory=0,
        safety_stock=0,
    )
    self.create_product(
        self.a0,
        self.blue,
        self.front,
        hanging_count=2,
        yield_rate=100,
        inventory=0,
        injection_inventory=0,
        safety_stock=0,
    )
    raw_color = Color.objects.create(name="raw")
    raw_front = self.create_product(
        self.a0,
        raw_color,
        self.front,
        hanging_count=2,
        yield_rate=100,
        inventory=0,
        injection_inventory=4,
        safety_stock=0,
    )
    self.create_product(self.a0, self.red, self.rear, injection_inventory=20)
    self.add_pull(1, self.a0, self.red)
    self.add_pull(2, self.a0, self.blue)

    algorithm = SchedulingAlgorithm(short_term_duration=2, long_term_duration=0)
    results = algorithm.calculate()
    front_plan = [
        item for item in results["short_plan"]
        if item["product"].position_type.name == "front"
    ]

    self.assertEqual(sum(item["vehicle_count"] for item in front_plan), 2)
    self.assertEqual(algorithm._get_product_key(raw_front), f"A0_raw_front")
    self.assertIn(red_front.id, {item["product"].id for item in front_plan})
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```powershell
python manage.py test schedule.tests.SchedulingRuleAlignmentTests.test_injection_inventory_is_shared_by_model_and_position_when_raw_color_exists -v 2
```

Expected: FAIL because allocation only looks up colored injection inventory keys.

- [ ] **Step 3: Add injection bucket helpers**

In `schedule/services/algorithms.py`, add these methods below `_build_remaining_injection_inventory`:

```python
    def _make_raw_injection_key(self, product: Product) -> str:
        return self._make_product_key(
            product.vehicle_model.name,
            "raw",
            product.position_type.name,
        )

    def _resolve_injection_key(self, product: Product, remaining_injection_inventory: Dict[str, int]) -> str:
        product_key = self._get_product_key(product)
        if product_key in remaining_injection_inventory:
            return product_key
        raw_key = self._make_raw_injection_key(product)
        if raw_key in remaining_injection_inventory:
            return raw_key
        return product_key

    def _available_injection_vehicles(self, product: Product, remaining_injection_inventory: Dict[str, int]) -> tuple[str, int, int]:
        injection_key = self._resolve_injection_key(product, remaining_injection_inventory)
        available_pieces = max(remaining_injection_inventory.get(injection_key, 0), 0)
        available_vehicles = available_pieces // product.hanging_count_per_vehicle
        return injection_key, available_pieces, available_vehicles
```

- [ ] **Step 4: Use the helper in short-term allocation**

In `calculate_short_term_plan`, replace:

```python
product_key = self._get_product_key(product)
available_pieces = max(remaining_injection_inventory.get(product_key, 0), 0)
available_vehicles = available_pieces // product.hanging_count_per_vehicle
allocated = min(needed_vehicles, remaining_vehicles, available_vehicles)
```

with:

```python
injection_key, available_pieces, available_vehicles = self._available_injection_vehicles(
    product,
    remaining_injection_inventory,
)
allocated = min(needed_vehicles, remaining_vehicles, available_vehicles)
```

Replace the inventory decrement block with:

```python
remaining_injection_inventory[injection_key] = max(
    available_pieces - allocated * product.hanging_count_per_vehicle,
    0,
)
```

- [ ] **Step 5: Use the helper in long-term allocation and backfill**

In `calculate_long_term_plan`, replace product-key injection lookup with `_available_injection_vehicles`, and decrement `remaining_injection_inventory[injection_key]`.

In `_consume_backfill_inventory`, replace:

```python
product_key = self._get_product_key(product)
available_pieces = max(remaining_injection_inventory.get(product_key, 0), 0)
if available_pieces < product.hanging_count_per_vehicle:
    return False
remaining_injection_inventory[product_key] = (
    available_pieces - product.hanging_count_per_vehicle
)
return True
```

with:

```python
injection_key, available_pieces, _available_vehicles = self._available_injection_vehicles(
    product,
    remaining_injection_inventory,
)
if available_pieces < product.hanging_count_per_vehicle:
    return False
remaining_injection_inventory[injection_key] = available_pieces - product.hanging_count_per_vehicle
return True
```

- [ ] **Step 6: Run the focused test**

Run:

```powershell
python manage.py test schedule.tests.SchedulingRuleAlignmentTests.test_injection_inventory_is_shared_by_model_and_position_when_raw_color_exists -v 2
```

Expected: PASS.

- [ ] **Step 7: Run schedule tests**

Run:

```powershell
python manage.py test schedule.tests -v 2
```

Expected: all schedule tests pass.

- [ ] **Step 8: Commit**

```powershell
git add -- schedule/services/algorithms.py schedule/tests.py
git commit -m "feat: share raw injection inventory by model and position"
```

## Task 3: Add Backend Early-Trigger Guard

**Files:**
- Modify: `schedule/views.py`
- Modify: `templates/schedule/calculate.html`
- Test: `schedule/tests.py`

- [ ] **Step 1: Write failing tests for early trigger guard**

Append these tests to `SchedulingRuleAlignmentTests`:

```python
def test_calculate_post_requires_confirmation_when_last_completed_run_is_inside_cycle_time(self):
    completed = self.create_record()
    completed.status = "completed"
    completed.record_time = timezone.now()
    completed.save(update_fields=["status", "record_time"])

    response = self.client.post(
        "/schedule/calculate/",
        {"short_term_duration": "0", "long_term_duration": "0"},
        follow=True,
    )

    self.assertContains(response, "距离上次排产")
    self.assertEqual(ScheduleRecord.objects.filter(status="completed").count(), 1)

def test_calculate_post_allows_early_trigger_when_confirmed(self):
    completed = self.create_record()
    completed.status = "completed"
    completed.record_time = timezone.now()
    completed.save(update_fields=["status", "record_time"])

    self.create_product(self.a0, self.red, self.front, injection_inventory=10)
    self.create_product(self.a0, self.red, self.rear, injection_inventory=10)

    response = self.client.post(
        "/schedule/calculate/",
        {
            "short_term_duration": "0",
            "long_term_duration": "0",
            "confirm_early_trigger": "1",
        },
        follow=True,
    )

    self.assertEqual(response.status_code, 200)
    self.assertEqual(ScheduleRecord.objects.filter(status="completed").count(), 2)
```

- [ ] **Step 2: Run both tests and verify they fail**

Run:

```powershell
python manage.py test schedule.tests.SchedulingRuleAlignmentTests.test_calculate_post_requires_confirmation_when_last_completed_run_is_inside_cycle_time schedule.tests.SchedulingRuleAlignmentTests.test_calculate_post_allows_early_trigger_when_confirmed -v 2
```

Expected: first test fails because no backend guard exists.

- [ ] **Step 3: Add early-trigger helper**

In `schedule/views.py`, add:

```python
def _latest_completed_record():
    return ScheduleRecord.objects.filter(status="completed").order_by("-record_time", "-id").first()


def _build_early_trigger_context(params):
    latest = _latest_completed_record()
    if not latest:
        return {"requires_confirmation": False}

    cycle_minutes = int(params.get("CYCLE_TIME_MIN", 300) or 300)
    elapsed = timezone.now() - latest.record_time
    elapsed_minutes = int(elapsed.total_seconds() // 60)
    return {
        "requires_confirmation": elapsed_minutes < cycle_minutes,
        "latest_record": latest,
        "elapsed_minutes": elapsed_minutes,
        "cycle_minutes": cycle_minutes,
    }
```

Also add this import:

```python
from django.utils import timezone
```

- [ ] **Step 4: Enforce guard on POST**

In `calculate_view`, after parameters are loaded and before creating `ScheduleRecord`, add:

```python
early_trigger = _build_early_trigger_context({
    "CYCLE_TIME_MIN": get_int("CYCLE_TIME_MIN", 300),
})
if early_trigger["requires_confirmation"] and request.POST.get("confirm_early_trigger") != "1":
    messages.warning(
        request,
        f"距离上次排产仅过去 {early_trigger['elapsed_minutes']} 分钟，涂装线一圈约需 {early_trigger['cycle_minutes']} 分钟。请确认后再生成新的排产计划。",
    )
    return redirect("schedule:calculate")
```

- [ ] **Step 5: Pass early-trigger context on GET**

In GET context construction, add:

```python
"early_trigger": _build_early_trigger_context(param_dict),
```

- [ ] **Step 6: Add confirmation checkbox to calculate page**

In `templates/schedule/calculate.html`, near the submit button, add:

```html
{% if early_trigger.requires_confirmation %}
<div class="alert alert-warning">
    距离上次排产仅过去 {{ early_trigger.elapsed_minutes }} 分钟，涂装线一圈约需 {{ early_trigger.cycle_minutes }} 分钟。
    如需提前生成，请勾选确认。
</div>
<label class="form-check mb-3">
    <input class="form-check-input" type="checkbox" name="confirm_early_trigger" value="1">
    <span class="form-check-label">确认提前生成新的排产计划</span>
</label>
{% endif %}
```

- [ ] **Step 7: Run focused tests**

Run:

```powershell
python manage.py test schedule.tests.SchedulingRuleAlignmentTests.test_calculate_post_requires_confirmation_when_last_completed_run_is_inside_cycle_time schedule.tests.SchedulingRuleAlignmentTests.test_calculate_post_allows_early_trigger_when_confirmed -v 2
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add -- schedule/views.py templates/schedule/calculate.html schedule/tests.py
git commit -m "feat: require confirmation for early schedule trigger"
```

## Task 4: Make Schedule Creation Transactionally Consistent

**Files:**
- Modify: `schedule/views.py`
- Test: `schedule/tests.py`

- [ ] **Step 1: Write failing test for save failure rollback**

Append this test to `SchedulingRuleAlignmentTests`:

```python
def test_schedule_creation_rolls_back_record_and_inventory_when_save_results_fails(self):
    front_product = self.create_product(
        self.a0,
        self.red,
        self.front,
        hanging_count=1,
        yield_rate=100,
        inventory=0,
        injection_inventory=10,
    )
    self.create_product(
        self.a0,
        self.red,
        self.rear,
        hanging_count=1,
        yield_rate=100,
        inventory=0,
        injection_inventory=10,
    )
    self.add_pull(1, self.a0, self.red)

    with patch.object(SchedulingAlgorithm, "send_risk_notifications", side_effect=RuntimeError("boom")):
        response = self.client.post(
            "/schedule/calculate/",
            {"short_term_duration": "1", "long_term_duration": "0"},
            follow=True,
        )

    self.assertContains(response, "计算失败")
    self.assertEqual(ScheduleRecord.objects.exclude(status="failed").count(), 0)
    self.assertEqual(Inventory.objects.get(product=front_product).current_quantity, 0)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
python manage.py test schedule.tests.SchedulingRuleAlignmentTests.test_schedule_creation_rolls_back_record_and_inventory_when_save_results_fails -v 2
```

Expected: FAIL if the record or inventory mutations survive the exception.

- [ ] **Step 3: Move record creation inside transaction**

In `schedule/views.py`, replace the POST record creation and save block with this structure:

```python
record = None
try:
    with transaction.atomic():
        record = ScheduleRecord.objects.create(
            short_term_duration=short_term_duration,
            long_term_duration=long_term_duration,
            status="pending",
            cycle_time_min=get_int("CYCLE_TIME_MIN", 300),
            avg_hanging_count=get_int("AVG_HANGING_COUNT", 4),
            total_vehicles_in_line=get_int("TOTAL_VEHICLES", 100),
            short_term_capacity=get_float("SHORT_TERM_CAPACITY", 40.0),
            long_term_capacity=get_float("LONG_TERM_CAPACITY", 60.0),
            front_rear_balance_d=get_int("FRONT_REAR_BALANCE_D", 15),
            group_capacity_limit=get_float("GROUP_CAPACITY_LIMIT", 40.0),
            total_vehicles=get_int("TOTAL_VEHICLES", 100),
        )
        algorithm = SchedulingAlgorithm(
            short_term_duration=short_term_duration,
            long_term_duration=long_term_duration,
            record_time=record.record_time,
        )
        results = algorithm.calculate()
        algorithm.save_results(results, record)
        record.status = "completed"
        record.save(update_fields=["status"])
except Exception as e:
    ScheduleRecord.objects.create(
        short_term_duration=short_term_duration,
        long_term_duration=long_term_duration,
        status="failed",
        error_message=str(e),
        cycle_time_min=get_int("CYCLE_TIME_MIN", 300),
        avg_hanging_count=get_int("AVG_HANGING_COUNT", 4),
        total_vehicles_in_line=get_int("TOTAL_VEHICLES", 100),
        short_term_capacity=get_float("SHORT_TERM_CAPACITY", 40.0),
        long_term_capacity=get_float("LONG_TERM_CAPACITY", 60.0),
        front_rear_balance_d=get_int("FRONT_REAR_BALANCE_D", 15),
        group_capacity_limit=get_float("GROUP_CAPACITY_LIMIT", 40.0),
        total_vehicles=get_int("TOTAL_VEHICLES", 100),
    )
    messages.error(request, f"计算失败: {str(e)}")
else:
    messages.success(request, f"排产计算完成！记录ID: {record.id}")
    return redirect("schedule:result", id=record.id)
```

Keep parsing and early-trigger validation before this block.

- [ ] **Step 4: Run focused test**

Run:

```powershell
python manage.py test schedule.tests.SchedulingRuleAlignmentTests.test_schedule_creation_rolls_back_record_and_inventory_when_save_results_fails -v 2
```

Expected: PASS.

- [ ] **Step 5: Run schedule tests**

Run:

```powershell
python manage.py test schedule.tests -v 2
```

Expected: all schedule tests pass.

- [ ] **Step 6: Commit**

```powershell
git add -- schedule/views.py schedule/tests.py
git commit -m "fix: make schedule creation transactional"
```

## Task 5: Verify Audit Output and Final Integration

**Files:**
- Modify if needed: `schedule/utils.py`
- Test: `schedule/tests.py`

- [ ] **Step 1: Write or update Excel audit test**

If existing Excel tests do not cover the required audit headers, add this assertion to `test_excel_export_includes_plan_notes_slot_reuse_and_inventory_snapshots`:

```python
self.assertIn("注塑约束", workbook.sheetnames)
self.assertIn("计划缺口", workbook.sheetnames)
summary_values = [
    workbook["计算摘要"].cell(row=row, column=1).value
    for row in range(2, workbook["计算摘要"].max_row + 1)
]
self.assertIn("注塑受限物料数", summary_values)
self.assertIn("计划缺口物料数", summary_values)
```

- [ ] **Step 2: Run the Excel test**

Run:

```powershell
python manage.py test schedule.tests.SchedulingRuleAlignmentTests.test_excel_export_includes_plan_notes_slot_reuse_and_inventory_snapshots -v 2
```

Expected: PASS if current export already includes the audit sheets; otherwise FAIL.

- [ ] **Step 3: Fix export only if the test fails**

If needed, update `schedule/utils.py` so `export_schedule_to_excel` writes these sheets:

```python
_write_injection_constraint_sheet(writer, record)
_write_plan_gap_sheet(writer, record)
```

And make sure `_write_summary_sheet` includes:

```python
"注塑受限物料数"
"注塑截断车数"
"计划缺口物料数"
"计划缺口车数"
```

- [ ] **Step 4: Run final test suite**

Run:

```powershell
python manage.py test schedule.tests data.tests -v 2
```

Expected: all tests pass.

- [ ] **Step 5: Check migrations**

Run:

```powershell
python manage.py makemigrations --check
```

Expected: `No changes detected`.

- [ ] **Step 6: Review diff**

Run:

```powershell
git diff -- data/views.py data/tests.py schedule/services/algorithms.py schedule/views.py schedule/tests.py schedule/utils.py templates/schedule/calculate.html
```

Expected: diff only covers the planned closed-loop optimization.

- [ ] **Step 7: Commit final verification adjustments**

If Task 5 changed files:

```powershell
git add -- schedule/utils.py schedule/tests.py
git commit -m "test: verify scheduling audit export"
```

If Task 5 changed no files, skip this commit.

## Self-Review

- Spec coverage: import compatibility is covered by Task 1, raw injection allocation by Task 2, early trigger by Task 3, transaction and rollback safety by Task 4, audit output and verification by Task 5.
- Placeholder scan: no placeholder markers remain.
- Type consistency: helper names introduced in Task 2 are used consistently by short-term, long-term, and backfill allocation.
- Scope check: the plan stays inside the scheduling closed loop and avoids unrelated CRUD or UI redesign.
