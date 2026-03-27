"""
URL configuration for schedule app.
"""
from django.urls import path
from . import views

app_name = 'schedule'

urlpatterns = [
    path('calculate/', views.calculate_view, name='calculate'),
    path('result/<int:id>/', views.result_view, name='result'),
    path('history/', views.history_list_view, name='history'),
    path('history/<int:id>/delete/', views.history_delete_view, name='history_delete'),
    path('history/<int:id>/rollback/', views.history_rollback_view, name='history_rollback'),
    path('export/<int:id>/', views.export_to_excel_view, name='export'),
]
