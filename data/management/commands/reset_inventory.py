"""
重置涂装库存管理命令 - reset_inventory
根据 3.2涂装库存.xlsx 的数据重置涂装库存和安全库存

使用方法:
    python manage.py reset_inventory
"""
from django.core.management.base import BaseCommand

# 从 3.2涂装库存.xlsx 提取的数据
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
