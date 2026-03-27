# 简化库存更新 + 添加回退功能

生产计划执行后直接覆盖原始库存（`current_quantity`），移除 `updated_quantity` 概念。在历史记录页面为每条记录添加"回退"按钮，利用已有的 [InventorySnapshot](file:///d:/workspace2/painting/schedule/models.py#96-114) 逆向恢复库存，一级一级地往上回退。

## User Review Required

> [!IMPORTANT]
> 回退只允许从最新记录往前逐条回退（即只有最新一条已完成记录可以回退），不能跳过中间记录。回退后 [ScheduleRecord](file:///d:/workspace2/painting/schedule/models.py#4-35) 保留但被标记为 `rolled_back` 状态。

> [!WARNING]
> `updated_quantity` 和 `update_time` 字段将从 [Inventory](file:///d:/workspace2/painting/data/models.py#120-136)/[InjectionInventory](file:///d:/workspace2/painting/data/models.py#138-154) 模型中移除，需要做数据库迁移。导入视图中的相关赋值也会被清理。

## Proposed Changes

### 数据模型

#### [MODIFY] [models.py](file:///d:/workspace2/painting/data/models.py)
- [Inventory](file:///d:/workspace2/painting/data/models.py#120-136)：移除 `updated_quantity`、`update_time` 字段
- [InjectionInventory](file:///d:/workspace2/painting/data/models.py#138-154)：移除 `updated_quantity`、`update_time` 字段

#### [MODIFY] [models.py](file:///d:/workspace2/painting/schedule/models.py)
- [ScheduleRecord](file:///d:/workspace2/painting/schedule/models.py#4-35)：`STATUS_CHOICES` 增加 [('rolled_back', '已回退')](file:///d:/workspace2/painting/data/models.py#147-151)

---

### 算法层

#### [MODIFY] [algorithms.py](file:///d:/workspace2/painting/schedule/services/algorithms.py)
- [_load_paint_inventory](file:///d:/workspace2/painting/schedule/services/algorithms.py#68-80) / [_load_injection_inventory](file:///d:/workspace2/painting/schedule/services/algorithms.py#81-93)：直接使用 `current_quantity`，不再调用 [_effective_quantity](file:///d:/workspace2/painting/schedule/views.py#34-36)
- [_persist_inventory_updates](file:///d:/workspace2/painting/schedule/services/algorithms.py#792-816)：只更新 `current_quantity`，不再写 `updated_quantity`/`update_time`
- 移除 [_effective_quantity](file:///d:/workspace2/painting/schedule/views.py#34-36) 方法

---

### 视图层

#### [MODIFY] [views.py](file:///d:/workspace2/painting/schedule/views.py)
- 移除 [_effective_quantity](file:///d:/workspace2/painting/schedule/views.py#34-36) 辅助函数
- [_build_calculate_preview](file:///d:/workspace2/painting/schedule/views.py#38-63) 中直接用 `current_quantity`
- 新增 `history_rollback_view(request, id)` 视图：
  1. 校验该记录是最新的已完成记录
  2. 读取该记录的 [InventorySnapshot](file:///d:/workspace2/painting/schedule/models.py#96-114)
  3. 对每个快照：`current_quantity -= delta_quantity`（逆向操作）
  4. 将记录状态改为 `rolled_back`
  5. redirect 回历史页

#### [MODIFY] [urls.py](file:///d:/workspace2/painting/schedule/urls.py)
- 新增路由 `history/<int:id>/rollback/` → `history_rollback_view`

#### [MODIFY] [views.py](file:///d:/workspace2/painting/data/views.py)
- 导入函数中移除对 `updated_quantity`/`update_time` 的赋值
- 导出函数中移除对 `updated_quantity`/`update_time` 的引用

---

### 模板层

#### [MODIFY] [history.html](file:///d:/workspace2/painting/templates/schedule/history.html)
- 操作列：为最新一条已完成记录显示"回退"按钮（POST form + confirm 提示）
- 已回退状态显示对应 badge

---

### 数据库迁移

- 生成迁移文件以移除 `updated_quantity`/`update_time` 字段，并为 [ScheduleRecord](file:///d:/workspace2/painting/schedule/models.py#4-35) 的 status 增加选项

---

## Verification Plan

### Automated Tests

运行所有现有测试确保不破坏已有功能：
```bash
python manage.py test schedule -v2
```

现有测试中 [test_inventory_updates_become_current_inventory_for_next_run](file:///d:/workspace2/painting/schedule/tests.py#293-331) 和 [test_updated_inventory_is_used_as_effective_current_inventory](file:///d:/workspace2/painting/schedule/tests.py#143-159) 需要更新以适配新逻辑（不再有 `updated_quantity`）。

新增测试：
- `test_rollback_restores_inventory_to_pre_schedule_state`：执行排产 → 回退 → 验证 `current_quantity` 恢复
- `test_only_latest_completed_record_can_be_rolled_back`：非最新记录回退应失败
- `test_rolled_back_record_status_is_updated`：回退后记录状态变为 `rolled_back`

### Manual Verification
- 在浏览器中打开历史记录页面，确认最新一条已完成记录有"回退"按钮，之前的记录没有
- 点击回退按钮后，检查涂装库存和注塑库存是否恢复到排产前的值
