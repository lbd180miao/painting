from django import forms

from .models import (
    AssemblyPullData,
    Color,
    InjectionInventory,
    Inventory,
    Product,
    SafetyStock,
    SystemParameter,
    VehicleModel,
)


class VehicleModelForm(forms.ModelForm):
    class Meta:
        model = VehicleModel
        fields = ["name"]
        labels = {"name": "车型名称"}


class ColorForm(forms.ModelForm):
    class Meta:
        model = Color
        fields = ["name"]
        labels = {"name": "颜色名称"}


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "vehicle_model",
            "color",
            "position_type",
            "hanging_count_per_vehicle",
            "yield_rate",
            "is_active",
        ]
        labels = {
            "vehicle_model": "车型",
            "color": "颜色",
            "position_type": "位置",
            "hanging_count_per_vehicle": "每车挂数",
            "yield_rate": "合格率(%)",
            "is_active": "启用",
        }


class SystemParameterForm(forms.ModelForm):
    class Meta:
        model = SystemParameter
        fields = ["param_key", "param_value", "description"]
        labels = {
            "param_key": "参数键名",
            "param_value": "参数值",
            "description": "描述",
        }


class InventoryForm(forms.ModelForm):
    class Meta:
        model = Inventory
        fields = ["product", "current_quantity"]
        labels = {
            "product": "产品",
            "current_quantity": "当前库存",
        }


class InjectionInventoryForm(forms.ModelForm):
    class Meta:
        model = InjectionInventory
        fields = ["product", "current_quantity"]
        labels = {
            "product": "产品",
            "current_quantity": "当前库存",
        }



class SafetyStockForm(forms.ModelForm):
    class Meta:
        model = SafetyStock
        fields = ["product", "quantity"]
        labels = {
            "product": "产品",
            "quantity": "安全库存数量",
        }


class AssemblyPullDataForm(forms.ModelForm):
    class Meta:
        model = AssemblyPullData
        fields = ["sequence", "vehicle_model", "color", "planned_time", "import_batch"]
        labels = {
            "sequence": "顺序号",
            "vehicle_model": "车型",
            "color": "颜色",
            "planned_time": "计划时间",
            "import_batch": "导入批次",
        }
        widgets = {
            "planned_time": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["planned_time"].input_formats = ["%Y-%m-%dT%H:%M"]
