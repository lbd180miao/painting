"""
Views for data management app.
"""
import os
import csv
from datetime import datetime, timedelta
import pandas as pd
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.core.paginator import Paginator
from django.conf import settings
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.http import HttpResponse

from .forms import (
    AssemblyPullDataForm,
    ColorForm,
    InjectionInventoryForm,
    InventoryForm,
    ProductForm,
    SafetyStockForm,
    SystemParameterForm,
    VehicleModelForm,
)
from .models import (
    VehicleModel, Color, PositionType, Product,
    ImportRecord, Inventory, InjectionInventory, SafetyStock, AssemblyPullData
)


def _build_color_query(field_name, keyword):
    query = Q(**{f"{field_name}__icontains": keyword})
    normalized = keyword.strip().lower()
    mapped_names = [
        color_name for color_name, display in Color.DISPLAY_MAP.items()
        if display[0] == keyword or color_name == normalized
    ]
    if mapped_names:
        query |= Q(**{f"{field_name}__in": mapped_names})
    return query


def _build_delete_impacts(instance):
    if isinstance(instance, VehicleModel):
        return [
            ("产品", instance.products.count()),
            ("总成拉动", instance.assembly_data.count()),
        ]
    if isinstance(instance, Color):
        return [
            ("产品", instance.products.count()),
            ("总成拉动", instance.assembly_data.count()),
        ]
    if isinstance(instance, Product):
        return [
            ("涂装库存", 1 if hasattr(instance, "inventory") else 0),
            ("注塑库存", 1 if hasattr(instance, "injection_inventory") else 0),
            ("安全库存", 1 if hasattr(instance, "safety_stock") else 0),
        ]
    return []


def _paginate_queryset(request, queryset, per_page=10):
    paginator = Paginator(queryset, per_page)
    page_obj = paginator.get_page(request.GET.get("page") or 1)
    return page_obj


def _bulk_delete_view(request, model, redirect_name, object_label):
    if request.method != "POST":
        return redirect(redirect_name)
    selected_ids = request.POST.getlist("selected_ids")
    deleted_count = model.objects.filter(id__in=selected_ids).count()
    if deleted_count:
        model.objects.filter(id__in=selected_ids).delete()
        messages.success(request, f"已批量删除 {deleted_count} 条{object_label}")
    else:
        messages.warning(request, f"请选择要删除的{object_label}")
    next_url = _get_safe_next_url(request)
    return redirect(next_url or redirect_name)


def _get_safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return ""


def _filtered_inventory_queryset(request, model):
    queryset = model.objects.select_related(
        'product__vehicle_model',
        'product__color',
        'product__position_type'
    ).all()
    keyword = request.GET.get("q", "").strip()
    vehicle_id = request.GET.get("vehicle", "").strip()
    color_id = request.GET.get("color", "").strip()
    if keyword:
        queryset = queryset.filter(
            Q(product__vehicle_model__name__icontains=keyword)
            | _build_color_query("product__color__name", keyword)
        )
    if vehicle_id:
        queryset = queryset.filter(product__vehicle_model_id=vehicle_id)
    if color_id:
        queryset = queryset.filter(product__color_id=color_id)
    return queryset, {"q": keyword, "vehicle": vehicle_id, "color": color_id}


def _filtered_assembly_queryset(request):
    queryset = AssemblyPullData.objects.select_related(
        'vehicle_model',
        'color'
    ).order_by('sequence')
    keyword = request.GET.get("q", "").strip()
    vehicle_id = request.GET.get("vehicle", "").strip()
    color_id = request.GET.get("color", "").strip()
    import_batch = request.GET.get("import_batch", "").strip()
    if keyword:
        queryset = queryset.filter(
            Q(vehicle_model__name__icontains=keyword)
            | _build_color_query("color__name", keyword)
            | Q(import_batch__icontains=keyword)
        )
    if vehicle_id:
        queryset = queryset.filter(vehicle_model_id=vehicle_id)
    if color_id:
        queryset = queryset.filter(color_id=color_id)
    if import_batch:
        queryset = queryset.filter(import_batch__icontains=import_batch)
    return queryset, {
        "q": keyword,
        "vehicle": vehicle_id,
        "color": color_id,
        "import_batch": import_batch,
    }


