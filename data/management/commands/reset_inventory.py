"""
重置涂装库存管理命令 - reset_inventory
根据 3.2涂装库存.xlsx 的数据重置涂装库存和安全库存

使用方法:
    python manage.py reset_inventory
"""
from django.core.management.base import BaseCommand

# 涂装库存基础水位 - 收紧到工厂真实水位
# 设计意图：current 设在 safety 附近 (±5)，让每次排产都能触发不同的生产组合
INVENTORY_DATA = {
    # 物料名           当前库存  安全库存
    'A0front red':   (35,   30),
    'A0rear red':    (28,   30),
    'A0front white': (22,   20),
    'A0rear white':  (18,   20),
    'A0front blue':  (18,   15),
    'A0rear blue':   (12,   15),
    'A0front black': (12,   10),
    'A0rear black':  ( 7,   10),
    'A1front red':   (28,   25),
    'A1rear red':    (20,   25),
    'A1front blue':  (30,   25),
    'A1rear blue':   (22,   25),
    'A1front white': (22,   20),
    'A1rear white':  (15,   20),
    'A1front black': (12,   10),
    'A1rear black':  ( 8,   10),
}


class Command(BaseCommand):
    help = '根据 3.2涂装库存.xlsx 重置涂装库存和安全库存'

    def handle(self, *args, **options):
        from data.models import VehicleModel, Color, PositionType, Product, Inventory, SafetyStock

        self.stdout.write('=== 重置涂装库存 (来自 3.2涂装库存.xlsx) ===')
        inv_count = 0
        ss_count = 0
        skip_count = 0

        for material_key, (current_qty, safety_qty) in INVENTORY_DATA.items():
            parts = material_key.split(' ')
            color_name = parts[1]
            model_pos = parts[0]  # e.g. 'A0front'

            # 解析车型和位置
            if 'front' in model_pos:
                model_name = model_pos.replace('front', '')
                pos_name = 'front'
            else:
                model_name = model_pos.replace('rear', '')
                pos_name = 'rear'

            try:
                vm = VehicleModel.objects.get(name=model_name)
                c = Color.objects.get(name=color_name)
                pt = PositionType.objects.get(name=pos_name)
                product = Product.objects.get(vehicle_model=vm, color=c, position_type=pt)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  ⚠️  跳过 {material_key}: {e}'))
                skip_count += 1
                continue

            # 更新涂装库存
            inv, created = Inventory.objects.update_or_create(
                product=product,
                defaults={'current_quantity': current_qty}
            )
            action = '创建' if created else '更新'
            self.stdout.write(f'  {action} 涂装库存: {material_key} = {current_qty}')
            inv_count += 1

            # 更新安全库存
            ss, created = SafetyStock.objects.update_or_create(
                product=product,
                defaults={'quantity': safety_qty}
            )
            action = '创建' if created else '更新'
            self.stdout.write(f'  {action} 安全库存: {material_key} = {safety_qty}')
            ss_count += 1

        self.stdout.write('')
        if skip_count:
            self.stdout.write(self.style.WARNING(f'  ⚠️  跳过: {skip_count} 条'))
        self.stdout.write(self.style.SUCCESS(f'✅ 涂装库存重置完成: {inv_count} 条'))
        self.stdout.write(self.style.SUCCESS(f'✅ 安全库存重置完成: {ss_count} 条'))
