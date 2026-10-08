from rest_framework import serializers

from apps.inventory.models import StockItem, StockMovement


class StockItemSerializer(serializers.ModelSerializer):
    is_low = serializers.BooleanField(read_only=True)

    class Meta:
        model = StockItem
        fields = (
            "id",
            "restaurant",
            "name",
            "unit",
            "quantity",
            "min_threshold",
            "product",
            "is_active",
            "is_low",
        )
        read_only_fields = ("id", "restaurant", "quantity")


class StockMovementSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = StockMovement
        fields = ("id", "restaurant", "item", "item_name", "movement_type", "quantity", "reason", "user", "created_at")
        read_only_fields = ("id", "restaurant", "user", "created_at")
