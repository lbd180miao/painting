from django.contrib import admin
from .models import (
    VehicleModel, Color, PositionType, Product,
    Inventory, InjectionInventory, SafetyStock,
    AssemblyPullData, SystemParameter
)

@admin.register(VehicleModel)
class VehicleModelAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']


@admin.register(PositionType)
class PositionTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['vehicle_model', 'color', 'position_type', 'hanging_count_per_vehicle', 'yield_rate', 'is_active']
    list_filter = ['vehicle_model', 'color', 'position_type', 'is_active']
    search_fields = ['vehicle_model__name', 'color__name']
    list_editable = ['is_active']


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ['product', 'current_quantity', 'updated_at']
    search_fields = ['product__vehicle_model__name', 'product__color__name']


@admin.register(InjectionInventory)
class InjectionInventoryAdmin(admin.ModelAdmin):
    list_display = ['product', 'current_quantity', 'updated_at']
    search_fields = ['product__vehicle_model__name', 'product__color__name']


@admin.register(SafetyStock)
class SafetyStockAdmin(admin.ModelAdmin):
    list_display = ['product', 'quantity']
    search_fields = ['product__vehicle_model__name', 'product__color__name']


@admin.register(AssemblyPullData)
class AssemblyPullDataAdmin(admin.ModelAdmin):
    list_display = ['sequence', 'vehicle_model', 'color', 'planned_time', 'import_batch']
    list_filter = ['vehicle_model', 'color', 'import_batch']
    search_fields = ['vehicle_model__name', 'color__name']


@admin.register(SystemParameter)
class SystemParameterAdmin(admin.ModelAdmin):
    list_display = ['param_key', 'param_value', 'description', 'updated_at']
    list_editable = ['param_value']
