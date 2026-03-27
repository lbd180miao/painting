"""
Excel export utilities for schedule results.
"""
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from django.http import HttpResponse
from .models import (
    ScheduleRecord,
    DemandRecord,
    RiskRecord,
    SchedulePlan,
    FormationSlot,
    InventorySnapshot,
)


def build_injection_constraint_items(record, prefetched_risks=None, prefetched_plans=None):
    """Build injection constraint details from saved plans and risks.

    Args:
        record: ScheduleRecord instance.
        prefetched_risks: Optional pre-fetched list of RiskRecord objects for this record
            (with product select_related). When provided, no DB query is issued.
        prefetched_plans: Optional pre-fetched list of SchedulePlan objects for this record
            (with product select_related). When provided, no DB query is issued.
    """
    if prefetched_risks is not None:
        short_risks = [r for r in prefetched_risks if r.risk_type == 'short']
        long_risks = [r for r in prefetched_risks if r.risk_type == 'long']
    else:
        short_risks = list(RiskRecord.objects.filter(
            record=record,
            risk_type='short',
        ).select_related('product__vehicle_model', 'product__color', 'product__position_type'))
        long_risks = list(RiskRecord.objects.filter(
            record=record,
            risk_type='long',
        ).select_related('product__vehicle_model', 'product__color', 'product__position_type'))

    if prefetched_plans is not None:
        plan_records = prefetched_plans
    else:
        plan_records = list(SchedulePlan.objects.filter(
            record=record,
        ).select_related('product__vehicle_model', 'product__color', 'product__position_type'))

    short_risk_map = {risk.product_id: risk for risk in short_risks}
    long_risk_map = {risk.product_id: risk for risk in long_risks}
    items = []

    for plan in plan_records:
        if '受注塑库存限制' not in (plan.note or ''):
            continue

        if plan.plan_type == 'short':
            risk = short_risk_map.get(plan.product_id)
            needed_vehicles = 0
            if risk and risk.final_value < 0:
                needed_vehicles = (
                    abs(risk.final_value) + plan.product.hanging_count_per_vehicle - 1
                ) // plan.product.hanging_count_per_vehicle
            phase_label = '短期'
        else:
            risk = long_risk_map.get(plan.product_id)
            needed_vehicles = 0
            if risk and (risk.risk_value or 0) > 0:
                needed_vehicles = (
                    (risk.risk_value or 0) + plan.product.hanging_count_per_vehicle - 1
                ) // plan.product.hanging_count_per_vehicle
            phase_label = '长期'

        constrained_vehicles = max(needed_vehicles - plan.vehicle_count, 0)
        items.append({
            'phase_label': phase_label,
            'product': plan.product,
            'needed_vehicles': needed_vehicles,
            'allocated_vehicles': plan.vehicle_count,
            'constrained_vehicles': constrained_vehicles,
            'note': plan.note or '',
        })

    items.sort(
        key=lambda item: (
            0 if item['phase_label'] == '短期' else 1,
            -item['constrained_vehicles'],
            item['product'].vehicle_model.name,
            item['product'].color.display_name,
            item['product'].position_type.name,
        )
    )
    return items


def build_injection_constraint_metrics(record, prefetched_risks=None, prefetched_plans=None):
    """Return summary metrics and detail items for injection constraints."""
    items = build_injection_constraint_items(
        record,
        prefetched_risks=prefetched_risks,
        prefetched_plans=prefetched_plans,
    )
    phase_breakdown = {
        'short': {'count': 0, 'vehicle_loss': 0},
        'long': {'count': 0, 'vehicle_loss': 0},
    }
    for item in items:
        phase_key = 'short' if item['phase_label'] == '短期' else 'long'
        phase_breakdown[phase_key]['count'] += 1
        phase_breakdown[phase_key]['vehicle_loss'] += item['constrained_vehicles']
    return {
        'items': items,
        'count': len(items),
        'vehicle_loss': sum(item['constrained_vehicles'] for item in items),
        'phase_breakdown': phase_breakdown,
    }