def _csv_response(filename, headers, rows):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return response


def _build_import_result(success, message, updated_count=0, errors=None):
    errors = errors or []
    return {
        "success": success,
        "message": message,
        "updated_count": updated_count,
        "error_count": len(errors),
        "errors": errors,
    }


IMPORT_TEMPLATES = {
    "inventory": {
        "label": "涂装库存",
        "filename": "inventory-template.csv",
        "headers": ["物料", "当前库存"],
        "rows": [["A0front red", 12], ["A1rear blue", 8]],
    },
    "injection": {
        "label": "注塑库存",
        "filename": "injection-template.csv",
        "headers": ["物料", "当前库存"],
        "rows": [["A0front red", 20], ["A1rear blue", 16]],
    },
    "safety": {
        "label": "安全库存",
        "filename": "safety-template.csv",
        "headers": ["物料", "安全库存"],
        "rows": [["A0front red", 6], ["A1rear blue", 4]],
    },
    "assembly": {
        "label": "总成拉动",
        "filename": "assembly-template.csv",
        "headers": ["min", "产品名称", "颜色"],
        "rows": [[1, "A0", "red"], [2, "A1", "blue"]],
    },
}


def _record_import_result(import_type, file_name, result):
    error_count = result.get("error_count", 0)
    success_count = result.get("updated_count", 0)
    if result.get("success") and error_count:
        status = "partial"
    elif result.get("success"):
        status = "success"
    else:
        status = "failed"
    ImportRecord.objects.create(
        import_type=import_type,
        file_name=file_name,
        status=status,
        message=result.get("message", ""),
        success_count=success_count,
        error_count=error_count,
        error_details=result.get("errors", []),
    )


def _import_page_context():
    return {
        "template_options": [
            {"type": key, **value}
            for key, value in IMPORT_TEMPLATES.items()
        ],
        "recent_imports": ImportRecord.objects.all()[:10],
    }


def _filtered_import_record_queryset(request):
    queryset = ImportRecord.objects.all()
    keyword = request.GET.get("q", "").strip()
    import_type = request.GET.get("type", "").strip()
    status = request.GET.get("status", "").strip()
    if keyword:
        queryset = queryset.filter(
            Q(file_name__icontains=keyword)
            | Q(message__icontains=keyword)
        )
    if import_type:
        queryset = queryset.filter(import_type=import_type)
    if status:
        queryset = queryset.filter(status=status)
    return queryset, {"q": keyword, "type": import_type, "status": status}


def import_data(request):
    """数据导入页面"""
    context = _import_page_context()
    if request.method == 'POST':
        import_type = request.POST.get('import_type')
        file = request.FILES.get('file')

        if not file:
            messages.error(request, '请选择要上传的文件')
            return render(request, 'data/import.html', context)

        if not file.name.endswith(('.xlsx', '.xls')):
            messages.error(request, '只支持Excel文件格式(.xlsx, .xls)')
            return render(request, 'data/import.html', context)

        try:
            # 保存临时文件
            temp_path = os.path.join(settings.MEDIA_ROOT, 'temp', file.name)
            os.makedirs(os.path.dirname(temp_path), exist_ok=True)

            with open(temp_path, 'wb+') as destination:
                for chunk in file.chunks():
                    destination.write(chunk)

            # 根据导入类型处理
            if import_type == 'inventory':
                result = _import_painting_inventory(temp_path)
            elif import_type == 'injection':
                result = _import_injection_inventory(temp_path)
            elif import_type == 'safety':
                result = _import_safety_stock(temp_path)
            elif import_type == 'assembly':
                result = _import_assembly_pull_data(temp_path)
            else:
                messages.error(request, '无效的导入类型')
                return render(request, 'data/import.html', context)

            # 删除临时文件
            if os.path.exists(temp_path):
                os.remove(temp_path)

            if result['success']:
                messages.success(request, result['message'])
            else:
                messages.error(request, result['message'])
            _record_import_result(import_type, file.name, result)
            context["result"] = result
            context.update(_import_page_context())

        except Exception as e:
            messages.error(request, f'导入失败: {str(e)}')
            result = _build_import_result(
                False,
                f'导入失败: {str(e)}',
                errors=[{"row": "系统", "reason": str(e)}],
            )
            if import_type and file:
                _record_import_result(import_type, file.name, result)
            context["result"] = result
            context.update(_import_page_context())

        return render(request, 'data/import.html', context)

    return render(request, 'data/import.html', context)


