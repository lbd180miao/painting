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
]