def build_plan_gap_items(record, prefetched_risks=None, prefetched_plans=None):
    """Build unmet plan demand details from saved risks and plans.

    Args:
        record: ScheduleRecord instance.
        prefetched_risks: Optional pre-fetched list of RiskRecord objects for this record.
        prefetched_plans: Optional pre-fetched list of SchedulePlan objects for this record.
    """
    if prefetched_risks is not None:
        short_risks = [r for r in prefetched_risks if r.risk_type == 'short']
        long_risks = [r for r in prefetched_risks if r.risk_type == 'long']
    else:
        short_risks = list(RiskRecord.objects.filter(
            record=record,
            risk_type='short',
        ).select_related('product__vehicle_model', 'product__color', 'product__position_type'))
        long_risks = list(RiskRecord.objects.filter(
            record=record,
            risk_type='long',
        ).select_related('product__vehicle_model', 'product__color', 'product__position_type'))

    if prefetched_plans is not None:
        plan_records = prefetched_plans
    else:
        plan_records = list(SchedulePlan.objects.filter(
            record=record,
        ).select_related('product__vehicle_model', 'product__color', 'product__position_type'))

    plan_map = {
        (plan.plan_type, plan.product_id): plan
        for plan in plan_records
    }
    items = []

    for risk in short_risks:
        if risk.final_value >= 0:
            continue
        plan = plan_map.get(('short', risk.product_id))
        needed_vehicles = (
            abs(risk.final_value) + risk.product.hanging_count_per_vehicle - 1
        ) // risk.product.hanging_count_per_vehicle
        allocated = plan.vehicle_count if plan else 0
        gap = max(needed_vehicles - allocated, 0)
        if gap <= 0:
            continue
        items.append({
            'phase_label': '短期',
            'product': risk.product,
            'needed_vehicles': needed_vehicles,
            'allocated_vehicles': allocated,
            'gap_vehicles': gap,
            'unmet_quantity': abs(risk.final_value),
            'reason': (plan.note or '未生成计划') if plan else '未生成计划',
        })

    for risk in long_risks:
        if (risk.risk_value or 0) <= 0:
            continue
        plan = plan_map.get(('long', risk.product_id))
        needed_vehicles = (
            (risk.risk_value or 0) + risk.product.hanging_count_per_vehicle - 1
        ) // risk.product.hanging_count_per_vehicle
        allocated = plan.vehicle_count if plan else 0
        gap = max(needed_vehicles - allocated, 0)
        if gap <= 0:
            continue
        items.append({
            'phase_label': '长期',
            'product': risk.product,
            'needed_vehicles': needed_vehicles,
            'allocated_vehicles': allocated,
            'gap_vehicles': gap,
            'unmet_quantity': risk.risk_value or 0,
            'reason': (plan.note or '未生成计划') if plan else '未生成计划',
        })

    items.sort(
        key=lambda item: (
            0 if item['phase_label'] == '短期' else 1,
            -item['gap_vehicles'],
            item['product'].vehicle_model.name,
            item['product'].color.display_name,
            item['product'].position_type.name,
        )
    )
    return items


def build_plan_gap_metrics(record, prefetched_risks=None, prefetched_plans=None):
    """Return summary metrics and detail items for unmet plan gaps."""
    items = build_plan_gap_items(
        record,
        prefetched_risks=prefetched_risks,
        prefetched_plans=prefetched_plans,
    )
    return {
        'items': items,
        'count': len(items),
        'gap_vehicles': sum(item['gap_vehicles'] for item in items),
    }


def export_schedule_to_excel(record_id):
    """
    Export schedule calculation results to Excel file.

    Args:
        record_id: ScheduleRecord ID to export

    Returns:
        HttpResponse with Excel file
    """
    record = ScheduleRecord.objects.get(id=record_id)

    # Create Excel writer
    output = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    output['Content-Disposition'] = f'attachment; filename="schedule_result_{record.id}.xlsx"'

    # Create workbook
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Sheet 1: Summary
        _write_summary_sheet(writer, record)

        # Sheet 2: Short-term Demand
        _write_demand_sheet(writer, record, 'short')

        # Sheet 3: Long-term Demand
        _write_demand_sheet(writer, record, 'long')

        # Sheet 4: Short-term Risk
        _write_risk_sheet(writer, record, 'short')

        # Sheet 5: Long-term Risk
        _write_risk_sheet(writer, record, 'long')

        # Sheet 6: Short-term Plan
        _write_plan_sheet(writer, record, 'short')

        # Sheet 7: Long-term Plan
        _write_plan_sheet(writer, record, 'long')

        # Sheet 8: Formation Slots
        _write_formation_sheet(writer, record)

        # Sheet 9-10: Inventory snapshots
        _write_inventory_sheet(writer, record, 'paint')
        _write_inventory_sheet(writer, record, 'injection')

        # Sheet 11: Injection constraint summary
        _write_injection_constraint_sheet(writer, record)

        # Sheet 12: Plan gap summary
        _write_plan_gap_sheet(writer, record)

    # Apply styling
    workbook = writer.book
    _apply_styling(workbook)

    return output