def import_template_download(request, template_type):
    template = IMPORT_TEMPLATES.get(template_type)
    if not template:
        messages.error(request, "无效的模板类型")
        return redirect("data:import")
    return _csv_response(
        template["filename"],
        template["headers"],
        template["rows"],
    )


def import_history(request):
    records, filters = _filtered_import_record_queryset(request)
    page_obj = _paginate_queryset(request, records, per_page=15)
    filtered_records = page_obj.paginator.object_list
    failed_records = filtered_records.exclude(status="success")
    return render(request, "data/import_history.html", {
        "records": page_obj.object_list,
        "page_obj": page_obj,
        "filters": filters,
        "import_types": ImportRecord.IMPORT_TYPE_CHOICES,
        "status_choices": ImportRecord.STATUS_CHOICES,
        "summary": {
            "total_records": filtered_records.count(),
            "total_success_count": sum(item.success_count for item in filtered_records),
            "total_error_count": sum(item.error_count for item in filtered_records),
            "latest_failed_at": failed_records.first().created_at if failed_records.exists() else None,
        },
    })


def import_history_detail(request, pk):
    record = get_object_or_404(ImportRecord, pk=pk)
    return render(request, "data/import_history_detail.html", {
        "record": record,
    })


def import_history_export(request):
    records, _ = _filtered_import_record_queryset(request)
    rows = [
        [
            item.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            item.get_import_type_display(),
            item.file_name,
            item.get_status_display(),
            item.success_count,
            item.error_count,
            item.message,
        ]
        for item in records
    ]
    return _csv_response(
        "import-history-export.csv",
        ["时间", "导入类型", "文件名", "状态", "成功条数", "失败条数", "结果说明"],
        rows,
    )


def _parse_material_info(material_name):
    """解析物料名称，返回车型、位置类型、颜色"""
    material_name = material_name.strip()
    parts = material_name.split()

    if len(parts) < 2:
        return None, None, None

    # 第一部分包含车型和位置，例如 "A0front" 或 "A0rear"
    vehicle_position_part = parts[0]
    # 最后一部分是颜色
    color_name = parts[-1]

    # 判断前后位置并提取车型
    if 'front' in vehicle_position_part.lower():
        position_str = 'front'
        vehicle_model_str = vehicle_position_part.replace('front', '').replace('rear', '').strip()
    elif 'rear' in vehicle_position_part.lower():
        position_str = 'rear'
        vehicle_model_str = vehicle_position_part.replace('rear', '').replace('front', '').strip()
    else:
        position_str = 'front'
        vehicle_model_str = vehicle_position_part

    return vehicle_model_str, position_str, color_name


def _get_or_create_product(vehicle_model_name, color_name, position_str):
    """获取或创建产品"""
    # 获取或创建车型
    vehicle_model, _ = VehicleModel.objects.get_or_create(
        name=vehicle_model_name.strip(),
        defaults={'name': vehicle_model_name.strip()}
    )

    # 获取或创建颜色
    color, _ = Color.objects.get_or_create(
        name=color_name.strip(),
        defaults={'name': color_name.strip()}
    )

    # 获取或创建位置类型
    position_type, _ = PositionType.objects.get_or_create(
        name=position_str
    )

    # 获取或创建产品
    product, created = Product.objects.get_or_create(
        vehicle_model=vehicle_model,
        color=color,
        position_type=position_type,
        defaults={
            'hanging_count_per_vehicle': 4,
            'yield_rate': 80.00
        }
    )

    return product


