# Scheduling Rule Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align the scheduling algorithm, inventory rolling, and result pages with the documented rolling scheduling rules.

**Architecture:** Refactor the scheduling service into staged calculations, persist plan explanations and inventory snapshots, then update the result views to render those staged outputs. Inventory rolling will use effective current values from prior updates and will commit the new state for the next run.

**Tech Stack:** Django, Django ORM, Django TestCase, SQLite

---

### Task 1: Add regression tests for scheduling rule alignment

**Files:**
- Modify: `schedule/tests.py`

**Step 1: Write failing tests for the documented behaviors**

- Manual short/long durations define the read windows.
- Effective inventory prefers `updated_quantity`.
- Long-term plan respects front/rear balance and model capacity limit.
- Formation optimization reuses prior slots.
- Saved inventory updates become the next run's current inventory.

**Step 2: Run the targeted tests and confirm they fail**

Run: `python manage.py test schedule.tests -v 2`

**Step 3: Commit after the tests exist and fail**

```bash
git add schedule/tests.py
git commit -m "test: add scheduling rule alignment regressions"
```

### Task 2: Extend models for traceability

**Files:**
- Modify: `schedule/models.py`
- Create: `schedule/migrations/0002_rule_alignment_fields.py`

**Step 1: Add minimal fields**

- Add plan note field on `SchedulePlan`.
- Add `is_reused` on `FormationSlot`.
- Add `InventorySnapshot` model for paint/injection inventory before and after values.

**Step 2: Run migrations**

Run: `python manage.py makemigrations schedule`

**Step 3: Commit**

```bash
git add schedule/models.py schedule/migrations/
git commit -m "feat: add scheduling traceability models"
```

### Task 3: Refactor scheduling algorithm in stages

**Files:**
- Modify: `schedule/services/algorithms.py`

**Step 1: Make the tests pass with minimal staged logic**

- Accept run-time durations.
- Load effective inventory values.
- Compute windowed demands.
- Compute short and long risks.
- Allocate short and long plans under documented constraints.
- Reuse formation slots from the latest completed record.
- Compute and persist rolling inventory updates.

**Step 2: Run the targeted tests**

Run: `python manage.py test schedule.tests -v 2`

**Step 3: Commit**

```bash
git add schedule/services/algorithms.py
git commit -m "feat: align scheduling algorithm with documented rules"
```

### Task 4: Update views and templates

**Files:**
- Modify: `schedule/views.py`
- Modify: `templates/schedule/calculate.html`
- Modify: `templates/schedule/result.html`

**Step 1: Surface staged results**

- Pass actual/recommended windows into the calculate page.
- Pass inventory snapshots and richer plan metadata into the result page.
- Render read windows, plan notes, slot reuse, and inventory update tables.

**Step 2: Run page-related tests or the relevant test suite**

Run: `python manage.py test schedule.tests -v 2`

**Step 3: Commit**

```bash
git add schedule/views.py templates/schedule/calculate.html templates/schedule/result.html
git commit -m "feat: expose rule-aligned scheduling results in UI"
```

### Task 5: Verify end-to-end behavior

**Files:**
- Modify: none

**Step 1: Run fresh verification**

Run: `python manage.py test schedule.tests -v 2`

**Step 2: Confirm migrations are in sync**

Run: `python manage.py makemigrations --check`

**Step 3: Commit only after green verification**

```bash
git add -A
git commit -m "feat: complete scheduling rule alignment"
```
