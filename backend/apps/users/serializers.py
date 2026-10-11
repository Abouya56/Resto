from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.users.models import CustomerAddress, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "phone", "role", "created_at")
        read_only_fields = ("id", "role", "created_at")


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(min_length=8)

    def validate_new_password(self, value):
        validate_password(value)
        return value


class CustomerAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerAddress
        fields = (
            "id",
            "label",
            "line1",
            "city",
            "district",
            "instructions",
            "latitude",
            "longitude",
            "is_default",
        )

    def create(self, validated_data):
        validated_data["customer"] = self.context["request"].user
        return super().create(validated_data)
