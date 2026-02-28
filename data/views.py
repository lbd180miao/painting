"""
Views for data management app.
"""
import os
from datetime import datetime, timedelta
import pandas as pd
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from django.conf import settings
from django.utils import timezone

from .models import (
    VehicleModel, Color, PositionType, Product,
    Inventory, InjectionInventory, SafetyStock, AssemblyPullData
)


def import_data(request):
    """数据导入页面"""
    if request.method == 'POST':
        import_type = request.POST.get('import_type')
        file = request.FILES.get('file')

        if not file:
            messages.error(request, '请选择要上传的文件')
            return render(request, 'data/import.html')

        if not file.name.endswith(('.xlsx', '.xls')):
            messages.error(request, '只支持Excel文件格式(.xlsx, .xls)')
            return render(request, 'data/import.html')

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
                return render(request, 'data/import.html')

            # 删除临时文件
            if os.path.exists(temp_path):
                os.remove(temp_path)

            if result['success']:
                messages.success(request, result['message'])
            else:
                messages.error(request, result['message'])

        except Exception as e:
            messages.error(request, f'导入失败: {str(e)}')

        return render(request, 'data/import.html')

    return render(request, 'data/import.html')


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
                return {
                    'success': False,
                    'message': f'Excel文件缺少必要列: {col}'
                }

        updated_count = 0
        for _, row in df.iterrows():
            material = str(row['物料']).strip()
            quantity = int(row['当前库存']) if pd.notna(row['当前库存']) else 0

            # 解析物料名称
            vehicle_model_name, position_str, color_name = _parse_material_info(material)

            if not vehicle_model_name or not color_name:
                continue

            # 获取或创建产品
            product = _get_or_create_product(vehicle_model_name, color_name, position_str)

            # 更新或创建库存
            inventory, created = Inventory.objects.get_or_create(
                product=product,
                defaults={
                    'current_quantity': quantity
                }
            )

            if not created:
                inventory.current_quantity = quantity
                inventory.updated_quantity = quantity
                inventory.update_time = timezone.now()
                inventory.save()

            updated_count += 1

        return {
            'success': True,
            'message': f'成功导入涂装库存数据，共{updated_count}条记录'
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'导入涂装库存数据失败: {str(e)}'
        }


def _import_injection_inventory(file_path):
    """导入注塑库存数据"""
    try:
        df = pd.read_excel(file_path)
        df = df.fillna('')

        # 验证列名（假设与涂装库存格式相同）
        expected_columns = ['物料', '当前库存']
        for col in expected_columns:
            if col not in df.columns:
                return {
                    'success': False,
                    'message': f'Excel文件缺少必要列: {col}'
                }

        updated_count = 0
        for _, row in df.iterrows():
            material = str(row['物料']).strip()
            quantity = int(row['当前库存']) if pd.notna(row['当前库存']) else 0

            # 解析物料名称
            vehicle_model_name, position_str, color_name = _parse_material_info(material)

            if not vehicle_model_name or not color_name:
                continue

            # 获取或创建产品
            product = _get_or_create_product(vehicle_model_name, color_name, position_str)

            # 更新或创建注塑库存
            inventory, created = InjectionInventory.objects.get_or_create(
                product=product,
                defaults={
                    'current_quantity': quantity
                }
            )

            if not created:
                inventory.current_quantity = quantity
                inventory.updated_quantity = quantity
                inventory.update_time = timezone.now()
                inventory.save()

            updated_count += 1

        return {
            'success': True,
            'message': f'成功导入注塑库存数据，共{updated_count}条记录'
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'导入注塑库存数据失败: {str(e)}'
        }


def _import_safety_stock(file_path):
    """导入安全库存数据"""
    try:
        df = pd.read_excel(file_path)
        df = df.fillna('')

        # 验证列名
        expected_columns = ['物料', '安全库存']
        for col in expected_columns:
            if col not in df.columns:
                return {
                    'success': False,
                    'message': f'Excel文件缺少必要列: {col}'
                }

        updated_count = 0
        for _, row in df.iterrows():
            material = str(row['物料']).strip()
            quantity = int(row['安全库存']) if pd.notna(row['安全库存']) else 0

            # 解析物料名称
            vehicle_model_name, position_str, color_name = _parse_material_info(material)

            if not vehicle_model_name or not color_name:
                continue

            # 获取或创建产品
            product = _get_or_create_product(vehicle_model_name, color_name, position_str)

            # 更新或创建安全库存
            safety_stock, created = SafetyStock.objects.get_or_create(
                product=product,
                defaults={
                    'quantity': quantity
                }
            )

            if not created:
                safety_stock.quantity = quantity
                safety_stock.save()

            updated_count += 1

        return {
            'success': True,
            'message': f'成功导入安全库存数据，共{updated_count}条记录'
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'导入安全库存数据失败: {str(e)}'
        }


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
                    return {
                        'success': False,
                        'message': f'Excel文件缺少必要列: {col}'
                    }

            # 生成导入批次标识
            import_batch = f"{timezone.now().strftime('%Y%m%d_%H%M%S')}"

            created_count = 0
            base_time = timezone.now()

            for _, row in df.iterrows():
                sequence = int(row['min']) if pd.notna(row['min']) else 0
                vehicle_model_name = str(row['产品名称']).strip()
                color_name = str(row['颜色']).strip()

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
                    sequence=sequence,
                    vehicle_model=vehicle_model,
                    color=color,
                    planned_time=planned_time,
                    import_batch=import_batch
                )

                created_count += 1

            return {
                'success': True,
                'message': f'成功导入总成拉动数据，共{created_count}条记录'
            }

    except Exception as e:
        return {
            'success': False,
            'message': f'导入总成拉动数据失败: {str(e)}'
        }


def inventory_list(request):
    """涂装库存列表"""
    inventories = Inventory.objects.select_related(
        'product__vehicle_model',
        'product__color',
        'product__position_type'
    ).all()
    return render(request, 'data/inventory_list.html', {
        'inventories': inventories
    })


def injection_list(request):
    """注塑库存列表"""
    inventories = InjectionInventory.objects.select_related(
        'product__vehicle_model',
        'product__color',
        'product__position_type'
    ).all()
    return render(request, 'data/injection_list.html', {
        'inventories': inventories
    })


def safety_list(request):
    """安全库存列表"""
    safety_stocks = SafetyStock.objects.select_related(
        'product__vehicle_model',
        'product__color',
        'product__position_type'
    ).all()
    return render(request, 'data/safety_list.html', {
        'safety_stocks': safety_stocks
    })


def assembly_list(request):
    """总成拉动数据列表"""
    assembly_data = AssemblyPullData.objects.select_related(
        'vehicle_model',
        'color'
    ).order_by('sequence')[:100]  # 只显示前100条
    return render(request, 'data/assembly_list.html', {
        'assembly_data': assembly_data
    })


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