def _import_painting_inventory(file_path):
    """导入涂装库存数据"""
    try:
        df = pd.read_excel(file_path)
        df = df.fillna('')  # 处理空值

        # 验证列名
        expected_columns = ['物料', '当前库存']
        for col in expected_columns:
            if col not in df.columns:
                return _build_import_result(
                    False,
                    f'Excel文件缺少必要列: {col}',
                    errors=[{"row": "表头", "reason": f"缺少必要列: {col}"}],
                )

        updated_count = 0
        errors = []
        for row_number, (_, row) in enumerate(df.iterrows(), start=2):
            material = str(row['物料']).strip()
            quantity = pd.to_numeric(row['当前库存'], errors='coerce')
            if pd.isna(quantity):
                errors.append({"row": f"第 {row_number} 行", "reason": "当前库存不是有效数字"})
                continue

            # 解析物料名称
            vehicle_model_name, position_str, color_name = _parse_material_info(material)

            if not vehicle_model_name or not color_name:
                errors.append({"row": f"第 {row_number} 行", "reason": "物料名称无法解析"})
                continue

            # 获取或创建产品
            product = _get_or_create_product(vehicle_model_name, color_name, position_str)

            # 更新或创建库存
            inventory, created = Inventory.objects.get_or_create(
                product=product,
                defaults={
                    'current_quantity': int(quantity)
                }
            )

            if not created:
                inventory.current_quantity = int(quantity)
                inventory.save()

            updated_count += 1

        success = updated_count > 0
        message = f'成功导入涂装库存数据，共{updated_count}条记录'
        if errors:
            message += f'，失败{len(errors)}条'
        return _build_import_result(success, message, updated_count, errors)

    except Exception as e:
        return _build_import_result(False, f'导入涂装库存数据失败: {str(e)}', errors=[{"row": "系统", "reason": str(e)}])


def _import_injection_inventory(file_path):
    """导入注塑库存数据"""
    try:
        df = pd.read_excel(file_path)
        df = df.fillna('')

        # 验证列名（假设与涂装库存格式相同）
        expected_columns = ['物料', '当前库存']
        for col in expected_columns:
            if col not in df.columns:
                return _build_import_result(
                    False,
                    f'Excel文件缺少必要列: {col}',
                    errors=[{"row": "表头", "reason": f"缺少必要列: {col}"}],
                )

        updated_count = 0
        errors = []
        for row_number, (_, row) in enumerate(df.iterrows(), start=2):
            material = str(row['物料']).strip()
            quantity = pd.to_numeric(row['当前库存'], errors='coerce')
            if pd.isna(quantity):
                errors.append({"row": f"第 {row_number} 行", "reason": "当前库存不是有效数字"})
                continue

            # 解析物料名称
            vehicle_model_name, position_str, color_name = _parse_material_info(material)

            if not vehicle_model_name or not color_name:
                errors.append({"row": f"第 {row_number} 行", "reason": "物料名称无法解析"})
                continue

            # 获取或创建产品
            product = _get_or_create_product(vehicle_model_name, color_name, position_str)

            # 更新或创建注塑库存
            inventory, created = InjectionInventory.objects.get_or_create(
                product=product,
                defaults={
                    'current_quantity': int(quantity)
                }
            )

            if not created:
                inventory.current_quantity = int(quantity)
                inventory.save()

            updated_count += 1

        success = updated_count > 0
        message = f'成功导入注塑库存数据，共{updated_count}条记录'
        if errors:
            message += f'，失败{len(errors)}条'
        return _build_import_result(success, message, updated_count, errors)

    except Exception as e:
        return _build_import_result(False, f'导入注塑库存数据失败: {str(e)}', errors=[{"row": "系统", "reason": str(e)}])


