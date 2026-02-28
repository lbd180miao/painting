"""
Excel export utilities for schedule results.
"""
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows
from django.http import HttpResponse
from .models import ScheduleRecord, DemandRecord, RiskRecord, SchedulePlan, FormationSlot


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

    # Apply styling
    workbook = writer.book
    _apply_styling(workbook)

    return output


def _write_summary_sheet(writer, record):
    """Write summary sheet."""
    data = {
        '项目': ['记录ID', '计算时间', '状态', '短期时长(分钟)', '长期时长(分钟)', '总车数',
                '涂装一圈时间(分钟)', '每车平均挂数', '涂装线一圈车数',
                '短期产能百分比', '长期产能百分比', '前后平衡约束差值', '组车数平衡约束'],
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
            f"{record.short_term_capacity * 100:.1f}%",
            f"{record.long_term_capacity * 100:.1f}%",
            record.front_rear_balance_d,
            f"{record.group_capacity_limit * 100:.1f}%"
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
            '颜色': dr.product.color.name,
            '位置': dr.product.get_position_type_display(),
            '需求数量(台)': dr.demand_quantity,
            '生产数量(台)': dr.production_quantity
        })

    df = pd.DataFrame(data)
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
            '颜色': rr.product.color.name,
            '位置': rr.product.get_position_type_display(),
            '终值': rr.final_value,
            '安全库存': rr.safety_stock,
            '风险值': rr.risk_value if rr.risk_type == 'long' else '',
            '组风险值': rr.group_risk_value if rr.risk_type == 'long' else ''
        })

    df = pd.DataFrame(data)
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
            '颜色': pr.product.color.name,
            '位置': pr.product.get_position_type_display(),
            '生产车数': pr.vehicle_count
        })

    df = pd.DataFrame(data)
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
                '颜色': slot.product.color.name,
                '位置': slot.product.get_position_type_display(),
                '计划类型': '短期' if slot.plan_type == 'short' else '长期'
            })
        else:
            data.append({
                '槽位号': slot.slot_number,
                '车型': '',
                '颜色': '',
                '位置': '',
                '计划类型': ''
            })

    df = pd.DataFrame(data)
    df.to_excel(writer, sheet_name='阵型排布', index=False)


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
