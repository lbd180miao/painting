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

    class Meta:
        verbose_name = "颜色"
        verbose_name_plural = "颜色"
        ordering = ['name']

    def __str__(self):
        return self.name


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
        return f"{self.vehicle_model} {self.color} {self.get_position_type_display()}"


class Inventory(models.Model):
    """涂装库存"""
    product = models.OneToOneField(Product, on_delete=models.CASCADE, verbose_name="产品", related_name='inventory')
    current_quantity = models.IntegerField(default=0, verbose_name="当前库存", validators=[MinValueValidator(0)])
    updated_quantity = models.IntegerField(null=True, blank=True, verbose_name="更新后库存", validators=[MinValueValidator(0)])
    update_time = models.DateTimeField(null=True, blank=True, verbose_name="更新时间")
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
    updated_quantity = models.IntegerField(null=True, blank=True, verbose_name="更新后库存", validators=[MinValueValidator(0)])
    update_time = models.DateTimeField(null=True, blank=True, verbose_name="更新时间")
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
