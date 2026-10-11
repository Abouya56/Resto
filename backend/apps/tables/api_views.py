from django.http import FileResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.api import CurrentRestaurantAPIMixin
from apps.core.permissions import IsRestaurantManager, IsWaiterStaff, RestaurantQuerysetMixin
from apps.tables.models import DiningTable
from apps.tables.serializers import DiningTableSerializer, QRCodeSerializer
from apps.tables.services import ensure_qrcode, regenerate_qrcode


class DiningTableViewSet(CurrentRestaurantAPIMixin, RestaurantQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = DiningTableSerializer
    queryset = DiningTable.objects.select_related("restaurant", "qrcode")
    filterset_fields = ("status", "is_active", "restaurant")
    search_fields = ("number",)

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsWaiterStaff()]
        return [IsRestaurantManager()]

    def perform_create(self, serializer):
        restaurant = self.request.current_restaurant
        if restaurant is None:
            raise ValidationError("Restaurant actif requis.")
        table = serializer.save(restaurant=restaurant)
        ensure_qrcode(table)

    @action(detail=True, methods=["post"], permission_classes=[IsRestaurantManager])
    def generate_qr(self, request, pk=None):
        table = self.get_object()
        qr = ensure_qrcode(table)
        return Response(QRCodeSerializer(qr).data)

    @action(detail=True, methods=["post"], permission_classes=[IsRestaurantManager])
    def regenerate_qr(self, request, pk=None):
        table = self.get_object()
        qr = regenerate_qrcode(table)
        return Response(QRCodeSerializer(qr).data)

    @action(detail=True, methods=["get"], permission_classes=[IsRestaurantManager])
    def download_qr(self, request, pk=None):
        table = self.get_object()
        qr = ensure_qrcode(table)
        return FileResponse(qr.image.open("rb"), as_attachment=True, filename=f"qr-{table.number}.png")
