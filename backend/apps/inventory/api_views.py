from django.core.exceptions import ValidationError
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as APIValidationError
from rest_framework.response import Response

from apps.core.api import CurrentRestaurantAPIMixin
from apps.core.permissions import IsRestaurantManager, RestaurantQuerysetMixin
from apps.inventory.feature import StockEnabledPermission
from apps.inventory.models import StockItem, StockMovement
from apps.inventory.serializers import StockItemSerializer, StockMovementSerializer
from apps.inventory.services import apply_movement


class StockItemViewSet(CurrentRestaurantAPIMixin, RestaurantQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = StockItemSerializer
    permission_classes = [StockEnabledPermission, IsRestaurantManager]
    queryset = StockItem.objects.all()
    search_fields = ("name",)
    filterset_fields = ("is_active",)

    def perform_create(self, serializer):
        restaurant = self.request.current_restaurant
        if restaurant is None:
            raise APIValidationError("Restaurant actif requis.")
        serializer.save(restaurant=restaurant)

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        item = self.get_object()
        serializer = StockMovementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            movement = apply_movement(
                item,
                serializer.validated_data["movement_type"],
                serializer.validated_data["quantity"],
                serializer.validated_data["reason"],
                request.user,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=400)
        return Response(StockMovementSerializer(movement).data)


class StockMovementViewSet(RestaurantQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = StockMovementSerializer
    permission_classes = [StockEnabledPermission, IsRestaurantManager]
    queryset = StockMovement.objects.select_related("item", "user")
    filterset_fields = ("movement_type", "item")
