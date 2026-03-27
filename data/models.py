from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class VehicleModel(models.Model):
    """车型"""
    name = models.CharField(max_length=50, unique=True, verbose_name="车型名称")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "车型"
        verbose_name_plural = "车型"
        ordering = ['name']

    def __str__(self):
        return self.name


class Color(models.Model):
    """颜色"""
    name = models.CharField(max_length=50, unique=True, verbose_name="颜色名称")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    DISPLAY_MAP = {
        "red": ("红", "#d9485f", "#ffffff"),
        "blue": ("蓝", "#2563eb", "#ffffff"),
        "white": ("白", "#f8fafc", "#111827"),
        "black": ("黑", "#111827", "#ffffff"),
        "gray": ("灰", "#6b7280", "#ffffff"),
        "grey": ("灰", "#6b7280", "#ffffff"),
        "silver": ("银", "#cbd5e1", "#111827"),
        "green": ("绿", "#16a34a", "#ffffff"),
        "yellow": ("黄", "#facc15", "#111827"),
        "orange": ("橙", "#f97316", "#ffffff"),
        "brown": ("棕", "#92400e", "#ffffff"),
        "purple": ("紫", "#7c3aed", "#ffffff"),
        "pink": ("粉", "#ec4899", "#ffffff"),
    }

    class Meta:
        verbose_name = "颜色"
        verbose_name_plural = "颜色"
        ordering = ['name']

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        key = (self.name or "").strip().lower()
        if key in self.DISPLAY_MAP:
            return self.DISPLAY_MAP[key][0]
        return self.name

    @property
    def display_hex(self):
        key = (self.name or "").strip().lower()
        if key in self.DISPLAY_MAP:
            return self.DISPLAY_MAP[key][1]
        palette = ["#0f766e", "#1d4ed8", "#be185d", "#9a3412", "#4338ca", "#15803d"]
        seed = sum(ord(ch) for ch in key) if key else 0
        return palette[seed % len(palette)]

    @property
    def display_text_color(self):
        key = (self.name or "").strip().lower()
        if key in self.DISPLAY_MAP:
            return self.DISPLAY_MAP[key][2]
        return "#ffffff"


