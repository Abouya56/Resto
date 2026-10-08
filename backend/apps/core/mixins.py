from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from apps.core.tenancy import (
    is_platform_admin,
    user_can_access_restaurant,
    user_has_restaurant_role,
)
from apps.restaurants.models import Restaurant
from apps.users.roles import Role


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_roles = (Role.MANAGER, Role.COOK, Role.WAITER, Role.DRIVER)

    def test_func(self):
        user = self.request.user
        if is_platform_admin(user):
            return True
        return user.employments.filter(is_active=True, role__in=self.allowed_roles).exists()


class ManagerRequiredMixin(StaffRequiredMixin):
    allowed_roles = (Role.MANAGER,)


class KitchenRequiredMixin(StaffRequiredMixin):
    allowed_roles = (Role.MANAGER, Role.COOK)


class WaiterRequiredMixin(StaffRequiredMixin):
    allowed_roles = (Role.MANAGER, Role.WAITER)


class DriverRequiredMixin(StaffRequiredMixin):
    allowed_roles = (Role.MANAGER, Role.DRIVER)


class PlatformAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return is_platform_admin(self.request.user)


class RestaurantContextMixin:
    """Résout le restaurant courant et refuse l'accès inter-établissements."""

    restaurant_url_kwarg = "restaurant_id"

    def get_restaurant(self):
        restaurant = getattr(self.request, "current_restaurant", None)
        restaurant_id = (
            self.kwargs.get(self.restaurant_url_kwarg)
            or self.request.GET.get("restaurant")
            or self.request.session.get("current_restaurant_id")
        )
        if restaurant_id:
            restaurant = get_object_or_404(Restaurant, pk=restaurant_id)
        if restaurant is None and is_platform_admin(self.request.user):
            restaurant = Restaurant.objects.order_by("name").first()
        if restaurant is None:
            raise PermissionDenied("Aucun restaurant actif.")
        if not user_can_access_restaurant(self.request.user, restaurant):
            raise PermissionDenied("Accès refusé à ce restaurant.")
        self.request.session["current_restaurant_id"] = restaurant.pk
        return restaurant

    def dispatch(self, request, *args, **kwargs):
        self.restaurant = self.get_restaurant()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["restaurant"] = self.restaurant
        return context


class RoleRestaurantMixin(RestaurantContextMixin):
    allowed_roles = (Role.MANAGER,)

    def dispatch(self, request, *args, **kwargs):
        self.restaurant = self.get_restaurant()
        if not user_has_restaurant_role(request.user, self.restaurant, self.allowed_roles):
            raise PermissionDenied("Rôle insuffisant pour cette action.")
        return super(RestaurantContextMixin, self).dispatch(request, *args, **kwargs)
