from rest_framework import viewsets

from apps.core.api import CurrentRestaurantAPIMixin
from apps.core.permissions import IsReceptionStaff
from apps.core.tenancy import get_user_restaurant_ids, is_platform_admin
from apps.deliveries.models import Delivery
from apps.deliveries.serializers import DeliverySerializer


class DeliveryViewSet(CurrentRestaurantAPIMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = DeliverySerializer
    permission_classes = [IsReceptionStaff]
    queryset = Delivery.objects.select_related("order", "order__restaurant")
    filterset_fields = ("status",)

    def get_queryset(self):
        qs = Delivery.objects.select_related("order", "order__restaurant")
        user = self.request.user
        if is_platform_admin(user):
            return qs
        return qs.filter(order__restaurant_id__in=get_user_restaurant_ids(user))
