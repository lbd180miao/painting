from django.db import models
from data.models import Product, VehicleModel, Color

class ScheduleRecord(models.Model):
    """排产记录"""
    STATUS_CHOICES = [
        ('pending', '计算中'),
        ('completed', '已完成'),
        ('failed', '失败'),
        ('rolled_back', '已回退'),
    ]

    record_time = models.DateTimeField(auto_now_add=True, verbose_name="记录时间")
    short_term_duration = models.IntegerField(verbose_name="短期时长(分钟)")
    long_term_duration = models.IntegerField(verbose_name="长期时长(分钟)")
    total_vehicles = models.IntegerField(verbose_name="总车数")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="状态")
    error_message = models.TextField(blank=True, verbose_name="错误信息")

    # 计算参数快照
    cycle_time_min = models.IntegerField(verbose_name="涂装一圈时间(分钟)")
    avg_hanging_count = models.IntegerField(verbose_name="每车平均挂数")
    total_vehicles_in_line = models.IntegerField(verbose_name="涂装线一圈车数")
    short_term_capacity = models.FloatField(verbose_name="短期产能百分比")
    long_term_capacity = models.FloatField(verbose_name="长期产能百分比")
    front_rear_balance_d = models.IntegerField(verbose_name="前后平衡约束差值")
    group_capacity_limit = models.FloatField(verbose_name="组车数平衡约束")

    class Meta:
        verbose_name = "排产记录"
        verbose_name_plural = "排产记录"
        ordering = ['-record_time']

    def __str__(self):
        return f"排产记录 #{self.id} - {self.record_time}"


class DemandRecord(models.Model):
    """需求记录"""
    record = models.ForeignKey(ScheduleRecord, on_delete=models.CASCADE, related_name='demands', verbose_name="排产记录")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="产品")
    demand_type = models.CharField(max_length=20, choices=[('short', '短期'), ('long', '长期')], verbose_name="需求类型")
    demand_quantity = models.IntegerField(verbose_name="需求数量(台)")
    production_quantity = models.IntegerField(verbose_name="生产数量(台)")

    class Meta:
        verbose_name = "需求记录"
        verbose_name_plural = "需求记录"
        unique_together = ['record', 'product', 'demand_type']


class RiskRecord(models.Model):
    """风险记录"""
    record = models.ForeignKey(ScheduleRecord, on_delete=models.CASCADE, related_name='risks', verbose_name="排产记录")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="产品")
    risk_type = models.CharField(max_length=20, choices=[('short', '短期'), ('long', '长期')], verbose_name="风险类型")
    final_value = models.IntegerField(verbose_name="终值")
    safety_stock = models.IntegerField(verbose_name="安全库存")
    risk_value = models.IntegerField(null=True, blank=True, verbose_name="风险值")
    group_risk_value = models.IntegerField(null=True, blank=True, verbose_name="组风险值")
    rank = models.IntegerField(null=True, blank=True, verbose_name="排名")

    class Meta:
        verbose_name = "风险记录"
        verbose_name_plural = "风险记录"
        ordering = ['record', 'risk_type', 'rank']


class SchedulePlan(models.Model):
    """排产计划详情"""
    record = models.ForeignKey(ScheduleRecord, on_delete=models.CASCADE, related_name='plans', verbose_name="排产记录")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="产品")
    plan_type = models.CharField(max_length=20, choices=[('short', '短期'), ('long', '长期')], verbose_name="计划类型")
    vehicle_count = models.IntegerField(verbose_name="生产车数")
    note = models.CharField(max_length=255, blank=True, verbose_name="计划说明")

    class Meta:
        verbose_name = "排产计划"
        verbose_name_plural = "排产计划"


class FormationSlot(models.Model):
    """阵型槽位"""
    record = models.ForeignKey(ScheduleRecord, on_delete=models.CASCADE, related_name='formation_slots', verbose_name="排产记录")
    slot_number = models.IntegerField(verbose_name="槽位号")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, verbose_name="产品")
    plan_type = models.CharField(max_length=20, choices=[('short', '短期'), ('long', '长期')], verbose_name="计划类型")
    is_reused = models.BooleanField(default=False, verbose_name="是否复用上一轮槽位")

    class Meta:
        verbose_name = "阵型槽位"
        verbose_name_plural = "阵型槽位"
        unique_together = ['record', 'slot_number']
        ordering = ['slot_number']


class InventorySnapshot(models.Model):
    """排产库存快照"""
    INVENTORY_TYPE_CHOICES = [
        ('paint', '涂装库存'),
        ('injection', '注塑库存'),
    ]

    record = models.ForeignKey(ScheduleRecord, on_delete=models.CASCADE, related_name='inventory_snapshots', verbose_name="排产记录")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="产品")
    inventory_type = models.CharField(max_length=20, choices=INVENTORY_TYPE_CHOICES, verbose_name="库存类型")
    current_quantity = models.IntegerField(verbose_name="计算前库存")
    delta_quantity = models.IntegerField(verbose_name="库存变动")
    updated_quantity = models.IntegerField(verbose_name="更新后库存")

    class Meta:
        verbose_name = "库存快照"
        verbose_name_plural = "库存快照"
        ordering = ['inventory_type', 'product']