def _write_summary_sheet(writer, record):
    """Write summary sheet."""
    injection_metrics = build_injection_constraint_metrics(record)
    gap_metrics = build_plan_gap_metrics(record)
    data = {
        '项目': ['记录ID', '计算时间', '状态', '短期时长(分钟)', '长期时长(分钟)', '总车数',
                '涂装一圈时间(分钟)', '每车平均挂数', '涂装线一圈车数',
                '短期产能百分比', '长期产能百分比', '前后平衡约束差值', '组车数平衡约束',
                '注塑受限物料数', '注塑截断车数', '短期注塑受限', '短期注塑截断车数', '长期注塑受限', '长期注塑截断车数',
                '计划缺口物料数', '计划缺口车数'],
        '值': [
            record.id,
            record.record_time.strftime('%Y-%m-%d %H:%M:%S'),
            record.get_status_display(),
            record.short_term_duration,
            record.long_term_duration,
            record.total_vehicles,
            record.cycle_time_min,
            record.avg_hanging_count,
            record.total_vehicles_in_line,
            f"{record.short_term_capacity:.1f}%",
            f"{record.long_term_capacity:.1f}%",
            record.front_rear_balance_d,
            f"{record.group_capacity_limit:.1f}%",
            injection_metrics['count'],
            injection_metrics['vehicle_loss'],
            injection_metrics['phase_breakdown']['short']['count'],
            injection_metrics['phase_breakdown']['short']['vehicle_loss'],
            injection_metrics['phase_breakdown']['long']['count'],
            injection_metrics['phase_breakdown']['long']['vehicle_loss'],
            gap_metrics['count'],
            gap_metrics['gap_vehicles'],
        ]
    }

    df = pd.DataFrame(data)
    df.to_excel(writer, sheet_name='计算摘要', index=False)


def _write_demand_sheet(writer, record, demand_type):
    """Write demand sheet."""
    demand_records = DemandRecord.objects.filter(
        record=record,
        demand_type=demand_type
    ).select_related('product__vehicle_model', 'product__color', 'product__position_type')

    data = []
    for dr in demand_records:
        data.append({
            '车型': dr.product.vehicle_model.name,
            '颜色': dr.product.color.display_name,
            '位置': dr.product.position_type.get_name_display(),
            '需求数量(台)': dr.demand_quantity,
            '生产数量(台)': dr.production_quantity
        })

    df = pd.DataFrame(
        data,
        columns=['车型', '颜色', '位置', '需求数量(台)', '生产数量(台)']
    )
    sheet_name = '短期需求' if demand_type == 'short' else '长期需求'
    df.to_excel(writer, sheet_name=sheet_name, index=False)


def _write_risk_sheet(writer, record, risk_type):
    """Write risk sheet."""
    risk_records = RiskRecord.objects.filter(
        record=record,
        risk_type=risk_type
    ).select_related('product__vehicle_model', 'product__color', 'product__position_type').order_by('rank')

    data = []
    for rr in risk_records:
        data.append({
            '排名': rr.rank or '',
            '车型': rr.product.vehicle_model.name,
            '颜色': rr.product.color.display_name,
            '位置': rr.product.position_type.get_name_display(),
            '终值': rr.final_value,
            '安全库存': rr.safety_stock,
            '风险值': rr.risk_value if rr.risk_type == 'long' else '',
            '组风险值': rr.group_risk_value if rr.risk_type == 'long' else ''
        })

    df = pd.DataFrame(
        data,
        columns=['排名', '车型', '颜色', '位置', '终值', '安全库存', '风险值', '组风险值']
    )
    sheet_name = '短期风险' if risk_type == 'short' else '长期风险'
    df.to_excel(writer, sheet_name=sheet_name, index=False)


def _write_plan_sheet(writer, record, plan_type):
    """Write plan sheet."""
    plan_records = SchedulePlan.objects.filter(
        record=record,
        plan_type=plan_type
    ).select_related('product__vehicle_model', 'product__color', 'product__position_type')

    data = []
    for pr in plan_records:
        data.append({
            '车型': pr.product.vehicle_model.name,
            '颜色': pr.product.color.display_name,
            '位置': pr.product.position_type.get_name_display(),
            '计划说明': pr.note,
            '生产车数': pr.vehicle_count
        })

    df = pd.DataFrame(
        data,
        columns=['车型', '颜色', '位置', '计划说明', '生产车数']
    )
    sheet_name = '短期计划' if plan_type == 'short' else '长期计划'
    df.to_excel(writer, sheet_name=sheet_name, index=False)


