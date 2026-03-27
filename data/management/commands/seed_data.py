"""
数据填充管理命令 - seed_data
根据《涂装双层滚动排产标准决策流程》文档和真实 Excel 数据填充数据库

使用方法:
    python manage.py seed_data            # 填充数据（保留现有数据）
    python manage.py seed_data --reset    # 清空后重填
"""
import openpyxl
import openpyxl
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone



# ============================================================
# 1. 静态数据（直接从 Excel 提取，格式验证正确）
# ============================================================

# 涂装库存 (当前库存, 安全库存) - 来自 3.2涂装库存.xlsx
INVENTORY_DATA = {
    # 物料名           当前库存  安全库存
    'A0front red':   (80,   30),
    'A0rear red':    (40,   30),
    'A0front white': (50,   20),
    'A0rear white':  (20,   20),
    'A0front blue':  (40,   15),
    'A0rear blue':   (18,   15),
    'A0front black': (25,   10),
    'A0rear black':  (10,   10),
    'A1front red':   (60,   25),
    'A1rear red':    (25,   25),
    'A1front blue':  (70,   25),
    'A1rear blue':   (35,   25),
    'A1front white': (40,   20),
    'A1rear white':  (15,   20),
    'A1front black': (20,   10),
    'A1rear black':  ( 8,   10),
}

# 注塑库存（直接提取自 Excel 的注塑库存 Sheet）
INJECTION_INVENTORY_DATA = {
    'A0front': 2000,
    'A0rear':  2000,
    'A1front': 1600,
    'A1rear':  1600,
}

# 产品参数配置 - 严格按文档规范
# A0: 挂数=5, 合格率=80%; A1: 挂数=4, 合格率=90%
PRODUCT_CONFIG = {
    ('A0', 'front'): {'hanging_count': 5, 'yield_rate': 80.0},
    ('A0', 'rear'):  {'hanging_count': 5, 'yield_rate': 80.0},
    ('A1', 'front'): {'hanging_count': 4, 'yield_rate': 90.0},
    ('A1', 'rear'):  {'hanging_count': 4, 'yield_rate': 90.0},
}

# 系统参数默认值 - 按文档规范
SYSTEM_PARAMS = [
    ('CYCLE_TIME_MIN',       '300',   '涂装一圈到落库时间(分钟)，默认300min=5h'),
    ('AVG_HANGING_COUNT',    '4',     '每车平均挂数，默认4（开放窗口）'),
    ('TOTAL_VEHICLES',       '100',   '涂装线一圈一共多少台车，默认100（开放窗口）'),
    ('SHORT_TERM_CAPACITY',  '40',    '短期产能百分比A=40%（开放窗口）'),
    ('LONG_TERM_CAPACITY',   '60',    '长期产能百分比B=60%（开放窗口）'),
    ('FRONT_REAR_BALANCE_D', '15',    '前后平衡约束差值D，默认15'),
    ('GROUP_CAPACITY_LIMIT', '40',    '组车数平衡约束：同型号front+rear不超过长期产能的40%'),
    ('LONG_TERM_FORECAST_HOURS', '0', '长期需求预测时间(小时)，0=使用计算推荐值'),
]


