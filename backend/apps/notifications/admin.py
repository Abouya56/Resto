from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "notif_type", "is_read", "created_at")
    list_filter = ("is_read", "notif_type")