def _write_formation_sheet(writer, record):
    """Write formation slots sheet."""
    slots = FormationSlot.objects.filter(
        record=record
    ).select_related('product__vehicle_model', 'product__color', 'product__position_type').order_by('slot_number')

    data = []
    for slot in slots:
        if slot.product:
            data.append({
                '槽位号': slot.slot_number,
                '车型': slot.product.vehicle_model.name,
                '颜色': slot.product.color.display_name,
                '位置': slot.product.position_type.get_name_display(),
                '计划类型': '短期' if slot.plan_type == 'short' else '长期',
                '是否复用上一轮': '是' if slot.is_reused else '否',
            })
        else:
            data.append({
                '槽位号': slot.slot_number,
                '车型': '',
                '颜色': '',
                '位置': '',
                '计划类型': '',
                '是否复用上一轮': '',
            })

    df = pd.DataFrame(
        data,
        columns=['槽位号', '车型', '颜色', '位置', '计划类型', '是否复用上一轮']
    )
    df.to_excel(writer, sheet_name='阵型排布', index=False)


def _write_inventory_sheet(writer, record, inventory_type):
    """Write inventory snapshots sheet."""
    snapshots = InventorySnapshot.objects.filter(
        record=record,
        inventory_type=inventory_type,
    ).select_related('product__vehicle_model', 'product__color', 'product__position_type')

    data = []
    for snapshot in snapshots:
        data.append({
            '车型': snapshot.product.vehicle_model.name,
            '颜色': snapshot.product.color.display_name,
            '位置': snapshot.product.position_type.get_name_display(),
            '计算前': snapshot.current_quantity,
            '变动': snapshot.delta_quantity,
            '更新后': snapshot.updated_quantity,
        })

    df = pd.DataFrame(
        data,
        columns=['车型', '颜色', '位置', '计算前', '变动', '更新后']
    )
    sheet_name = '涂装库存更新' if inventory_type == 'paint' else '注塑库存更新'
    df.to_excel(writer, sheet_name=sheet_name, index=False)


def _write_injection_constraint_sheet(writer, record):
    """Write injection constraint detail sheet."""
    metrics = build_injection_constraint_metrics(record)
    data = []
    for item in metrics['items']:
        data.append({
            '阶段': item['phase_label'],
            '车型': item['product'].vehicle_model.name,
            '颜色': item['product'].color.display_name,
            '位置': item['product'].position_type.get_name_display(),
            '需要车数': item['needed_vehicles'],
            '实际分配': item['allocated_vehicles'],
            '截断车数': item['constrained_vehicles'],
            '说明': item['note'],
        })

    df = pd.DataFrame(
        data,
        columns=['阶段', '车型', '颜色', '位置', '需要车数', '实际分配', '截断车数', '说明']
    )
    df.to_excel(writer, sheet_name='注塑约束', index=False)


def _write_plan_gap_sheet(writer, record):
    """Write unmet plan gap detail sheet."""
    metrics = build_plan_gap_metrics(record)
    data = []
    for item in metrics['items']:
        data.append({
            '阶段': item['phase_label'],
            '车型': item['product'].vehicle_model.name,
            '颜色': item['product'].color.display_name,
            '位置': item['product'].position_type.get_name_display(),
            '需要车数': item['needed_vehicles'],
            '实际分配': item['allocated_vehicles'],
            '缺口车数': item['gap_vehicles'],
            '未满足需求': item['unmet_quantity'],
            '原因': item['reason'],
        })

    df = pd.DataFrame(
        data,
        columns=['阶段', '车型', '颜色', '位置', '需要车数', '实际分配', '缺口车数', '未满足需求', '原因']
    )
    df.to_excel(writer, sheet_name='计划缺口', index=False)


def _apply_styling(workbook):
    """Apply styling to all sheets."""
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    header_font_white = Font(bold=True, size=11, color='FFFFFF')

    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    for sheet in workbook.worksheets:
        # Apply header styling
        for cell in sheet[1]:
            cell.font = header_font_white
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border

        # Auto-adjust column widths
        for column in sheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            sheet.column_dimensions[column_letter].width = adjusted_width
