# Scheduling Rule Closed-Loop Optimization Design

Date: 2026-05-17

## Goal

Optimize the project around `doc/涂装双层滚动排产标准决策流程.md` so the scheduling workflow is stricter end to end:

- Source Excel samples can be imported without manual reshaping.
- Scheduling calculations follow the documented short-term and long-term rules.
- Inventory writes are transactional and reversible.
- Early rolling triggers are explicitly confirmed.
- Result pages and exports expose enough evidence to audit a run.

## Scope

This work is limited to the scheduling closed loop:

- Data import for assembly pull, paint inventory, safety stock, and injection inventory.
- Scheduling algorithm constraints and inventory usage.
- Schedule creation, persistence, rollback, and early-trigger guard.
- Result/history/Excel audit outputs.
- Focused tests for the above.

This work will not redesign unrelated CRUD pages, replace the UI framework, or rewrite the whole algorithm into a new architecture unless a small extraction is needed to make the rules testable.

## Current Gaps

### Import Contract

`doc/3.2涂装库存.xlsx` uses these sample structures:

- Paint inventory sheet: `物料`, `当前库存`, `安全库存`
- Injection inventory sheet: `物料`, `当前注塑库存`
- Injection material names such as `A0front_raw`, without color.

The current injection import expects `当前库存` and parses material names like colored finished products. That prevents the documented sample data from loading cleanly into the system.

### Rule Enforcement

The current algorithm already covers most documented stages, but several behaviors need explicit tests and tighter implementation:

- Short-term and long-term demand windows must be contiguous and non-overlapping.
- Long-term risk must stay independent from short-term risk, using the same time point inventory.
- Long-term allocation must preserve group-risk ordering while applying front/rear balance, model capacity, total capacity, and injection constraints.
- Allocation notes must explain the first limiting constraint clearly enough for result pages and Excel.

### Inventory Consistency

Schedule calculation creates persistent records and updates inventory. These writes must behave as one unit: either all calculation outputs and inventory updates are saved, or none are. Rollback must restore the inventory snapshot before the latest completed run.

### Rolling Trigger

The process document requires confirmation when a user starts a new schedule less than one line cycle after the previous completed schedule. The backend should enforce this guard so it does not depend only on browser behavior.

## Proposed Design

### 1. Import Compatibility Layer

Extend import parsing so the app accepts both existing internal templates and the documented sample workbook shapes.

For injection inventory:

- Accept `当前库存` or `当前注塑库存` as the quantity column.
- Parse raw material names like `A0front_raw` and `A0rear_raw`.
- Treat raw injection inventory as shared by vehicle model and position, not by color.
- When the scheduling algorithm checks injection availability for a colored product, it can consume from the matching raw bucket for that vehicle model and position.

For paint inventory and safety stock:

- Keep parsing colored finished product names such as `A0front red`.
- If one workbook contains both current inventory and safety stock columns, import each value into its corresponding table when the selected import type supports it.

### 2. Scheduling Calculation Rules

Keep `SchedulingAlgorithm` as the orchestration point, but make the calculation stages easier to reason about:

1. Load parameters, active products, current paint inventory, current injection inventory, safety stock, assembly pull data, and previous formation slots.
2. Calculate short and long demand windows:
   - Short window starts at sequence offset 0.
   - Long window starts immediately after the short window.
   - Manual durations override recommended values.
3. Calculate risks:
   - Short final value: `current paint inventory - short demand pieces`.
   - Long final value: `current paint inventory - long demand pieces`.
   - Long risk value: `safety stock - long final value`.
   - Group risk: max of front and rear risk for the same vehicle model and color.
4. Allocate short-term capacity:
   - First priority: negative short final values, most negative first.
   - Second priority: non-negative final values below safety stock, highest risk first.
   - Stop at short capacity or injection availability.
5. Allocate long-term capacity:
   - Process groups by group risk descending.
   - Prefer the higher-risk side in each group.
   - Apply group front/rear risk-difference correction.
   - Respect total long-term capacity, model capacity limit, global front/rear balance, and injection availability.
6. Build formation:
   - Reuse exact previous slots first.
   - Then reuse same vehicle model and position where possible.
   - Fill remaining slots deterministically.
   - Preserve explicit empty slots in display if material is unavailable.
7. Compute inventory updates:
   - Paint inventory reflects planned good output and documented demand consumption policy.
   - Injection inventory reflects planned raw input consumption.
   - Snapshot current, delta, and updated values for every changed product or raw bucket.

### 3. Transaction and Rollback

Schedule creation will be transactional:

- Create the schedule record.
- Run calculation.
- Persist demands, risks, plans, formation slots, inventory snapshots, and inventory updates.
- Mark the record completed.

If any step fails, the transaction rolls back. The failed record may be saved separately with an error message only if no inventory mutation has occurred.

Rollback remains limited to the latest completed record and restores inventory quantities from `InventorySnapshot.current_quantity`, then marks the record `rolled_back`.

### 4. Early Trigger Guard

Add a backend guard based on the latest completed schedule:

- If elapsed time is at least `CYCLE_TIME_MIN`, proceed normally.
- If elapsed time is less than `CYCLE_TIME_MIN`, require an explicit confirmation flag in the POST.
- The calculate page should show the elapsed time and offer a confirmation path, but the backend remains authoritative.

### 5. Audit Outputs

Result page, history page, and Excel export should expose the same core evidence:

- Short and long window ranges.
- Demand totals and production quantities.
- Risk rankings and group-risk values.
- Short/long plan vehicle counts and limiting notes.
- Injection constraint summary.
- Plan gap summary.
- Formation slot reuse and empty-slot count.
- Paint and injection inventory before, delta, and after.
- Plan score as a summary indicator, backed by the detailed tables.

## Testing Strategy

Use test-first changes for each behavior:

- Import accepts `当前注塑库存` and `A0front_raw` sample rows.
- Raw injection inventory is shared across colors for the same vehicle model and position.
- Short and long demand windows remain non-overlapping.
- Long-term risk is calculated from the original current inventory, not short-term final inventory.
- Long-term plan notes identify capacity, model limit, balance, or injection constraints.
- Schedule creation rolls back all persisted outputs and inventory mutations on failure.
- Early trigger without confirmation is blocked; early trigger with confirmation proceeds.
- Rollback restores inventory from the latest completed record only.
- Excel export includes the audit sheets and headers needed for the above.

Verification command:

```powershell
python manage.py test schedule.tests data.tests -v 2
```

Also run:

```powershell
python manage.py makemigrations --check
```

## Acceptance Criteria

- The documented sample workbook shapes are accepted by import logic.
- A scheduling run can be traced from imported data through demand, risk, plan, formation, inventory update, and export.
- Inventory state is not partially mutated after calculation failure.
- Early rolling schedules require explicit confirmation when within the configured cycle time.
- Existing tests pass, and new tests cover the optimized behavior.
