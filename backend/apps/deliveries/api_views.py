from django.core.exceptions import ValidationError
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api import CurrentRestaurantAPIMixin
from apps.core.permissions import IsDriverStaff, IsRestaurantManager
from apps.core.tenancy import get_user_restaurant_ids, is_platform_admin
from apps.deliveries.models import Delivery
from apps.deliveries.serializers import DeliverySerializer
from apps.deliveries.services import assign_driver, driver_transition
from apps.users.models import User
from apps.users.roles import Role


class DeliveryViewSet(CurrentRestaurantAPIMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = DeliverySerializer
    permission_classes = [IsDriverStaff]
    queryset = Delivery.objects.select_related("order", "order__restaurant", "driver")
    filterset_fields = ("status", "driver")

    def get_queryset(self):
        user = self.request.user
        qs = Delivery.objects.select_related("order", "order__restaurant", "driver")
        if is_platform_admin(user):
            return qs
        restaurant_ids = get_user_restaurant_ids(user)
        is_manager = user.employments.filter(is_active=True, role=Role.MANAGER).exists()
        if is_manager:
            return qs.filter(order__restaurant_id__in=restaurant_ids)
        return qs.filter(driver=user, order__restaurant_id__in=restaurant_ids)

    @action(detail=True, methods=["post"], permission_classes=[IsRestaurantManager])
    def assign(self, request, pk=None):
        delivery = self.get_object()
        driver = User.objects.filter(pk=request.data.get("driver_id")).first()
        if not driver:
            return Response({"detail": "Livreur introuvable."}, status=404)
        try:
            assign_driver(delivery, driver)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=400)
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        delivery = self.get_object()
        try:
            driver_transition(delivery, request.data.get("status"), request.user)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=400)
        return Response(DeliverySerializer(delivery).data)