class PositionType(models.Model):
    """前后位置类型"""
    name = models.CharField(max_length=10, choices=[('front', '前'), ('rear', '后')], unique=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "位置类型"
        verbose_name_plural = "位置类型"

    def __str__(self):
        return self.get_name_display()


class Product(models.Model):
    """产品 - 车型+颜色+位置的组合"""
    vehicle_model = models.ForeignKey(VehicleModel, on_delete=models.CASCADE, verbose_name="车型", related_name='products')
    color = models.ForeignKey(Color, on_delete=models.CASCADE, verbose_name="颜色", related_name='products')
    position_type = models.ForeignKey(PositionType, on_delete=models.CASCADE, verbose_name="位置", related_name='products')

    # 挂具配置
    hanging_count_per_vehicle = models.PositiveIntegerField(
        default=4, verbose_name="每车挂数",
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )

    # 合格率（百分比）
    yield_rate = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=80.00,
        verbose_name="合格率(%)",
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    is_active = models.BooleanField(default=True, verbose_name="启用")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "产品"
        verbose_name_plural = "产品"
        unique_together = ['vehicle_model', 'color', 'position_type']
        ordering = ['vehicle_model', 'color', 'position_type']

    def __str__(self):
        return f"{self.vehicle_model} {self.color} {self.position_type}"


class Inventory(models.Model):
    """涂装库存"""
    product = models.OneToOneField(Product, on_delete=models.CASCADE, verbose_name="产品", related_name='inventory')
    current_quantity = models.IntegerField(default=0, verbose_name="当前库存", validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "涂装库存"
        verbose_name_plural = "涂装库存"
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.product}: {self.current_quantity}"


class InjectionInventory(models.Model):
    """注塑库存"""
    product = models.OneToOneField(Product, on_delete=models.CASCADE, verbose_name="产品", related_name='injection_inventory')
    current_quantity = models.IntegerField(default=0, verbose_name="当前库存", validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "注塑库存"
        verbose_name_plural = "注塑库存"
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.product}: {self.current_quantity}"


class SafetyStock(models.Model):
    """安全库存"""
    product = models.OneToOneField(Product, on_delete=models.CASCADE, verbose_name="产品", related_name='safety_stock')
    quantity = models.IntegerField(default=0, verbose_name="安全库存数量", validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "安全库存"
        verbose_name_plural = "安全库存"
        ordering = ['product']

    def __str__(self):
        return f"{self.product}: {self.quantity}"


class AssemblyPullData(models.Model):
    """总成拉动数据"""
    sequence = models.PositiveIntegerField(verbose_name="顺序号")
    vehicle_model = models.ForeignKey(VehicleModel, on_delete=models.CASCADE, verbose_name="车型", related_name='assembly_data')
    color = models.ForeignKey(Color, on_delete=models.CASCADE, verbose_name="颜色", related_name='assembly_data')
    planned_time = models.DateTimeField(verbose_name="计划时间")

    # 导入批次标识
    import_batch = models.CharField(max_length=100, blank=True, verbose_name="导入批次")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "总成拉动数据"
        verbose_name_plural = "总成拉动数据"
        ordering = ['sequence']
        indexes = [
            models.Index(fields=['sequence']),
            models.Index(fields=['import_batch']),
        ]

    def __str__(self):
        return f"#{self.sequence} - {self.vehicle_model} {self.color}"


class SystemParameter(models.Model):
    """系统参数"""
    PARAMETER_CHOICES = [
        ('CYCLE_TIME_MIN', '涂装一圈时间(分钟)'),
        ('AVG_HANGING_COUNT', '每车平均挂数'),
        ('TOTAL_VEHICLES', '涂装线一圈车数'),
        ('SHORT_TERM_CAPACITY', '短期产能百分比(%)'),
        ('LONG_TERM_CAPACITY', '长期产能百分比(%)'),
        ('FRONT_REAR_BALANCE_D', '前后平衡约束差值'),
        ('GROUP_CAPACITY_LIMIT', '组车数平衡约束(%)'),
        ('LONG_TERM_FORECAST_HOURS', '长期需求预测时间(小时)'),
    ]

    param_key = models.CharField(max_length=50, choices=PARAMETER_CHOICES, unique=True, verbose_name="参数键")
    param_value = models.CharField(max_length=200, verbose_name="参数值")
    description = models.TextField(blank=True, verbose_name="描述")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "系统参数"
        verbose_name_plural = "系统参数"

    def __str__(self):
        return f"{self.get_param_key_display()}: {self.param_value}"

    def get_float_value(self):
        """获取浮点数值"""
        try:
            return float(self.param_value)
        except (ValueError, TypeError):
            return 0.0

    def get_int_value(self):
        """获取整数值"""
        try:
            return int(float(self.param_value))
        except (ValueError, TypeError):
            return 0


class ImportRecord(models.Model):
    """导入归档记录"""
    IMPORT_TYPE_CHOICES = [
        ("inventory", "涂装库存"),
        ("injection", "注塑库存"),
        ("safety", "安全库存"),
        ("assembly", "总成拉动"),
    ]
    STATUS_CHOICES = [
        ("success", "成功"),
        ("partial", "部分成功"),
        ("failed", "失败"),
    ]

    import_type = models.CharField(max_length=20, choices=IMPORT_TYPE_CHOICES, verbose_name="导入类型")
    file_name = models.CharField(max_length=255, verbose_name="文件名")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, verbose_name="状态")
    message = models.CharField(max_length=255, verbose_name="结果说明")
    success_count = models.PositiveIntegerField(default=0, verbose_name="成功条数")
    error_count = models.PositiveIntegerField(default=0, verbose_name="失败条数")
    error_details = models.JSONField(default=list, blank=True, verbose_name="错误明细")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "导入记录"
        verbose_name_plural = "导入记录"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_import_type_display()} - {self.file_name}"
