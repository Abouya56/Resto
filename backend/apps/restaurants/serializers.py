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
        read_only_fields = ("id", "slug", "created_at", "status", "subscription_plan")


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

    def validate_user(self, user):
        if self.instance is not None and user != self.instance.user:
            raise serializers.ValidationError("Le compte d'un employé ne peut pas être changé.")
        if user.is_platform_admin or user.is_staff:
            raise serializers.ValidationError("Ce compte ne peut pas être ajouté comme employé.")
        return user

    def validate(self, attrs):
        request = self.context.get("request")
        restaurant = getattr(self.instance, "restaurant", None) or getattr(request, "current_restaurant", None)
        user = attrs.get("user")
        if self.instance is None and restaurant and user:
            if Employee.objects.filter(user=user, restaurant=restaurant).exists():
                raise serializers.ValidationError("Cette personne fait déjà partie de l'équipe.")
        return attrs
