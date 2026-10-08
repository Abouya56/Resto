from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api import CurrentRestaurantAPIMixin
from apps.core.permissions import IsRestaurantManager, RestaurantQuerysetMixin
from apps.payments.models import Payment, PaymentStatus
from apps.payments.serializers import PaymentSerializer
from django.utils import timezone


class PaymentViewSet(CurrentRestaurantAPIMixin, RestaurantQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [IsRestaurantManager]
    queryset = Payment.objects.select_related("order", "order__restaurant")
    restaurant_field = "order__restaurant"
    filterset_fields = ("status", "method")

    @action(detail=True, methods=["post"])
    def mark_paid(self, request, pk=None):
        payment = self.get_object()
        payment.status = PaymentStatus.PAID
        payment.paid_at = timezone.now()
        payment.save(update_fields=["status", "paid_at", "updated_at"])
        return Response(PaymentSerializer(payment).data)
