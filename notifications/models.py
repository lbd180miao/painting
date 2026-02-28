from django.db import models
from django.contrib.auth.models import User
from schedule.models import ScheduleRecord


class Notification(models.Model):
    """消息通知模型"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', verbose_name="用户")
    title = models.CharField(max_length=255, verbose_name="标题")
    content = models.TextField(verbose_name="内容")
    is_read = models.BooleanField(default=False, verbose_name="是否已读")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    related_record = models.ForeignKey(
        ScheduleRecord,
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True,
        verbose_name="相关排产记录"
    )

    class Meta:
        verbose_name = "消息"
        verbose_name_plural = "消息"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.title}"
