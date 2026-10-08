from rest_framework import serializers

from apps.payments.models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.number", read_only=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "order",
            "order_number",
            "amount",
            "method",
            "status",
            "reference",
            "provider",
            "paid_at",
            "created_at",
        )
        read_only_fields = fields
