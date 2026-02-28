"""
Views for schedule calculation and result display.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.db.models import Q, Sum
from .models import ScheduleRecord, DemandRecord, RiskRecord, SchedulePlan, FormationSlot
from .services.algorithms import SchedulingAlgorithm
from data.models import SystemParameter


def calculate_view(request):
    """
    Display calculation form and trigger calculation
    """
    if request.method == 'POST':
        try:
            # Get parameters from form or use system defaults
            short_term_duration = int(request.POST.get('short_term_duration', 30))
            long_term_duration = int(request.POST.get('long_term_duration', 120))

            # Load system parameters
            params = SystemParameter.objects.all()
            param_dict = {p.param_key: p for p in params}

            # Create schedule record
            record = ScheduleRecord.objects.create(
                short_term_duration=short_term_duration,
                long_term_duration=long_term_duration,
                status='pending',
                cycle_time_min=param_dict.get('CYCLE_TIME_MIN', 90).get_int_value() if param_dict.get('CYCLE_TIME_MIN') else 90,
                avg_hanging_count=param_dict.get('AVG_HANGING_COUNT', 6).get_int_value() if param_dict.get('AVG_HANGING_COUNT') else 6,
                total_vehicles_in_line=param_dict.get('TOTAL_VEHICLES', 45).get_int_value() if param_dict.get('TOTAL_VEHICLES') else 45,
                short_term_capacity=param_dict.get('SHORT_TERM_CAPACITY', 80).get_float_value() if param_dict.get('SHORT_TERM_CAPACITY') else 80.0,
                long_term_capacity=param_dict.get('LONG_TERM_CAPACITY', 60).get_float_value() if param_dict.get('LONG_TERM_CAPACITY') else 60.0,
                front_rear_balance_d=param_dict.get('FRONT_REAR_BALANCE_D', 3).get_int_value() if param_dict.get('FRONT_REAR_BALANCE_D') else 3,
                group_capacity_limit=param_dict.get('GROUP_CAPACITY_LIMIT', 15).get_float_value() if param_dict.get('GROUP_CAPACITY_LIMIT') else 15.0,
                total_vehicles=param_dict.get('TOTAL_VEHICLES', 45).get_int_value() if param_dict.get('TOTAL_VEHICLES') else 45
            )

            # Run calculation
            algorithm = SchedulingAlgorithm()
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
        params = SystemParameter.objects.all()
        param_dict = {}
        for p in params:
            if 'CAPACITY' in p.param_key:
                param_dict[p.param_key] = p.get_float_value()
            else:
                param_dict[p.param_key] = p.get_int_value()
    except:
        param_dict = {}

    context = {
        'short_term_duration': param_dict.get('CYCLE_TIME_MIN', 90),
        'long_term_duration': param_dict.get('CYCLE_TIME_MIN', 90) * 4,
        'total_vehicles': param_dict.get('TOTAL_VEHICLES', 45),
        'short_term_capacity': param_dict.get('SHORT_TERM_CAPACITY', 80),
        'long_term_capacity': param_dict.get('LONG_TERM_CAPACITY', 60),
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

    formation_slots = record.formation_slots.all().select_related(
        'product__vehicle_model', 'product__color', 'product__position_type'
    ).order_by('slot_number')

    # Calculate summary statistics
    short_total_demand = short_demands.aggregate(Sum('demand_quantity'))['demand_quantity__sum'] or 0
    short_total_production = short_demands.aggregate(Sum('production_quantity'))['production_quantity__sum'] or 0
    long_total_demand = long_demands.aggregate(Sum('demand_quantity'))['demand_quantity__sum'] or 0
    long_total_production = long_demands.aggregate(Sum('production_quantity'))['production_quantity__sum'] or 0

    short_total_vehicles = short_plans.aggregate(Sum('vehicle_count'))['vehicle_count__sum'] or 0
    long_total_vehicles = long_plans.aggregate(Sum('vehicle_count'))['vehicle_count__sum'] or 0

    context = {
        'record': record,
        'short_demands': short_demands,
        'long_demands': long_demands,
        'short_risks': short_risks,
        'long_risks': long_risks,
        'short_plans': short_plans,
        'long_plans': long_plans,
        'formation_slots': formation_slots,
        'short_total_demand': short_total_demand,
        'short_total_production': short_total_production,
        'long_total_demand': long_total_demand,
        'long_total_production': long_total_production,
        'short_total_vehicles': short_total_vehicles,
        'long_total_vehicles': long_total_vehicles,
    }

    return render(request, 'schedule/result.html', context)


def history_list_view(request):
    """
    List all calculation records
    """
    records = ScheduleRecord.objects.all().order_by('-record_time')

    # Add summary data to each record
    for record in records:
        short_vehicles = record.plans.filter(plan_type='short').aggregate(
            Sum('vehicle_count'))['vehicle_count__sum'] or 0
        long_vehicles = record.plans.filter(plan_type='long').aggregate(
            Sum('vehicle_count'))['vehicle_count__sum'] or 0
        record.short_vehicles = short_vehicles
        record.long_vehicles = long_vehicles
        record.total_vehicles_used = short_vehicles + long_vehicles

    context = {
        'records': records,
    }

    return render(request, 'schedule/history.html', context)
