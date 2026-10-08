from django.contrib import admin

from apps.deliveries.models import Delivery


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ("order", "driver", "status", "fee", "created_at")
    list_filter = ("status",)
