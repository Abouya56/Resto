from rest_framework import serializers

from apps.tables.models import DiningTable, QRCode


class QRCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = QRCode
        fields = ("id", "token", "public_url", "image", "is_active", "created_at")
        read_only_fields = fields


class DiningTableSerializer(serializers.ModelSerializer):
    qrcode = QRCodeSerializer(read_only=True)

    class Meta:
        model = DiningTable
        fields = ("id", "restaurant", "number", "capacity", "status", "is_active", "qrcode")
        read_only_fields = ("id", "restaurant")