class Command(BaseCommand):
    help = '填充涂装排产系统数据库（车型、颜色、产品、库存、总成拉动数据、系统参数）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='清空现有数据后重新填充',
        )
        parser.add_argument(
            '--excel',
            type=str,
            default=None,
            help='指定总成拉动数据 Excel 文件路径（默认自动查找 doc/ 目录）',
        )

    def handle(self, *args, **options):
        from data.models import (
            VehicleModel, Color, PositionType, Product,
            Inventory, InjectionInventory, SafetyStock,
            AssemblyPullData, SystemParameter
        )

        if options['reset']:
            self.stdout.write('🗑️  清空现有数据...')
            AssemblyPullData.objects.all().delete()
            Inventory.objects.all().delete()
            InjectionInventory.objects.all().delete()
            SafetyStock.objects.all().delete()
            Product.objects.all().delete()
            PositionType.objects.all().delete()
            Color.objects.all().delete()
            VehicleModel.objects.all().delete()
            SystemParameter.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('✅ 数据已清空'))

        # ── 1. 车型 ─────────────────────────────────────────
        self.stdout.write('📦 填充车型...')
        vehicle_models = {}
        for name in ['A0', 'A1']:
            vm, created = VehicleModel.objects.get_or_create(name=name)
            vehicle_models[name] = vm
            if created:
                self.stdout.write(f'   创建车型: {name}')
        self.stdout.write(self.style.SUCCESS(f'✅ 车型: {len(vehicle_models)} 条'))

        # ── 2. 颜色 ─────────────────────────────────────────
        self.stdout.write('🎨 填充颜色...')
        colors = {}
        for name in ['red', 'white', 'blue', 'black']:
            c, created = Color.objects.get_or_create(name=name)
            colors[name] = c
            if created:
                self.stdout.write(f'   创建颜色: {name}')
        self.stdout.write(self.style.SUCCESS(f'✅ 颜色: {len(colors)} 条'))

        # ── 3. 位置类型 ──────────────────────────────────────
        self.stdout.write('📍 填充位置类型...')
        positions = {}
        for name in ['front', 'rear']:
            pt, created = PositionType.objects.get_or_create(name=name)
            positions[name] = pt
            if created:
                self.stdout.write(f'   创建位置: {name}')
        self.stdout.write(self.style.SUCCESS(f'✅ 位置类型: {len(positions)} 条'))

        # ── 4. 产品 ──────────────────────────────────────────
        self.stdout.write('🏭 填充产品（含挂数/合格率）...')
        products = {}
        for model_name, vm in vehicle_models.items():
            for color_name, c in colors.items():
                for pos_name, pt in positions.items():
                    config = PRODUCT_CONFIG.get((model_name, pos_name), {})
                    hanging = config.get('hanging_count', 4)
                    yield_rate = config.get('yield_rate', 80.0)

                    product, created = Product.objects.get_or_create(
                        vehicle_model=vm,
                        color=c,
                        position_type=pt,
                        defaults={
                            'hanging_count_per_vehicle': hanging,
                            'yield_rate': yield_rate,
                            'is_active': True,
                        }
                    )
                    if not created:
                        # 更新挂数和合格率（即使已存在）
                        product.hanging_count_per_vehicle = hanging
                        product.yield_rate = yield_rate
                        product.save()

                    key = f'{model_name}{pos_name} {color_name}'
                    products[key] = product
                    if created:
                        self.stdout.write(
                            f'   创建产品: {model_name} {pos_name} {color_name} '
                            f'(挂数={hanging}, 合格率={yield_rate}%)'
                        )
        self.stdout.write(self.style.SUCCESS(f'✅ 产品: {len(products)} 条'))

        # ── 5. 涂装库存 ──────────────────────────────────────
        self.stdout.write('📊 填充涂装库存...')
        inv_count = 0
        for material_key, (current_qty, safety_qty) in INVENTORY_DATA.items():
            # 解析物料名称，例如 'A0front red'
            parts = material_key.split(' ')
            color_name = parts[1]
            model_pos = parts[0]  # e.g. 'A0front'

            # 找对应产品
            product = products.get(material_key)
            if not product:
                self.stdout.write(self.style.WARNING(f'   ⚠️ 找不到产品: {material_key}'))
                continue

            inv, created = Inventory.objects.get_or_create(
                product=product,
                defaults={
                    'current_quantity': current_qty,
                }
            )
            if not created:
                inv.current_quantity = current_qty
                inv.save()

            inv_count += 1

        self.stdout.write(self.style.SUCCESS(f'✅ 涂装库存: {inv_count} 条'))

        # ── 6. 安全库存 ──────────────────────────────────────
        self.stdout.write('🛡️  填充安全库存...')
        ss_count = 0
        for material_key, (current_qty, safety_qty) in INVENTORY_DATA.items():
            product = products.get(material_key)
            if not product:
                continue
            ss, created = SafetyStock.objects.get_or_create(
                product=product,
                defaults={'quantity': safety_qty}
            )
            if not created:
                ss.quantity = safety_qty
                ss.save()
            ss_count += 1
        self.stdout.write(self.style.SUCCESS(f'✅ 安全库存: {ss_count} 条'))

        # ── 7. 注塑库存 ──────────────────────────────────────
        self.stdout.write('💉 填充注塑库存...')
        inj_count = 0
        for model_name, vm in vehicle_models.items():
            for pos_name, pt in positions.items():
                # 注塑库存不区分颜色，使用 red 产品作为代表
                # （每个 model+pos 组合只创建一条，颜色用 red）
                inj_key = f'{model_name}{pos_name}'
                inj_qty = INJECTION_INVENTORY_DATA.get(inj_key, 0)
                color_name = 'red'  # 注塑库存以red为代表
                product_key = f'{model_name}{pos_name} {color_name}'
                product = products.get(product_key)
                if not product:
                    continue
                inj, created = InjectionInventory.objects.get_or_create(
                    product=product,
                    defaults={
                        'current_quantity': inj_qty,
                    }
                )
                if not created:
                    inj.current_quantity = inj_qty
                    inj.save()
                inj_count += 1
        self.stdout.write(self.style.SUCCESS(f'✅ 注塑库存: {inj_count} 条'))

        # ── 8. 总成拉动数据 ──────────────────────────────────
        self.stdout.write('🚗 填充总成拉动数据（从 Excel）...')

        excel_path = options.get('excel')
        if not excel_path:
            import os
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
            excel_path = os.path.join(base_dir, 'doc', '3.1总成拉动数据_1440min.xlsx')

        if not __import__('os').path.exists(excel_path):
            self.stdout.write(self.style.WARNING(
                f'   ⚠️  Excel 文件不存在: {excel_path}，使用模拟数据'
            ))
            assembly_rows = self._generate_mock_assembly(1440)
        else:
            assembly_rows = self._read_assembly_excel(excel_path)
            self.stdout.write(f'   读取 Excel: {len(assembly_rows)} 条')

        # 删除旧数据
        old_count = AssemblyPullData.objects.count()
        if old_count > 0:
            self.stdout.write(f'   删除旧总成拉动数据: {old_count} 条')
            AssemblyPullData.objects.all().delete()

        # 批量创建
        import_batch = timezone.now().strftime('%Y%m%d_%H%M%S')
        base_time = timezone.now()

        to_create = []
        missing_products = set()
        for seq, model_name, color_name in assembly_rows:
            vm = vehicle_models.get(model_name)
            c = colors.get(color_name)
            if not vm or not c:
                missing_products.add(f'{model_name}/{color_name}')
                continue

            planned_time = base_time + timedelta(minutes=seq - 1)
            to_create.append(AssemblyPullData(
                sequence=seq,
                vehicle_model=vm,
                color=c,
                planned_time=planned_time,
                import_batch=import_batch,
            ))

        AssemblyPullData.objects.bulk_create(to_create, batch_size=200)
        if missing_products:
            self.stdout.write(self.style.WARNING(
                f'   ⚠️  跳过未知产品: {missing_products}'
            ))
        self.stdout.write(self.style.SUCCESS(f'✅ 总成拉动数据: {len(to_create)} 条'))

        # ── 9. 系统参数 ──────────────────────────────────────
        self.stdout.write('⚙️  填充系统参数...')
        param_count = 0
        for param_key, param_value, description in SYSTEM_PARAMS:
            sp, created = SystemParameter.objects.get_or_create(
                param_key=param_key,
                defaults={
                    'param_value': param_value,
                    'description': description,
                }
            )
            if not created:
                sp.param_value = param_value
                sp.description = description
                sp.save()
            param_count += 1
        self.stdout.write(self.style.SUCCESS(f'✅ 系统参数: {param_count} 条'))

        # ── 完成汇总 ─────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 50))
        self.stdout.write(self.style.SUCCESS('🎉 数据填充完成！'))
        self.stdout.write(self.style.SUCCESS('=' * 50))
        self.stdout.write(f'   车型:         {VehicleModel.objects.count()} 条')
        self.stdout.write(f'   颜色:         {Color.objects.count()} 条')
        self.stdout.write(f'   位置类型:     {PositionType.objects.count()} 条')
        self.stdout.write(f'   产品:         {Product.objects.count()} 条')
        self.stdout.write(f'   涂装库存:     {Inventory.objects.count()} 条')
        self.stdout.write(f'   注塑库存:     {InjectionInventory.objects.count()} 条')
        self.stdout.write(f'   安全库存:     {SafetyStock.objects.count()} 条')
        self.stdout.write(f'   总成拉动数据: {AssemblyPullData.objects.count()} 条')
        self.stdout.write(f'   系统参数:     {SystemParameter.objects.count()} 条')

    def _read_assembly_excel(self, path):
        """从 Excel 读取总成拉动数据"""
        try:
            wb = openpyxl.load_workbook(path, read_only=True)
            ws = wb.active
            rows = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i == 0:
                    continue  # skip header
                if row[0] is None:
                    break
                seq = int(row[0])
                model = str(row[1]).strip()
                color = str(row[2]).strip().lower()
                rows.append((seq, model, color))
            wb.close()
            return rows
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'   ⚠️  读取 Excel 失败: {e}，使用模拟数据'))
            return self._generate_mock_assembly(1440)

    def _generate_mock_assembly(self, count):
        """生成模拟总成拉动数据（按比例随机）"""
        import random
        # 按统计比例：A0 更多，颜色分布参考 Excel
        vehicles = (['A0'] * 6 + ['A1'] * 4)
        color_weights = {
            'A0': ['red'] * 3 + ['white'] * 3 + ['blue'] * 2 + ['black'] * 2,
            'A1': ['red'] * 2 + ['white'] * 3 + ['blue'] * 2 + ['black'] * 3,
        }
        rows = []
        for i in range(1, count + 1):
            model = random.choice(vehicles)
            color = random.choice(color_weights[model])
            rows.append((i, model, color))
        return rows