def _import_safety_stock(file_path):
    """导入安全库存数据"""
    try:
        df = pd.read_excel(file_path)
        df = df.fillna('')

        # 验证列名
        expected_columns = ['物料', '安全库存']
        for col in expected_columns:
            if col not in df.columns:
                return _build_import_result(
                    False,
                    f'Excel文件缺少必要列: {col}',
                    errors=[{"row": "表头", "reason": f"缺少必要列: {col}"}],
                )

        updated_count = 0
        errors = []
        for row_number, (_, row) in enumerate(df.iterrows(), start=2):
            material = str(row['物料']).strip()
            quantity = pd.to_numeric(row['安全库存'], errors='coerce')
            if pd.isna(quantity):
                errors.append({"row": f"第 {row_number} 行", "reason": "安全库存不是有效数字"})
                continue

            # 解析物料名称
            vehicle_model_name, position_str, color_name = _parse_material_info(material)

            if not vehicle_model_name or not color_name:
                errors.append({"row": f"第 {row_number} 行", "reason": "物料名称无法解析"})
                continue

            # 获取或创建产品
            product = _get_or_create_product(vehicle_model_name, color_name, position_str)

            # 更新或创建安全库存
            safety_stock, created = SafetyStock.objects.get_or_create(
                product=product,
                defaults={
                    'quantity': int(quantity)
                }
            )

            if not created:
                safety_stock.quantity = int(quantity)
                safety_stock.save()

            updated_count += 1

        success = updated_count > 0
        message = f'成功导入安全库存数据，共{updated_count}条记录'
        if errors:
            message += f'，失败{len(errors)}条'
        return _build_import_result(success, message, updated_count, errors)

    except Exception as e:
        return _build_import_result(False, f'导入安全库存数据失败: {str(e)}', errors=[{"row": "系统", "reason": str(e)}])


def _import_assembly_pull_data(file_path):
    """导入总成拉动数据"""
    try:
        with transaction.atomic():
            # 删除旧数据
            AssemblyPullData.objects.all().delete()

            df = pd.read_excel(file_path)
            df = df.fillna('')

            # 验证列名
            expected_columns = ['min', '产品名称', '颜色']
            for col in expected_columns:
                if col not in df.columns:
                    return _build_import_result(
                        False,
                        f'Excel文件缺少必要列: {col}',
                        errors=[{"row": "表头", "reason": f"缺少必要列: {col}"}],
                    )

            # 生成导入批次标识
            import_batch = f"{timezone.now().strftime('%Y%m%d_%H%M%S')}"

            created_count = 0
            base_time = timezone.now()
            errors = []

            for row_number, (_, row) in enumerate(df.iterrows(), start=2):
                sequence = pd.to_numeric(row['min'], errors='coerce')
                vehicle_model_name = str(row['产品名称']).strip()
                color_name = str(row['颜色']).strip()
                if pd.isna(sequence):
                    errors.append({"row": f"第 {row_number} 行", "reason": "min 不是有效数字"})
                    continue
                if not vehicle_model_name or not color_name:
                    errors.append({"row": f"第 {row_number} 行", "reason": "产品名称或颜色为空"})
                    continue

                # 获取或创建车型和颜色
                vehicle_model, _ = VehicleModel.objects.get_or_create(
                    name=vehicle_model_name,
                    defaults={'name': vehicle_model_name}
                )

                color, _ = Color.objects.get_or_create(
                    name=color_name,
                    defaults={'name': color_name}
                )

                # 计算计划时间（每分钟一个）
                planned_time = base_time + timedelta(minutes=sequence - 1)

                # 创建总成拉动数据
                AssemblyPullData.objects.create(
                    sequence=int(sequence),
                    vehicle_model=vehicle_model,
                    color=color,
                    planned_time=planned_time,
                    import_batch=import_batch
                )

                created_count += 1

            success = created_count > 0
            message = f'成功导入总成拉动数据，共{created_count}条记录'
            if errors:
                message += f'，失败{len(errors)}条'
            return _build_import_result(success, message, created_count, errors)

    except Exception as e:
        return _build_import_result(False, f'导入总成拉动数据失败: {str(e)}', errors=[{"row": "系统", "reason": str(e)}])


