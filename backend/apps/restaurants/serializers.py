from rest_framework import serializers

from apps.restaurants.models import Employee, Restaurant
from apps.users.serializers import UserSerializer


class RestaurantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Restaurant
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "logo",
            "cover",
            "phone",
            "email",
            "address",
            "city",
            "district",
            "latitude",
            "longitude",
            "status",
            "delivery_fee",
            "min_delivery_amount",
            "estimated_prep_minutes",
            "is_accepting_orders",
            "subscription_plan",
            "created_at",
        )
        read_only_fields = ("id", "slug", "created_at")


class RestaurantPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Restaurant
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "logo",
            "cover",
            "phone",
            "address",
            "city",
            "district",
            "delivery_fee",
            "min_delivery_amount",
            "estimated_prep_minutes",
            "is_accepting_orders",
        )


class EmployeeSerializer(serializers.ModelSerializer):
    user_detail = UserSerializer(source="user", read_only=True)

    class Meta:
        model = Employee
        fields = (
            "id",
            "user",
            "user_detail",
            "restaurant",
            "role",
            "status",
            "is_active",
            "hired_at",
        )
        read_only_fields = ("id", "is_active", "restaurant")
