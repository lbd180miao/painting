"""
URL configuration for data app.
"""
from django.urls import path
from . import views

app_name = 'data'

urlpatterns = [
    path('import/', views.import_data, name='import'),
    path('inventory/', views.inventory_list, name='inventory_list'),
    path('injection/', views.injection_list, name='injection_list'),
    path('safety/', views.safety_list, name='safety_list'),
    path('assembly/', views.assembly_list, name='assembly_list'),
    path('vehicles/', views.vehicle_list, name='vehicles'),
    path('colors/', views.color_list, name='colors'),
    path('products/', views.product_list, name='products'),
    path('parameters/', views.parameter_list, name='parameters'),
]
