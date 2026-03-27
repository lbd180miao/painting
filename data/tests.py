from io import BytesIO

import pandas as pd
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from data.models import (
    AssemblyPullData,
    Color,
    ImportRecord,
    InjectionInventory,
    Inventory,
    PositionType,
    Product,
    SafetyStock,
    SystemParameter,
    VehicleModel,
)


class BaseConfigCrudTests(TestCase):
    def setUp(self):
        self.front = PositionType.objects.create(name="front")
        self.rear = PositionType.objects.create(name="rear")
        self.vehicle = VehicleModel.objects.create(name="A0")
        self.color = Color.objects.create(name="red")
        self.product = Product.objects.create(
            vehicle_model=self.vehicle,
            color=self.color,
            position_type=self.front,
            hanging_count_per_vehicle=4,
            yield_rate=80,
            is_active=True,
        )
        self.parameter, _ = SystemParameter.objects.update_or_create(
            param_key="CYCLE_TIME_MIN",
            defaults={
                "param_value": "300",
                "description": "cycle",
            },
        )
        self.paint_inventory = Inventory.objects.create(
            product=self.product,
            current_quantity=10,
        )
        self.injection_inventory = InjectionInventory.objects.create(
            product=self.product,
            current_quantity=12,
        )
        self.safety_stock = SafetyStock.objects.create(
            product=self.product,
            quantity=5,
        )
        self.assembly = AssemblyPullData.objects.create(
            sequence=1,
            vehicle_model=self.vehicle,
            color=self.color,
            planned_time="2026-03-23T08:00:00Z",
            import_batch="batch-1",
        )

    def test_vehicle_crud_views_create_update_delete(self):
        create_response = self.client.post(
            reverse("data:vehicle_create"),
            {"name": "A1"},
            follow=True,
        )
        self.assertEqual(create_response.status_code, 200)
        self.assertTrue(VehicleModel.objects.filter(name="A1").exists())

        vehicle = VehicleModel.objects.get(name="A1")
        update_response = self.client.post(
            reverse("data:vehicle_update", args=[vehicle.id]),
            {"name": "A1-改"},
            follow=True,
        )
        self.assertEqual(update_response.status_code, 200)
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.name, "A1-改")

        delete_response = self.client.post(
            reverse("data:vehicle_delete", args=[vehicle.id]),
            follow=True,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(VehicleModel.objects.filter(id=vehicle.id).exists())

    def test_color_crud_views_create_update_delete(self):
        create_response = self.client.post(
            reverse("data:color_create"),
            {"name": "green"},
            follow=True,
        )
        self.assertEqual(create_response.status_code, 200)
        self.assertTrue(Color.objects.filter(name="green").exists())

        color = Color.objects.get(name="green")
        update_response = self.client.post(
            reverse("data:color_update", args=[color.id]),
            {"name": "blue"},
            follow=True,
        )
        self.assertEqual(update_response.status_code, 200)
        color.refresh_from_db()
        self.assertEqual(color.name, "blue")

        delete_response = self.client.post(
            reverse("data:color_delete", args=[color.id]),
            follow=True,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(Color.objects.filter(id=color.id).exists())

    def test_product_crud_views_create_update_delete(self):
        vehicle_b = VehicleModel.objects.create(name="B0")
        color_blue = Color.objects.create(name="blue")

        create_response = self.client.post(
            reverse("data:product_create"),
            {
                "vehicle_model": vehicle_b.id,
                "color": color_blue.id,
                "position_type": self.rear.id,
                "hanging_count_per_vehicle": 5,
                "yield_rate": "88.50",
                "is_active": "on",
            },
            follow=True,
        )
        self.assertEqual(create_response.status_code, 200)
        created = Product.objects.get(
            vehicle_model=vehicle_b,
            color=color_blue,
            position_type=self.rear,
        )
        self.assertEqual(created.hanging_count_per_vehicle, 5)

        update_response = self.client.post(
            reverse("data:product_update", args=[created.id]),
            {
                "vehicle_model": vehicle_b.id,
                "color": color_blue.id,
                "position_type": self.rear.id,
                "hanging_count_per_vehicle": 6,
                "yield_rate": "91.00",
            },
            follow=True,
        )
        self.assertEqual(update_response.status_code, 200)
        created.refresh_from_db()
        self.assertEqual(created.hanging_count_per_vehicle, 6)
        self.assertEqual(str(created.yield_rate), "91.00")
        self.assertFalse(created.is_active)

        delete_response = self.client.post(
            reverse("data:product_delete", args=[created.id]),
            follow=True,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(Product.objects.filter(id=created.id).exists())

    def test_parameter_update_view_updates_value_and_description(self):
        response = self.client.post(
            reverse("data:parameter_update", args=[self.parameter.id]),
            {
                "param_key": self.parameter.param_key,
                "param_value": "360",
                "description": "updated",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.parameter.refresh_from_db()
        self.assertEqual(self.parameter.param_value, "360")
        self.assertEqual(self.parameter.description, "updated")

    def test_config_list_pages_show_action_buttons(self):
        response = self.client.get(reverse("data:vehicles"))

        self.assertContains(response, "新增车型")
        self.assertContains(response, "编辑")
        self.assertContains(response, "删除")

    def test_paint_inventory_crud_views_create_update_delete(self):
        vehicle_b = VehicleModel.objects.create(name="B1")
        color_blue = Color.objects.create(name="blue")
        product_b = Product.objects.create(
            vehicle_model=vehicle_b,
            color=color_blue,
            position_type=self.front,
            hanging_count_per_vehicle=4,
            yield_rate=85,
        )

        create_response = self.client.post(
            reverse("data:inventory_create"),
            {
                "product": product_b.id,
                "current_quantity": 20,
                "updated_quantity": 18,
            },
            follow=True,
        )
        self.assertEqual(create_response.status_code, 200)
        created = Inventory.objects.get(product=product_b)
        self.assertEqual(created.current_quantity, 20)

        update_response = self.client.post(
            reverse("data:inventory_update", args=[created.id]),
            {
                "product": product_b.id,
                "current_quantity": 25,
                "updated_quantity": 23,
            },
            follow=True,
        )
        self.assertEqual(update_response.status_code, 200)
        created.refresh_from_db()
        self.assertEqual(created.current_quantity, 25)

        delete_response = self.client.post(
            reverse("data:inventory_delete", args=[created.id]),
            follow=True,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(Inventory.objects.filter(id=created.id).exists())

    def test_injection_inventory_crud_views_create_update_delete(self):
        vehicle_b = VehicleModel.objects.create(name="B2")
        color_blue = Color.objects.create(name="blue")
        product_b = Product.objects.create(
            vehicle_model=vehicle_b,
            color=color_blue,
            position_type=self.front,
            hanging_count_per_vehicle=4,
            yield_rate=85,
        )

        create_response = self.client.post(
            reverse("data:injection_create"),
            {
                "product": product_b.id,
                "current_quantity": 30,
                "updated_quantity": 28,
            },
            follow=True,
        )
        self.assertEqual(create_response.status_code, 200)
        created = InjectionInventory.objects.get(product=product_b)
        self.assertEqual(created.current_quantity, 30)

        update_response = self.client.post(
            reverse("data:injection_update", args=[created.id]),
            {
                "product": product_b.id,
                "current_quantity": 35,
                "updated_quantity": 33,
            },
            follow=True,
        )
        self.assertEqual(update_response.status_code, 200)
        created.refresh_from_db()
        self.assertEqual(created.current_quantity, 35)

        delete_response = self.client.post(
            reverse("data:injection_delete", args=[created.id]),
            follow=True,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(InjectionInventory.objects.filter(id=created.id).exists())

    def test_safety_stock_crud_views_create_update_delete(self):
        vehicle_b = VehicleModel.objects.create(name="B3")
        color_blue = Color.objects.create(name="blue")
        product_b = Product.objects.create(
            vehicle_model=vehicle_b,
            color=color_blue,
            position_type=self.front,
            hanging_count_per_vehicle=4,
            yield_rate=85,
        )

        create_response = self.client.post(
            reverse("data:safety_create"),
            {
                "product": product_b.id,
                "quantity": 7,
            },
            follow=True,
        )
        self.assertEqual(create_response.status_code, 200)
        created = SafetyStock.objects.get(product=product_b)
        self.assertEqual(created.quantity, 7)

        update_response = self.client.post(
            reverse("data:safety_update", args=[created.id]),
            {
                "product": product_b.id,
                "quantity": 9,
            },
            follow=True,
        )
        self.assertEqual(update_response.status_code, 200)
        created.refresh_from_db()
        self.assertEqual(created.quantity, 9)

        delete_response = self.client.post(
            reverse("data:safety_delete", args=[created.id]),
            follow=True,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(SafetyStock.objects.filter(id=created.id).exists())

    def test_assembly_crud_views_create_update_delete(self):
        create_response = self.client.post(
            reverse("data:assembly_create"),
            {
                "sequence": 2,
                "vehicle_model": self.vehicle.id,
                "color": self.color.id,
                "planned_time": "2026-03-24T08:30",
                "import_batch": "batch-2",
            },
            follow=True,
        )
        self.assertEqual(create_response.status_code, 200)
        created = AssemblyPullData.objects.get(sequence=2)
        self.assertEqual(created.import_batch, "batch-2")

        update_response = self.client.post(
            reverse("data:assembly_update", args=[created.id]),
            {
                "sequence": 3,
                "vehicle_model": self.vehicle.id,
                "color": self.color.id,
                "planned_time": "2026-03-25T09:00",
                "import_batch": "batch-3",
            },
            follow=True,
        )
        self.assertEqual(update_response.status_code, 200)
        created.refresh_from_db()
        self.assertEqual(created.sequence, 3)
        self.assertEqual(created.import_batch, "batch-3")

        delete_response = self.client.post(
            reverse("data:assembly_delete", args=[created.id]),
            follow=True,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(AssemblyPullData.objects.filter(id=created.id).exists())

    def test_data_management_list_pages_show_action_buttons(self):
        response = self.client.get(reverse("data:inventory_list"))

        self.assertContains(response, "新增库存")
        self.assertContains(response, "编辑")
        self.assertContains(response, "删除")

    def test_import_page_shows_overwrite_warnings(self):
        response = self.client.get(reverse("data:import"))

        self.assertContains(response, "总成拉动数据导入会先清空现有记录再重建")
        self.assertContains(response, "库存类导入会覆盖同产品的当前库存")

    def test_delete_confirm_page_shows_related_impact_summary(self):
        response = self.client.get(reverse("data:vehicle_delete", args=[self.vehicle.id]))

        self.assertContains(response, "删除后将同时影响以下关联数据")
        self.assertContains(response, "产品: 1 条")
        self.assertContains(response, "总成拉动: 1 条")

    def test_inventory_list_supports_keyword_and_vehicle_filters(self):
        vehicle_b = VehicleModel.objects.create(name="B9")
        color_blue = Color.objects.create(name="blue")
        product_b = Product.objects.create(
            vehicle_model=vehicle_b,
            color=color_blue,
            position_type=self.front,
            hanging_count_per_vehicle=4,
            yield_rate=90,
        )
        Inventory.objects.create(product=product_b, current_quantity=99)

        response = self.client.get(
            reverse("data:inventory_list"),
            {"q": "蓝", "vehicle": vehicle_b.id},
        )

        self.assertContains(response, "<td>B9</td>", html=False)
        self.assertNotContains(response, "<td>A0</td>", html=False)

    def test_injection_list_supports_keyword_filter(self):
        vehicle_b = VehicleModel.objects.create(name="C1")
        color_blue = Color.objects.create(name="blue")
        product_b = Product.objects.create(
            vehicle_model=vehicle_b,
            color=color_blue,
            position_type=self.rear,
            hanging_count_per_vehicle=4,
            yield_rate=90,
        )
        InjectionInventory.objects.create(product=product_b, current_quantity=77)

        response = self.client.get(reverse("data:injection_list"), {"q": "C1"})

        self.assertContains(response, "<td>C1</td>", html=False)
        self.assertNotContains(response, "<td>A0</td>", html=False)

    def test_safety_list_supports_color_filter(self):
        vehicle_b = VehicleModel.objects.create(name="D2")
        color_blue = Color.objects.create(name="blue")
        product_b = Product.objects.create(
            vehicle_model=vehicle_b,
            color=color_blue,
            position_type=self.front,
            hanging_count_per_vehicle=4,
            yield_rate=90,
        )
        SafetyStock.objects.create(product=product_b, quantity=11)

        response = self.client.get(reverse("data:safety_list"), {"color": color_blue.id})

        self.assertContains(response, "<td>D2</td>", html=False)
        self.assertNotContains(response, "<td>A0</td>", html=False)

    def test_assembly_list_supports_batch_and_keyword_filters(self):
        vehicle_b = VehicleModel.objects.create(name="E3")
        color_blue = Color.objects.create(name="blue")
        AssemblyPullData.objects.create(
            sequence=2,
            vehicle_model=vehicle_b,
            color=color_blue,
            planned_time="2026-03-24T08:00:00Z",
            import_batch="batch-blue",
        )

        response = self.client.get(
            reverse("data:assembly_list"),
            {"q": "蓝", "import_batch": "batch-blue"},
        )

        self.assertContains(response, "<td>E3</td>", html=False)
        self.assertNotContains(response, "<td>batch-1</td>", html=False)

    def test_inventory_list_is_paginated(self):
        for index in range(2, 15):
            vehicle = VehicleModel.objects.create(name=f"P{index}")
            color = Color.objects.create(name=f"custom-{index}")
            product = Product.objects.create(
                vehicle_model=vehicle,
                color=color,
                position_type=self.front,
                hanging_count_per_vehicle=4,
                yield_rate=90,
            )
            Inventory.objects.create(product=product, current_quantity=index)

        response = self.client.get(reverse("data:inventory_list"), {"page": 2})

        self.assertContains(response, "第 2 / 2 页")
        self.assertContains(response, "<td>A0</td>", html=False)
        self.assertNotContains(response, "<td>P14</td>", html=False)

    def test_inventory_list_bulk_delete_removes_selected_rows(self):
        vehicle_b = VehicleModel.objects.create(name="G1")
        color_blue = Color.objects.create(name="blue")
        product_b = Product.objects.create(
            vehicle_model=vehicle_b,
            color=color_blue,
            position_type=self.front,
            hanging_count_per_vehicle=4,
            yield_rate=90,
        )
        extra_inventory = Inventory.objects.create(product=product_b, current_quantity=20)

        response = self.client.post(
            reverse("data:inventory_bulk_delete"),
            {"selected_ids": [self.paint_inventory.id, extra_inventory.id]},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Inventory.objects.filter(id=self.paint_inventory.id).exists())
        self.assertFalse(Inventory.objects.filter(id=extra_inventory.id).exists())

    def test_assembly_list_bulk_delete_removes_selected_rows(self):
        record = AssemblyPullData.objects.create(
            sequence=9,
            vehicle_model=self.vehicle,
            color=self.color,
            planned_time="2026-03-24T10:00:00Z",
            import_batch="batch-delete",
        )

        response = self.client.post(
            reverse("data:assembly_bulk_delete"),
            {"selected_ids": [self.assembly.id, record.id]},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AssemblyPullData.objects.filter(id=self.assembly.id).exists())
        self.assertFalse(AssemblyPullData.objects.filter(id=record.id).exists())

    def test_inventory_export_downloads_filtered_csv(self):
        vehicle_b = VehicleModel.objects.create(name="H1")
        color_blue = Color.objects.create(name="blue")
        product_b = Product.objects.create(
            vehicle_model=vehicle_b,
            color=color_blue,
            position_type=self.front,
            hanging_count_per_vehicle=4,
            yield_rate=90,
        )
        Inventory.objects.create(product=product_b, current_quantity=30)

        response = self.client.get(
            reverse("data:inventory_export"),
            {"q": "蓝"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment;", response["Content-Disposition"])
        content = response.content.decode("utf-8-sig")
        self.assertIn("H1,蓝,前,30", content)
        self.assertNotIn("A0,红,前,10", content)

    def test_assembly_export_downloads_filtered_csv(self):
        vehicle_b = VehicleModel.objects.create(name="J1")
        color_blue = Color.objects.create(name="blue")
        AssemblyPullData.objects.create(
            sequence=4,
            vehicle_model=vehicle_b,
            color=color_blue,
            planned_time="2026-03-24T09:00:00Z",
            import_batch="batch-export",
        )

        response = self.client.get(
            reverse("data:assembly_export"),
            {"import_batch": "batch-export"},
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8-sig")
        self.assertIn("4,J1,蓝", content)
        self.assertNotIn("1,A0,红", content)

    def test_injection_export_downloads_filtered_csv(self):
        vehicle_b = VehicleModel.objects.create(name="K1")
        color_blue = Color.objects.create(name="blue")
        product_b = Product.objects.create(
            vehicle_model=vehicle_b,
            color=color_blue,
            position_type=self.rear,
            hanging_count_per_vehicle=4,
            yield_rate=90,
        )
        InjectionInventory.objects.create(product=product_b, current_quantity=44)

        response = self.client.get(reverse("data:injection_export"), {"q": "K1"})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8-sig")
        self.assertIn("K1,蓝,后,44", content)
        self.assertNotIn("A0,红,前,12", content)

    def test_safety_export_downloads_filtered_csv(self):
        vehicle_b = VehicleModel.objects.create(name="L1")
        color_blue = Color.objects.create(name="blue")
        product_b = Product.objects.create(
            vehicle_model=vehicle_b,
            color=color_blue,
            position_type=self.front,
            hanging_count_per_vehicle=4,
            yield_rate=90,
        )
        SafetyStock.objects.create(product=product_b, quantity=15)

        response = self.client.get(reverse("data:safety_export"), {"q": "L1"})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8-sig")
        self.assertIn("L1,蓝,前,15", content)
        self.assertNotIn("A0,红,前,5", content)

    def test_inventory_update_redirects_back_to_filtered_list_when_next_is_provided(self):
        next_url = "/data/inventory/?q=%E8%93%9D&vehicle=2"

        response = self.client.post(
            reverse("data:inventory_update", args=[self.paint_inventory.id]),
            {
                "product": self.product.id,
                "current_quantity": 18,
                "updated_quantity": 16,
                "next": next_url,
            },
        )

        self.assertRedirects(response, next_url)

    def test_inventory_delete_redirects_back_to_filtered_list_when_next_is_provided(self):
        next_url = "/data/inventory/?q=%E7%BA%A2"

        response = self.client.post(
            reverse("data:inventory_delete", args=[self.paint_inventory.id]),
            {"next": next_url},
        )

        self.assertRedirects(response, next_url)

    def test_import_page_shows_missing_column_error_details(self):
        file_obj = self._build_excel_file([
            {"物料": "A0front red"},
        ])

        response = self.client.post(
            reverse("data:import"),
            {"import_type": "inventory", "file": file_obj},
        )

        self.assertContains(response, "导入错误明细")
        self.assertContains(response, "缺少必要列")
        self.assertContains(response, "当前库存")

    def test_import_page_shows_row_level_errors_and_keeps_valid_rows(self):
        file_obj = self._build_excel_file([
            {"物料": "bad-material", "当前库存": 5},
            {"物料": "A0front red", "当前库存": 8},
        ])

        response = self.client.post(
            reverse("data:import"),
            {"import_type": "inventory", "file": file_obj},
        )

        self.assertContains(response, "导入结果")
        self.assertContains(response, "第 2 行")
        self.assertContains(response, "物料名称无法解析")
        self.paint_inventory.refresh_from_db()
        self.assertEqual(self.paint_inventory.current_quantity, 8)

    def test_import_template_download_returns_expected_headers(self):
        response = self.client.get(reverse("data:import_template_download", args=["inventory"]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment;", response["Content-Disposition"])
        content = response.content.decode("utf-8-sig")
        self.assertIn("物料,当前库存", content)

    def test_import_creates_archive_record_and_shows_recent_history(self):
        file_obj = self._build_excel_file([
            {"物料": "A0front red", "当前库存": 9},
        ])

        post_response = self.client.post(
            reverse("data:import"),
            {"import_type": "inventory", "file": file_obj},
        )

        self.assertEqual(post_response.status_code, 200)
        record = ImportRecord.objects.get(import_type="inventory")
        self.assertEqual(record.file_name, "import.xlsx")
        self.assertEqual(record.success_count, 1)
        self.assertEqual(record.error_count, 0)
        self.assertEqual(record.status, "success")

        get_response = self.client.get(reverse("data:import"))
        self.assertContains(get_response, "最近导入记录")
        self.assertContains(get_response, "涂装库存")
        self.assertContains(get_response, "import.xlsx")
        self.assertContains(get_response, "成功 1")

    def test_import_history_list_supports_type_filter(self):
        ImportRecord.objects.create(
            import_type="inventory",
            file_name="inventory.xlsx",
            status="success",
            message="ok",
            success_count=2,
            error_count=0,
        )
        ImportRecord.objects.create(
            import_type="assembly",
            file_name="assembly.xlsx",
            status="failed",
            message="bad",
            success_count=0,
            error_count=2,
            error_details=[{"row": "第 3 行", "reason": "颜色为空"}],
        )

        response = self.client.get(reverse("data:import_history"), {"type": "assembly"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "导入历史")
        self.assertContains(response, "assembly.xlsx")
        self.assertNotContains(response, "inventory.xlsx")

    def test_import_history_detail_shows_error_details(self):
        record = ImportRecord.objects.create(
            import_type="assembly",
            file_name="assembly.xlsx",
            status="partial",
            message="成功导入总成拉动数据，共1条记录，失败1条",
            success_count=1,
            error_count=1,
            error_details=[{"row": "第 4 行", "reason": "产品名称或颜色为空"}],
        )

        response = self.client.get(reverse("data:import_history_detail", args=[record.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "导入记录详情")
        self.assertContains(response, "assembly.xlsx")
        self.assertContains(response, "第 4 行")
        self.assertContains(response, "产品名称或颜色为空")

    def test_import_history_list_supports_filename_search_and_summary_cards(self):
        ImportRecord.objects.create(
            import_type="inventory",
            file_name="paint-stock-1.xlsx",
            status="success",
            message="ok",
            success_count=3,
            error_count=0,
        )
        ImportRecord.objects.create(
            import_type="assembly",
            file_name="assembly-bad.xlsx",
            status="failed",
            message="bad",
            success_count=0,
            error_count=2,
        )

        response = self.client.get(reverse("data:import_history"), {"q": "assembly"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "assembly-bad.xlsx")
        self.assertNotContains(response, "paint-stock-1.xlsx")
        self.assertContains(response, "累计导入次数")
        self.assertContains(response, "累计失败条数")
        self.assertContains(response, "最近失败")

    def test_import_history_export_downloads_filtered_csv(self):
        ImportRecord.objects.create(
            import_type="inventory",
            file_name="paint-stock-1.xlsx",
            status="success",
            message="ok",
            success_count=3,
            error_count=0,
        )
        ImportRecord.objects.create(
            import_type="assembly",
            file_name="assembly-bad.xlsx",
            status="failed",
            message="bad",
            success_count=0,
            error_count=2,
        )

        response = self.client.get(reverse("data:import_history_export"), {"q": "assembly"})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8-sig")
        self.assertIn("assembly-bad.xlsx", content)
        self.assertNotIn("paint-stock-1.xlsx", content)

    def _build_excel_file(self, rows):
        output = BytesIO()
        pd.DataFrame(rows).to_excel(output, index=False)
        output.seek(0)
        return SimpleUploadedFile(
            "import.xlsx",
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
