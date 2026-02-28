from django.contrib import admin
from .models import ScheduleRecord, DemandRecord, RiskRecord, SchedulePlan, FormationSlot


@admin.register(ScheduleRecord)
class ScheduleRecordAdmin(admin.ModelAdmin):
    """排产记录管理"""
    list_display = ['id', 'record_time', 'status', 'short_term_duration', 'long_term_duration', 'total_vehicles']
    list_filter = ['status', 'record_time']
    search_fields = ['id', 'error_message']
    readonly_fields = ['record_time']
    ordering = ['-record_time']

    fieldsets = (
        ('基本信息', {
            'fields': ('record_time', 'status', 'error_message')
        }),
        ('时间参数', {
            'fields': ('short_term_duration', 'long_term_duration')
        }),
        ('系统参数快照', {
            'fields': ('total_vehicles', 'cycle_time_min', 'avg_hanging_count',
                      'total_vehicles_in_line', 'short_term_capacity',
                      'long_term_capacity', 'front_rear_balance_d',
                      'group_capacity_limit')
        }),
    )


@admin.register(DemandRecord)
class DemandRecordAdmin(admin.ModelAdmin):
    """需求记录管理"""
    list_display = ['id', 'record', 'product', 'demand_type', 'demand_quantity', 'production_quantity']
    list_filter = ['demand_type', 'record']
    search_fields = ['product__vehicle_model__name', 'product__color__name']
    ordering = ['-record', 'demand_type']


@admin.register(RiskRecord)
class RiskRecordAdmin(admin.ModelAdmin):
    """风险记录管理"""
    list_display = ['id', 'record', 'product', 'risk_type', 'final_value', 'safety_stock',
                    'risk_value', 'group_risk_value', 'rank']
    list_filter = ['risk_type', 'record']
    search_fields = ['product__vehicle_model__name', 'product__color__name']
    ordering = ['record', 'risk_type', 'rank']


@admin.register(SchedulePlan)
class SchedulePlanAdmin(admin.ModelAdmin):
    """排产计划管理"""
    list_display = ['id', 'record', 'product', 'plan_type', 'vehicle_count']
    list_filter = ['plan_type', 'record']
    search_fields = ['product__vehicle_model__name', 'product__color__name']
    ordering = ['-record', 'plan_type']


@admin.register(FormationSlot)
class FormationSlotAdmin(admin.ModelAdmin):
    """阵型槽位管理"""
    list_display = ['id', 'record', 'slot_number', 'product', 'plan_type']
    list_filter = ['plan_type', 'record']
    search_fields = ['product__vehicle_model__name', 'product__color__name']
    ordering = ['record', 'slot_number']
