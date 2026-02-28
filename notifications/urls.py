from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.inbox_view, name='inbox'),
    path('mark-read/<int:notification_id>/', views.mark_read_view, name='mark_read'),
    path('delete/<int:notification_id>/', views.delete_notification_view, name='delete'),
]
