from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.core.tenancy import (
    get_user_restaurant_ids,
    is_platform_admin,
    user_can_access_restaurant,
    user_has_restaurant_role,
)
from apps.users.roles import Role


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        return is_platform_admin(request.user)


class IsAuthenticatedCustomer(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsRestaurantStaff(BasePermission):
    """Accès réservé au personnel d'un restaurant (ou admin plateforme)."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if is_platform_admin(user):
            return True
        return user.employments.filter(is_active=True).exists()

    def has_object_permission(self, request, view, obj):
        restaurant = getattr(obj, "restaurant", obj)
        return user_can_access_restaurant(request.user, restaurant)


class HasRestaurantRole(BasePermission):
    allowed_roles = ()

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if is_platform_admin(user):
            return True
        roles = getattr(view, "allowed_roles", self.allowed_roles)
        return user.employments.filter(is_active=True, role__in=roles).exists()

    def has_object_permission(self, request, view, obj):
        restaurant = getattr(obj, "restaurant", obj)
        roles = getattr(view, "allowed_roles", self.allowed_roles)
        return user_has_restaurant_role(request.user, restaurant, roles)


class IsRestaurantManager(HasRestaurantRole):
    allowed_roles = (Role.MANAGER,)


class IsKitchenStaff(HasRestaurantRole):
    allowed_roles = (Role.MANAGER, Role.COOK)


class IsWaiterStaff(HasRestaurantRole):
    allowed_roles = (Role.MANAGER, Role.WAITER)


class IsDriverStaff(HasRestaurantRole):
    allowed_roles = (Role.MANAGER, Role.DRIVER)


class IsOwnerOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        owner = getattr(obj, "customer", None) or getattr(obj, "user", None)
        return owner == request.user or is_platform_admin(request.user)


class RestaurantQuerysetMixin:
    """Filtre systématiquement les querysets sur les restaurants autorisés."""

    restaurant_field = "restaurant"

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if is_platform_admin(user):
            restaurant_id = self.request.query_params.get("restaurant")
            if restaurant_id:
                return qs.filter(**{f"{self.restaurant_field}_id": restaurant_id})
            return qs
        restaurant_ids = get_user_restaurant_ids(user)
        return qs.filter(**{f"{self.restaurant_field}_id__in": restaurant_ids})
