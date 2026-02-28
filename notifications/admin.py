from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'is_read', 'created_at', 'related_record']
    list_filter = ['is_read', 'created_at']
    search_fields = ['title', 'content', 'user__username']
    readonly_fields = ['created_at']
