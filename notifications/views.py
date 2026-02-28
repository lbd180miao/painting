from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages as django_messages
from django.http import JsonResponse
from .models import Notification


@login_required
def inbox_view(request):
    """消息收件箱视图"""
    user_notifications = Notification.objects.filter(user=request.user).select_related('related_record')
    unread_count = user_notifications.filter(is_read=False).count()

    context = {
        'notifications': user_notifications,
        'unread_count': unread_count,
    }
    return render(request, 'notifications/inbox.html', context)


@login_required
def mark_read_view(request, notification_id):
    """标记消息为已读"""
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    notification.is_read = True
    notification.save()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success'})

    django_messages.success(request, f"消息 '{notification.title}' 已标记为已读")
    return redirect('notifications:inbox')


@login_required
def delete_notification_view(request, notification_id):
    """删除消息"""
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    notification.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success'})

    django_messages.success(request, "消息已删除")
    return redirect('notifications:inbox')
