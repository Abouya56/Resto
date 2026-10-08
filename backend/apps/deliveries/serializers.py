from rest_framework import serializers

from apps.deliveries.models import Delivery


class DeliverySerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.number", read_only=True)
    restaurant = serializers.IntegerField(source="order.restaurant_id", read_only=True)

    class Meta:
        model = Delivery
        fields = (
            "id",
            "order",
            "order_number",
            "restaurant",
            "driver",
            "address_text",
            "fee",
            "status",
            "assigned_at",
            "picked_up_at",
            "delivered_at",
            "notes",
        )
        read_only_fields = ("id", "order", "order_number", "restaurant", "assigned_at", "picked_up_at", "delivered_at")
