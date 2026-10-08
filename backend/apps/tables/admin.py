from django.contrib import admin

from apps.tables.models import DiningTable, QRCode


@admin.register(DiningTable)
class DiningTableAdmin(admin.ModelAdmin):
    list_display = ("number", "restaurant", "capacity", "status", "is_active")
    list_filter = ("status", "restaurant")


@admin.register(QRCode)
class QRCodeAdmin(admin.ModelAdmin):
    list_display = ("table", "token", "is_active", "created_at")
    search_fields = ("token",)
