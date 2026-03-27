"""
Views for schedule calculation and result display.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum, Prefetch
from .models import ScheduleRecord, DemandRecord, RiskRecord, SchedulePlan, FormationSlot, InventorySnapshot
from .services.algorithms import SchedulingAlgorithm
from .utils import build_injection_constraint_metrics, build_plan_gap_metrics
from data.models import SystemParameter, Inventory, InjectionInventory, SafetyStock, AssemblyPullData


def _load_parameter_values():
    params = SystemParameter.objects.all()
    param_dict = {}
    for p in params:
        if 'CAPACITY' in p.param_key or 'LIMIT' in p.param_key:
            param_dict[p.param_key] = p.get_float_value()
        else:
            param_dict[p.param_key] = p.get_int_value()
    return param_dict


def _recommended_duration_minutes(params, capacity_key):
    total = (
        params.get('TOTAL_VEHICLES', 100) *
        params.get('AVG_HANGING_COUNT', 4) *
        params.get(capacity_key, 0) / 100 / 2
    )
    return int(round(total + 0.499999))


def _build_calculate_preview():
    paint_inventories = list(Inventory.objects.select_related('product__vehicle_model', 'product__color', 'product__position_type'))
    injection_inventories = list(InjectionInventory.objects.select_related('product'))
    safety_map = {
        item.product_id: item.quantity
        for item in SafetyStock.objects.select_related('product')
    }

    below_safety_count = 0
    zero_or_negative_cover_count = 0
    for inventory in paint_inventories:
        current = inventory.current_quantity
        safety_quantity = safety_map.get(inventory.product_id, 0)
        if current < safety_quantity:
            below_safety_count += 1
        if current <= 0:
            zero_or_negative_cover_count += 1

    return {
        'assembly_count': AssemblyPullData.objects.count(),
        'paint_inventory_count': len(paint_inventories),
        'injection_inventory_count': len(injection_inventories),
        'below_safety_count': below_safety_count,
        'zero_or_negative_cover_count': zero_or_negative_cover_count,
    }


def calculate_view(request):
    """
    Display calculation form and trigger calculation
    """
    if request.method == 'POST':
        try:
            # Get parameters from form or use system defaults
            short_term_duration = int(request.POST.get('short_term_duration', 30))
            long_term_duration = int(request.POST.get('long_term_duration', 120))

            # Load system parameters safely
            params = SystemParameter.objects.all()
            param_dict = {p.param_key: p for p in params}

            def get_int(key, default):
                return param_dict[key].get_int_value() if key in param_dict else default

            def get_float(key, default):
                return param_dict[key].get_float_value() if key in param_dict else default

            # Create schedule record
            record = ScheduleRecord.objects.create(
                short_term_duration=short_term_duration,
                long_term_duration=long_term_duration,
                status='pending',
                cycle_time_min=get_int('CYCLE_TIME_MIN', 300),
                avg_hanging_count=get_int('AVG_HANGING_COUNT', 4),
                total_vehicles_in_line=get_int('TOTAL_VEHICLES', 100),
                short_term_capacity=get_float('SHORT_TERM_CAPACITY', 40.0),
                long_term_capacity=get_float('LONG_TERM_CAPACITY', 60.0),
                front_rear_balance_d=get_int('FRONT_REAR_BALANCE_D', 15),
                group_capacity_limit=get_float('GROUP_CAPACITY_LIMIT', 40.0),
                total_vehicles=get_int('TOTAL_VEHICLES', 100),
            )


            # Run calculation
            algorithm = SchedulingAlgorithm(
                short_term_duration=short_term_duration,
                long_term_duration=long_term_duration,
                record_time=record.record_time,
            )
            results = algorithm.calculate()

            # Save results
            with transaction.atomic():
                algorithm.save_results(results, record)

                # Update record status
                record.status = 'completed'
                record.save()

            messages.success(request, f'排产计算完成！记录ID: {record.id}')
            return redirect('schedule:result', id=record.id)

        except Exception as e:
            # Update record status to failed
            if 'record' in locals():
                record.status = 'failed'
                record.error_message = str(e)
                record.save()

            messages.error(request, f'计算失败: {str(e)}')

    # GET request - display form
    # Load default parameters
    try:
        param_dict = _load_parameter_values()
    except Exception:
        param_dict = {}

    recommended_short_duration = _recommended_duration_minutes(param_dict, 'SHORT_TERM_CAPACITY')
    recommended_long_duration = _recommended_duration_minutes(param_dict, 'LONG_TERM_CAPACITY')

    context = {
        'short_term_duration': recommended_short_duration or param_dict.get('CYCLE_TIME_MIN', 90),
        'long_term_duration': recommended_long_duration or param_dict.get('CYCLE_TIME_MIN', 90) * 4,
        'recommended_short_duration': recommended_short_duration,
        'recommended_long_duration': recommended_long_duration,
        'total_vehicles': param_dict.get('TOTAL_VEHICLES', 45),
        'short_term_capacity': param_dict.get('SHORT_TERM_CAPACITY', 40),
        'long_term_capacity': param_dict.get('LONG_TERM_CAPACITY', 60),
        'front_rear_balance_d': param_dict.get('FRONT_REAR_BALANCE_D', 15),
        'group_capacity_limit': param_dict.get('GROUP_CAPACITY_LIMIT', 40),
        'calculate_preview': _build_calculate_preview(),
    }

    return render(request, 'schedule/calculate.html', context)


def result_view(request, id):
    """
    Display calculation results (demand tables, risk tables, plans)
    """
    record = get_object_or_404(ScheduleRecord, id=id)

    # Get related data
    short_demands = record.demands.filter(demand_type='short').select_related(
        'product__vehicle_model', 'product__color', 'product__position_type'
    )
    long_demands = record.demands.filter(demand_type='long').select_related(
        'product__vehicle_model', 'product__color', 'product__position_type'
    )

    short_risks = record.risks.filter(risk_type='short').select_related(
        'product__vehicle_model', 'product__color', 'product__position_type'
    ).order_by('rank')
    long_risks = record.risks.filter(risk_type='long').select_related(
        'product__vehicle_model', 'product__color', 'product__position_type'
    ).order_by('rank')

    short_plans = record.plans.filter(plan_type='short').select_related(
        'product__vehicle_model', 'product__color', 'product__position_type'
    )
    long_plans = record.plans.filter(plan_type='long').select_related(
        'product__vehicle_model', 'product__color', 'product__position_type'
    )

    formation_slots = list(record.formation_slots.all().select_related(
        'product__vehicle_model', 'product__color', 'product__position_type'
    ).order_by('slot_number'))
    inventory_snapshots = record.inventory_snapshots.select_related(
        'product__vehicle_model', 'product__color', 'product__position_type'
    ).order_by('inventory_type', 'product__vehicle_model__name', 'product__color__name', 'product__position_type__name')
    paint_inventory_snapshots = [item for item in inventory_snapshots if item.inventory_type == 'paint']
    injection_inventory_snapshots = [item for item in inventory_snapshots if item.inventory_type == 'injection']

    # Calculate summary statistics
    short_total_demand = short_demands.aggregate(Sum('demand_quantity'))['demand_quantity__sum'] or 0
    short_total_production = short_demands.aggregate(Sum('production_quantity'))['production_quantity__sum'] or 0
    long_total_demand = long_demands.aggregate(Sum('demand_quantity'))['demand_quantity__sum'] or 0
    long_total_production = long_demands.aggregate(Sum('production_quantity'))['production_quantity__sum'] or 0

    short_total_vehicles = short_plans.aggregate(Sum('vehicle_count'))['vehicle_count__sum'] or 0
    long_total_vehicles = long_plans.aggregate(Sum('vehicle_count'))['vehicle_count__sum'] or 0
    short_shortage_count = short_risks.filter(final_value__lt=0).count()
    long_risk_group_count = len({
        f"{risk.product.vehicle_model.name} / {risk.product.color.name}"
        for risk in long_risks if (risk.group_risk_value or 0) > 0
    })
    long_risk_group_summaries = []
    group_summary_map = {}
    for risk in long_risks:
        group_key = f"{risk.product.vehicle_model.name} / {risk.product.color.display_name}"
        if group_key not in group_summary_map:
            group_summary_map[group_key] = {
                'group_label': group_key,
                'group_risk_value': risk.group_risk_value or 0,
                'positions': [],
            }
        group_summary_map[group_key]['group_risk_value'] = max(
            group_summary_map[group_key]['group_risk_value'],
            risk.group_risk_value or 0,
        )
        group_summary_map[group_key]['positions'].append({
            'position': risk.product.position_type.get_name_display(),
            'risk_value': risk.risk_value or 0,
        })

    for item in group_summary_map.values():
        if item['group_risk_value'] >= 5:
            risk_level = '高风险组'
        elif item['group_risk_value'] > 0:
            risk_level = '关注组'
        else:
            risk_level = '安全组'
        item['risk_level'] = risk_level
        long_risk_group_summaries.append(item)
    long_risk_group_summaries.sort(key=lambda item: item['group_risk_value'], reverse=True)
    slot_map = {slot.slot_number: slot for slot in formation_slots}
    full_formation_slots = []
    for slot_number in range(1, (record.total_vehicles or record.total_vehicles_in_line or 0) + 1):
        slot = slot_map.get(slot_number)
        if slot:
            full_formation_slots.append(slot)
            continue
        full_formation_slots.append({
            'slot_number': slot_number,
            'product': None,
            'plan_type': '',
            'is_reused': False,
        })
    vehicle_filter = request.GET.get('vehicle', '').strip()
    color_filter = request.GET.get('color', '').strip().lower()
    position_filter = request.GET.get('position', '').strip().lower()
    filtered_formation_slots = []
    for slot in full_formation_slots:
        product = getattr(slot, 'product', None) if not isinstance(slot, dict) else slot.get('product')
        if not product:
            if vehicle_filter or color_filter or position_filter:
                continue
            filtered_formation_slots.append(slot)
            continue
        if vehicle_filter and product.vehicle_model.name != vehicle_filter:
            continue
        if color_filter and product.color.name.lower() != color_filter:
            continue
        if position_filter and product.position_type.name.lower() != position_filter:
            continue
        filtered_formation_slots.append(slot)
    reused_slot_count = sum(1 for slot in full_formation_slots if getattr(slot, 'is_reused', False) or (isinstance(slot, dict) and slot.get('is_reused')))
    empty_slot_count = sum(1 for slot in full_formation_slots if (getattr(slot, 'product', None) is None if not isinstance(slot, dict) else slot.get('product') is None))
    injection_constraint_metrics = build_injection_constraint_metrics(record)
    plan_gap_metrics = build_plan_gap_metrics(record)

    context = {
        'record': record,
        'short_demands': short_demands,
        'long_demands': long_demands,
        'short_risks': short_risks,
        'long_risks': long_risks,
        'short_plans': short_plans,
        'long_plans': long_plans,
        'formation_slots': filtered_formation_slots,
        'formation_slot_total': len(filtered_formation_slots),
        'formation_filters': {
            'vehicle': vehicle_filter,
            'color': color_filter,
            'position': position_filter,
        },
        'short_total_demand': short_total_demand,
        'short_total_production': short_total_production,
        'long_total_demand': long_total_demand,
        'long_total_production': long_total_production,
        'short_total_vehicles': short_total_vehicles,
        'long_total_vehicles': long_total_vehicles,
        'short_shortage_count': short_shortage_count,
        'long_risk_group_count': long_risk_group_count,
        'long_risk_group_summaries': long_risk_group_summaries,
        'reused_slot_count': reused_slot_count,
        'empty_slot_count': empty_slot_count,
        'injection_constrained_count': injection_constraint_metrics['count'],
        'injection_constrained_vehicle_loss': injection_constraint_metrics['vehicle_loss'],
        'injection_constrained_items': injection_constraint_metrics['items'],
        'injection_constraint_phase_breakdown': injection_constraint_metrics['phase_breakdown'],
        'plan_gap_count': plan_gap_metrics['count'],
        'plan_gap_vehicle_loss': plan_gap_metrics['gap_vehicles'],
        'plan_gap_items': plan_gap_metrics['items'],
        'paint_inventory_snapshots': paint_inventory_snapshots,
        'injection_inventory_snapshots': injection_inventory_snapshots,
        'short_window': {
            'start': 1,
            'end': record.short_term_duration,
        },
        'long_window': {
            'start': record.short_term_duration + 1,
            'end': record.short_term_duration + record.long_term_duration,
        },
    }

    return render(request, 'schedule/result.html', context)


def history_list_view(request):
    """
    List all calculation records
    """
    _risks_qs = RiskRecord.objects.select_related(
        'product__vehicle_model', 'product__color', 'product__position_type'
    )
    _plans_qs = SchedulePlan.objects.select_related(
        'product__vehicle_model', 'product__color', 'product__position_type'
    )
    records = list(
        ScheduleRecord.objects.prefetch_related(
            Prefetch('risks', queryset=_risks_qs, to_attr='_prefetched_risks'),
            Prefetch('plans', queryset=_plans_qs, to_attr='_prefetched_plans'),
            'formation_slots',
            'inventory_snapshots',
            'demands',
        ).order_by('-record_time')
    )

    # Compute all per-record aggregates in Python from pre-fetched data
    for record in records:
        plans = record._prefetched_plans        # list, already select_related
        risks = record._prefetched_risks         # list, already select_related
        slots = list(record.formation_slots.all())
        snapshots = list(record.inventory_snapshots.all())
        demands = list(record.demands.all())

        record.short_vehicles = sum(p.vehicle_count for p in plans if p.plan_type == 'short')
        record.long_vehicles = sum(p.vehicle_count for p in plans if p.plan_type == 'long')
        record.reused_slots = sum(1 for s in slots if s.is_reused)
        record.total_vehicles_used = sum(1 for s in slots if s.product_id is not None)
        record.paint_delta = sum(s.delta_quantity for s in snapshots if s.inventory_type == 'paint')
        record.injection_delta = sum(s.delta_quantity for s in snapshots if s.inventory_type == 'injection')
        record.short_demand_total = sum(d.demand_quantity for d in demands if d.demand_type == 'short')
        record.long_demand_total = sum(d.demand_quantity for d in demands if d.demand_type == 'long')
        record.paint_snapshot_count = sum(1 for s in snapshots if s.inventory_type == 'paint')
        record.injection_snapshot_count = sum(1 for s in snapshots if s.inventory_type == 'injection')
        record.short_window_label = f"1-{record.short_term_duration}"
        record.long_window_label = (
            f"{record.short_term_duration + 1}-"
            f"{record.short_term_duration + record.long_term_duration}"
        )
        # Pass pre-fetched data — zero extra DB queries needed
        injection_constraint_metrics = build_injection_constraint_metrics(
            record,
            prefetched_risks=risks,
            prefetched_plans=plans,
        )
        record.injection_constrained_count = injection_constraint_metrics['count']
        record.injection_constrained_vehicle_loss = injection_constraint_metrics['vehicle_loss']
        plan_gap_metrics = build_plan_gap_metrics(
            record,
            prefetched_risks=risks,
            prefetched_plans=plans,
        )
        record.plan_gap_count = plan_gap_metrics['count']
        record.plan_gap_vehicle_loss = plan_gap_metrics['gap_vehicles']

    completed_count = sum(1 for r in records if r.status == 'completed')
    failed_count = sum(1 for r in records if r.status == 'failed')
    latest_completed = next((r for r in records if r.status == 'completed'), None)
    latest_completed_id = latest_completed.id if latest_completed else None
    latest_time = records[0].record_time if records else None
    total_injection_vehicle_loss = sum(r.injection_constrained_vehicle_loss for r in records)
    total_plan_gap_vehicle_loss = sum(r.plan_gap_vehicle_loss for r in records)
    latest_exception_record = next(
        (
            r for r in records
            if r.injection_constrained_vehicle_loss > 0 or r.plan_gap_vehicle_loss > 0
        ),
        None,
    )

    context = {
        'records': records,
        'completed_count': completed_count,
        'failed_count': failed_count,
        'latest_time': latest_time,
        'latest_completed_id': latest_completed_id,
        'total_injection_vehicle_loss': total_injection_vehicle_loss,
        'total_plan_gap_vehicle_loss': total_plan_gap_vehicle_loss,
        'latest_exception_record': latest_exception_record,
    }

    return render(request, 'schedule/history.html', context)


def history_delete_view(request, id):
    if request.method != "POST":
        return redirect('schedule:history')
    record = get_object_or_404(ScheduleRecord, id=id)
    record.delete()
    messages.success(request, '历史记录已删除')
    return redirect('schedule:history')


def export_to_excel_view(request, id):
    """
    Export schedule calculation results to Excel file
    """
    from .utils import export_schedule_to_excel

    return export_schedule_to_excel(id)


def history_rollback_view(request, id):
    """
    回退排产记录，恢复库存到该记录执行前的状态。
    只允许回退最新的已完成记录。
    """
    if request.method != 'POST':
        return redirect('schedule:history')

    record = get_object_or_404(ScheduleRecord, id=id)

    # 校验该记录是最新的已完成记录
    latest_completed = ScheduleRecord.objects.filter(status='completed').order_by('-record_time').first()
    if not latest_completed or latest_completed.id != record.id:
        messages.error(request, '只能回退最新的已完成记录')
        return redirect('schedule:history')

    try:
        with transaction.atomic():
            # 读取库存快照，逆向恢复库存
            snapshots = record.inventory_snapshots.select_related('product').all()
            for snapshot in snapshots:
                if snapshot.inventory_type == 'paint':
                    try:
                        inv = Inventory.objects.get(product=snapshot.product)
                        inv.current_quantity = snapshot.current_quantity
                        inv.save(update_fields=['current_quantity'])
                    except Inventory.DoesNotExist:
                        pass
                else:
                    try:
                        inv = InjectionInventory.objects.get(product=snapshot.product)
                        inv.current_quantity = snapshot.current_quantity
                        inv.save(update_fields=['current_quantity'])
                    except InjectionInventory.DoesNotExist:
                        pass

            # 更新记录状态
            record.status = 'rolled_back'
            record.save(update_fields=['status'])

        messages.success(request, f'排产记录 #{record.id} 已回退，库存已恢复')
    except Exception as e:
        messages.error(request, f'回退失败: {str(e)}')

    return redirect('schedule:history')