def inventory_list(request):
    """涂装库存列表"""
    inventories, filters = _filtered_inventory_queryset(request, Inventory)
    page_obj = _paginate_queryset(request, inventories)
    return render(request, 'data/inventory_list.html', {
        'inventories': page_obj.object_list,
        'page_obj': page_obj,
        'vehicles': VehicleModel.objects.all(),
        'colors': Color.objects.all(),
        'filters': filters,
    })


def inventory_bulk_delete(request):
    return _bulk_delete_view(request, Inventory, "data:inventory_list", "涂装库存")


def inventory_export(request):
    inventories, _ = _filtered_inventory_queryset(request, Inventory)
    rows = [
        [
            item.product.vehicle_model.name,
            item.product.color.display_name,
            item.product.position_type.get_name_display(),
            item.current_quantity,
        ]
        for item in inventories
    ]
    return _csv_response(
        "inventory-export.csv",
        ["车型", "颜色", "位置", "当前库存"],
        rows,
    )


def inventory_create(request):
    return _config_form_view(
        request,
        InventoryForm,
        "新增库存",
        "涂装库存已新增",
        "data:inventory_list",
    )


def inventory_update(request, pk):
    instance = get_object_or_404(Inventory, pk=pk)
    return _config_form_view(
        request,
        InventoryForm,
        "编辑涂装库存",
        "涂装库存已更新",
        "data:inventory_list",
        instance=instance,
    )


def inventory_delete(request, pk):
    return _config_delete_view(
        request,
        Inventory,
        pk,
        "涂装库存",
        "涂装库存已删除",
        "data:inventory_list",
    )


def injection_list(request):
    """注塑库存列表"""
    inventories, filters = _filtered_inventory_queryset(request, InjectionInventory)
    page_obj = _paginate_queryset(request, inventories)
    return render(request, 'data/injection_list.html', {
        'inventories': page_obj.object_list,
        'page_obj': page_obj,
        'vehicles': VehicleModel.objects.all(),
        'colors': Color.objects.all(),
        'filters': filters,
    })


def injection_bulk_delete(request):
    return _bulk_delete_view(request, InjectionInventory, "data:injection_list", "注塑库存")


def injection_export(request):
    inventories, _ = _filtered_inventory_queryset(request, InjectionInventory)
    rows = [
        [
            item.product.vehicle_model.name,
            item.product.color.display_name,
            item.product.position_type.get_name_display(),
            item.current_quantity,
        ]
        for item in inventories
    ]
    return _csv_response(
        "injection-export.csv",
        ["车型", "颜色", "位置", "当前库存"],
        rows,
    )


def injection_create(request):
    return _config_form_view(
        request,
        InjectionInventoryForm,
        "新增注塑库存",
        "注塑库存已新增",
        "data:injection_list",
    )


def injection_update(request, pk):
    instance = get_object_or_404(InjectionInventory, pk=pk)
    return _config_form_view(
        request,
        InjectionInventoryForm,
        "编辑注塑库存",
        "注塑库存已更新",
        "data:injection_list",
        instance=instance,
    )


def injection_delete(request, pk):
    return _config_delete_view(
        request,
        InjectionInventory,
        pk,
        "注塑库存",
        "注塑库存已删除",
        "data:injection_list",
    )


def safety_list(request):
    """安全库存列表"""
    safety_stocks, filters = _filtered_inventory_queryset(request, SafetyStock)
    page_obj = _paginate_queryset(request, safety_stocks)
    return render(request, 'data/safety_list.html', {
        'safety_stocks': page_obj.object_list,
        'page_obj': page_obj,
        'vehicles': VehicleModel.objects.all(),
        'colors': Color.objects.all(),
        'filters': filters,
    })


def safety_bulk_delete(request):
    return _bulk_delete_view(request, SafetyStock, "data:safety_list", "安全库存")


def safety_export(request):
    safety_stocks, _ = _filtered_inventory_queryset(request, SafetyStock)
    rows = [
        [
            item.product.vehicle_model.name,
            item.product.color.display_name,
            item.product.position_type.get_name_display(),
            item.quantity,
        ]
        for item in safety_stocks
    ]
    return _csv_response(
        "safety-export.csv",
        ["车型", "颜色", "位置", "安全库存"],
        rows,
    )


