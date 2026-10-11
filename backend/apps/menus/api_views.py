from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api import CurrentRestaurantAPIMixin
from apps.core.permissions import IsRestaurantManager, RestaurantQuerysetMixin
from apps.menus.models import Category, Product
from apps.menus.serializers import CategorySerializer, ProductSerializer, PublicProductSerializer
from apps.restaurants.models import RestaurantStatus


class CategoryViewSet(CurrentRestaurantAPIMixin, RestaurantQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsRestaurantManager]
    queryset = Category.objects.all()
    filterset_fields = ("is_active", "restaurant")
    search_fields = ("name",)

    def perform_create(self, serializer):
        restaurant = self.request.current_restaurant
        if restaurant is None:
            from rest_framework.exceptions import ValidationError

            raise ValidationError("Restaurant actif requis.")
        serializer.save(restaurant=restaurant)


class ProductViewSet(CurrentRestaurantAPIMixin, RestaurantQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsRestaurantManager]
    queryset = Product.objects.select_related("category", "restaurant")
    filterset_fields = ("is_available", "is_active", "category", "restaurant")
    search_fields = ("name", "description")

    def perform_create(self, serializer):
        restaurant = self.request.current_restaurant
        if restaurant is None:
            from rest_framework.exceptions import ValidationError

            raise ValidationError("Restaurant actif requis.")
        serializer.save(restaurant=restaurant)

    @action(detail=True, methods=["post"])
    def toggle_availability(self, request, pk=None):
        product = self.get_object()
        product.is_available = not product.is_available
        product.save(update_fields=["is_available", "updated_at"])
        return Response(ProductSerializer(product).data)


class PublicMenuViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = PublicProductSerializer
    filterset_fields = ("category", "restaurant")
    search_fields = ("name",)

    def get_queryset(self):
        return Product.objects.filter(
            is_active=True,
            is_available=True,
            restaurant__status=RestaurantStatus.ACTIVE,
        ).select_related("category")
