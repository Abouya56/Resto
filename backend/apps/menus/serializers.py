from rest_framework import serializers

from apps.menus.models import Category, Product


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "restaurant", "name", "description", "sort_order", "is_active")
        read_only_fields = ("id", "restaurant")


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "restaurant",
            "category",
            "category_name",
            "name",
            "description",
            "price",
            "image",
            "is_available",
            "is_active",
            "prep_minutes",
        )
        read_only_fields = ("id", "restaurant")

    def validate(self, attrs):
        request = self.context.get("request")
        restaurant = getattr(self.instance, "restaurant", None) or getattr(request, "current_restaurant", None)
        category = attrs.get("category") or getattr(self.instance, "category", None)
        if restaurant and category and category.restaurant_id != restaurant.id:
            raise serializers.ValidationError("La catégorie n'appartient pas à ce restaurant.")
        return attrs


class PublicProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ("id", "name", "description", "price", "image", "prep_minutes", "category")