def safety_create(request):
    return _config_form_view(
        request,
        SafetyStockForm,
        "新增安全库存",
        "安全库存已新增",
        "data:safety_list",
    )


def safety_update(request, pk):
    instance = get_object_or_404(SafetyStock, pk=pk)
    return _config_form_view(
        request,
        SafetyStockForm,
        "编辑安全库存",
        "安全库存已更新",
        "data:safety_list",
        instance=instance,
    )


def safety_delete(request, pk):
    return _config_delete_view(
        request,
        SafetyStock,
        pk,
        "安全库存",
        "安全库存已删除",
        "data:safety_list",
    )


def assembly_list(request):
    """总成拉动数据列表"""
    per_page = 10
    assembly_data, filters = _filtered_assembly_queryset(request)

    next_item = None
    next_item_page = None
    consumed_count = 0
    # 只在无筛选、无手动指定页码时自动定位
    has_filters = any(filters.get(k) for k in ('q', 'vehicle', 'color', 'import_batch'))
    if not has_filters:
        # 计算已消费的总成拉动条数：
        # 每次排程执行后，算法从序列头部消费 short_term_duration + long_term_duration 条数据
        # 累加所有 completed（且未被回退）的排程记录
        from schedule.models import ScheduleRecord
        completed_records = ScheduleRecord.objects.filter(
            status='completed'
        ).values_list('short_term_duration', 'long_term_duration')
        for short_d, long_d in completed_records:
            consumed_count += (short_d or 0) + (long_d or 0)

        # 按 sequence 排序，取第 consumed_count+1 条（即下一条未被消费的数据）
        ordered_qs = AssemblyPullData.objects.order_by('sequence')
        total = ordered_qs.count()
        if consumed_count < total:
            # 使用 offset 取第 consumed_count 条（0-indexed）
            next_item = ordered_qs[consumed_count]
            # 计算该记录位于全量列表中的位置（1-indexed），用于分页计算
            position = consumed_count + 1
            next_item_page = (position - 1) // per_page + 1
        # 若已消费完（consumed_count >= total），则 next_item 为 None，不高亮

    # 若没有手动指定 page，且目标页 > 1（不在第1页时才需要跳转定位）
    if 'page' not in request.GET and next_item_page and next_item_page > 1:
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        return HttpResponseRedirect(
            reverse('data:assembly_list') + f'?page={next_item_page}'
        )

    page_obj = _paginate_queryset(request, assembly_data, per_page=per_page)
    return render(request, 'data/assembly_list.html', {
        'assembly_data': page_obj.object_list,
        'page_obj': page_obj,
        'vehicles': VehicleModel.objects.all(),
        'colors': Color.objects.all(),
        'filters': filters,
        'next_item_id': next_item.id if next_item else None,
        'consumed_count': consumed_count,
    })


def assembly_bulk_delete(request):
    return _bulk_delete_view(request, AssemblyPullData, "data:assembly_list", "总成拉动")


def assembly_export(request):
    assembly_data, _ = _filtered_assembly_queryset(request)
    rows = [
        [
            item.sequence,
            item.vehicle_model.name,
            item.color.display_name,
            item.planned_time.strftime("%Y-%m-%d %H:%M:%S"),
            item.import_batch,
        ]
        for item in assembly_data
    ]
    return _csv_response(
        "assembly-export.csv",
        ["序号", "车型", "颜色", "计划时间", "导入批次"],
        rows,
    )


def assembly_create(request):
    return _config_form_view(
        request,
        AssemblyPullDataForm,
        "新增总成拉动",
        "总成拉动数据已新增",
        "data:assembly_list",
    )


def assembly_update(request, pk):
    instance = get_object_or_404(AssemblyPullData, pk=pk)
    return _config_form_view(
        request,
        AssemblyPullDataForm,
        "编辑总成拉动",
        "总成拉动数据已更新",
        "data:assembly_list",
        instance=instance,
    )


