"""
URL configuration for data app.
"""
from django.urls import path
from . import views

app_name = 'data'

urlpatterns = [
    path('import/', views.import_data, name='import'),
    path('import/templates/<str:template_type>/', views.import_template_download, name='import_template_download'),
    path('import/history/', views.import_history, name='import_history'),
    path('import/history/export/', views.import_history_export, name='import_history_export'),
    path('import/history/<int:pk>/', views.import_history_detail, name='import_history_detail'),
    path('inventory/', views.inventory_list, name='inventory_list'),
    path('inventory/export/', views.inventory_export, name='inventory_export'),
    path('inventory/bulk-delete/', views.inventory_bulk_delete, name='inventory_bulk_delete'),
    path('inventory/create/', views.inventory_create, name='inventory_create'),
    path('inventory/<int:pk>/edit/', views.inventory_update, name='inventory_update'),
    path('inventory/<int:pk>/delete/', views.inventory_delete, name='inventory_delete'),
    path('injection/', views.injection_list, name='injection_list'),
    path('injection/export/', views.injection_export, name='injection_export'),
    path('injection/bulk-delete/', views.injection_bulk_delete, name='injection_bulk_delete'),
    path('injection/create/', views.injection_create, name='injection_create'),
    path('injection/<int:pk>/edit/', views.injection_update, name='injection_update'),
    path('injection/<int:pk>/delete/', views.injection_delete, name='injection_delete'),
    path('safety/', views.safety_list, name='safety_list'),
    path('safety/export/', views.safety_export, name='safety_export'),
    path('safety/bulk-delete/', views.safety_bulk_delete, name='safety_bulk_delete'),
    path('safety/create/', views.safety_create, name='safety_create'),
    path('safety/<int:pk>/edit/', views.safety_update, name='safety_update'),
    path('safety/<int:pk>/delete/', views.safety_delete, name='safety_delete'),
    path('assembly/', views.assembly_list, name='assembly_list'),
    path('assembly/export/', views.assembly_export, name='assembly_export'),
    path('assembly/bulk-delete/', views.assembly_bulk_delete, name='assembly_bulk_delete'),
    path('assembly/create/', views.assembly_create, name='assembly_create'),
    path('assembly/<int:pk>/edit/', views.assembly_update, name='assembly_update'),
    path('assembly/<int:pk>/delete/', views.assembly_delete, name='assembly_delete'),
    path('vehicles/', views.vehicle_list, name='vehicles'),
    path('vehicles/create/', views.vehicle_create, name='vehicle_create'),
    path('vehicles/<int:pk>/edit/', views.vehicle_update, name='vehicle_update'),
    path('vehicles/<int:pk>/delete/', views.vehicle_delete, name='vehicle_delete'),
    path('colors/', views.color_list, name='colors'),
    path('colors/create/', views.color_create, name='color_create'),
    path('colors/<int:pk>/edit/', views.color_update, name='color_update'),
    path('colors/<int:pk>/delete/', views.color_delete, name='color_delete'),
    path('products/', views.product_list, name='products'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<int:pk>/edit/', views.product_update, name='product_update'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path('parameters/', views.parameter_list, name='parameters'),
    path('parameters/<int:pk>/edit/', views.parameter_update, name='parameter_update'),
]
