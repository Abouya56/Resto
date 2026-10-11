from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.core.api import CurrentRestaurantAPIMixin
from apps.core.permissions import IsPlatformAdmin, IsRestaurantManager, RestaurantQuerysetMixin
from apps.core.tenancy import get_user_restaurant_ids, is_platform_admin, user_has_restaurant_role
from apps.restaurants.models import Employee, Restaurant, RestaurantStatus
from apps.users.roles import Role
from apps.restaurants.serializers import (
    EmployeeSerializer,
    RestaurantPublicSerializer,
    RestaurantSerializer,
)


class PublicRestaurantViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = RestaurantPublicSerializer
    lookup_field = "slug"
    search_fields = ("name", "city", "district")
    filterset_fields = ("city",)

    def get_queryset(self):
        return Restaurant.objects.filter(status=RestaurantStatus.ACTIVE)


class RestaurantViewSet(viewsets.ModelViewSet):
    serializer_class = RestaurantSerializer
    search_fields = ("name", "city")
    filterset_fields = ("status", "city")

    def get_permissions(self):
        if self.action in ("create", "destroy"):
            return [IsPlatformAdmin()]
        if self.action in ("update", "partial_update"):
            return [IsRestaurantManager()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = Restaurant.objects.all()
        user = self.request.user
        if is_platform_admin(user):
            return qs
        return qs.filter(id__in=get_user_restaurant_ids(user))

    def perform_update(self, serializer):
        restaurant = self.get_object()
        if not is_platform_admin(self.request.user) and restaurant.status != RestaurantStatus.ACTIVE:
            raise PermissionDenied("Restaurant en attente de validation.")
        serializer.save()


class EmployeeViewSet(CurrentRestaurantAPIMixin, RestaurantQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = EmployeeSerializer
    permission_classes = [IsRestaurantManager]
    filterset_fields = ("role", "status", "restaurant")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    queryset = Employee.objects.select_related("user", "restaurant")

    def perform_create(self, serializer):
        restaurant = self.request.current_restaurant
        if restaurant is None:
            raise ValidationError("Restaurant actif requis.")
        if not user_has_restaurant_role(self.request.user, restaurant, (Role.MANAGER,)):
            raise PermissionDenied("Seul un gérant de ce restaurant peut gérer l'équipe.")
        serializer.save(restaurant=restaurant)

    def perform_update(self, serializer):
        restaurant = serializer.instance.restaurant
        if not user_has_restaurant_role(self.request.user, restaurant, (Role.MANAGER,)):
            raise PermissionDenied("Seul un gérant de ce restaurant peut gérer l'équipe.")
        serializer.save()

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        employee = self.get_object()
        employee.status = "inactive"
        employee.save()
        return Response(EmployeeSerializer(employee).data)