def assembly_delete(request, pk):
    return _config_delete_view(
        request,
        AssemblyPullData,
        pk,
        "总成拉动",
        "总成拉动数据已删除",
        "data:assembly_list",
    )


def vehicle_list(request):
    """车型列表"""
    vehicles = VehicleModel.objects.all()
    return render(request, 'data/vehicle_list.html', {
        'vehicles': vehicles
    })


def color_list(request):
    """颜色列表"""
    colors = Color.objects.all()
    return render(request, 'data/color_list.html', {
        'colors': colors
    })


def product_list(request):
    """产品列表"""
    products = Product.objects.select_related(
        'vehicle_model',
        'color',
        'position_type'
    ).all()
    return render(request, 'data/product_list.html', {
        'products': products
    })


def parameter_list(request):
    """系统参数列表"""
    from .models import SystemParameter
    parameters = SystemParameter.objects.all()
    return render(request, 'data/parameter_list.html', {
        'parameters': parameters
    })


def _config_form_view(request, form_class, template_title, success_message, redirect_name, instance=None):
    if request.method == "POST":
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, success_message)
            next_url = _get_safe_next_url(request)
            return redirect(next_url or redirect_name)
    else:
        form = form_class(instance=instance)

    return render(request, "data/config_form.html", {
        "form": form,
        "page_title": template_title,
        "submit_label": "保存",
        "next_url": _get_safe_next_url(request),
    })


def _config_delete_view(request, model, pk, object_label, success_message, redirect_name):
    instance = get_object_or_404(model, pk=pk)
    if request.method == "POST":
        instance.delete()
        messages.success(request, success_message)
        next_url = _get_safe_next_url(request)
        return redirect(next_url or redirect_name)
    return render(request, "data/config_confirm_delete.html", {
        "page_title": f"删除{object_label}",
        "object_label": object_label,
        "object_display": str(instance),
        "impact_rows": _build_delete_impacts(instance),
        "next_url": _get_safe_next_url(request),
    })


def vehicle_create(request):
    return _config_form_view(
        request,
        VehicleModelForm,
        "新增车型",
        "车型已新增",
        "data:vehicles",
    )


def vehicle_update(request, pk):
    instance = get_object_or_404(VehicleModel, pk=pk)
    return _config_form_view(
        request,
        VehicleModelForm,
        "编辑车型",
        "车型已更新",
        "data:vehicles",
        instance=instance,
    )


def vehicle_delete(request, pk):
    return _config_delete_view(
        request,
        VehicleModel,
        pk,
        "车型",
        "车型已删除",
        "data:vehicles",
    )


def color_create(request):
    return _config_form_view(
        request,
        ColorForm,
        "新增颜色",
        "颜色已新增",
        "data:colors",
    )


def color_update(request, pk):
    instance = get_object_or_404(Color, pk=pk)
    return _config_form_view(
        request,
        ColorForm,
        "编辑颜色",
        "颜色已更新",
        "data:colors",
        instance=instance,
    )


def color_delete(request, pk):
    return _config_delete_view(
        request,
        Color,
        pk,
        "颜色",
        "颜色已删除",
        "data:colors",
    )


def product_create(request):
    return _config_form_view(
        request,
        ProductForm,
        "新增产品",
        "产品已新增",
        "data:products",
    )


def product_update(request, pk):
    instance = get_object_or_404(Product, pk=pk)
    return _config_form_view(
        request,
        ProductForm,
        "编辑产品",
        "产品已更新",
        "data:products",
        instance=instance,
    )


def product_delete(request, pk):
    return _config_delete_view(
        request,
        Product,
        pk,
        "产品",
        "产品已删除",
        "data:products",
    )


def parameter_update(request, pk):
    from .models import SystemParameter

    instance = get_object_or_404(SystemParameter, pk=pk)
    return _config_form_view(
        request,
        SystemParameterForm,
        "编辑系统参数",
        "系统参数已更新",
        "data:parameters",
        instance=instance,
    )
