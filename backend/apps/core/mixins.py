from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect

from apps.core.tenancy import (
    is_platform_admin,
    user_can_access_restaurant,
    user_has_restaurant_role,
)
from apps.restaurants.models import Restaurant, RestaurantStatus
from apps.users.roles import Role


class RestaurantFormKwargsMixin:
    """Transmet le restaurant courant au formulaire (à placer avant CreateView/UpdateView)."""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["restaurant"] = self.restaurant
        return kwargs


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_roles = (Role.MANAGER, Role.RECEPTION)

    def test_func(self):
        user = self.request.user
        if is_platform_admin(user):
            return True
        return user.employments.filter(is_active=True, role__in=self.allowed_roles).exists()


class ManagerRequiredMixin(StaffRequiredMixin):
    allowed_roles = (Role.MANAGER,)


class ReceptionRequiredMixin(StaffRequiredMixin):
    allowed_roles = (Role.MANAGER, Role.RECEPTION)


class PlatformAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return is_platform_admin(self.request.user)


class RestaurantContextMixin:
    """Résout le restaurant courant et refuse l'accès inter-établissements."""

    restaurant_url_kwarg = "restaurant_id"
    allow_incomplete_profile = False

    def get_restaurant(self):
        user = self.request.user
        roles = getattr(self, "allowed_roles", None)
        explicit_id = self.kwargs.get(self.restaurant_url_kwarg) or self.request.GET.get("restaurant")
        restaurant_id = explicit_id or self.request.session.get("current_restaurant_id")
        restaurant = getattr(self.request, "current_restaurant", None)
        if restaurant_id:
            restaurant = get_object_or_404(Restaurant, pk=restaurant_id)
        if not explicit_id and roles and not is_platform_admin(user):
            # Sans choix explicite, on bascule sur un établissement où l'utilisateur a le bon rôle.
            if restaurant is None or not user_has_restaurant_role(user, restaurant, roles):
                employment = (
                    user.employments.filter(is_active=True, role__in=roles).select_related("restaurant").first()
                )
                restaurant = employment.restaurant if employment else restaurant
        if restaurant is None and is_platform_admin(user):
            restaurant = Restaurant.objects.order_by("name").first()
        if restaurant is None:
            raise PermissionDenied("Aucun restaurant actif.")
        if not user_can_access_restaurant(user, restaurant):
            raise PermissionDenied("Accès refusé à ce restaurant.")
        if roles and not user_has_restaurant_role(user, restaurant, roles):
            raise PermissionDenied("Votre rôle ne donne pas accès à cette page dans ce restaurant.")
        self.request.session["current_restaurant_id"] = restaurant.pk
        return restaurant

    def dispatch(self, request, *args, **kwargs):
        self.restaurant = self.get_restaurant()
        if not is_platform_admin(request.user):
            if self.restaurant.status != RestaurantStatus.ACTIVE:
                return redirect("restaurants:pending")
            if not self.restaurant.is_profile_complete and not self.allow_incomplete_profile:
                messages.info(
                    request,
                    "Renseignez d'abord les informations de votre restaurant.",
                )
                return redirect("restaurants:manage")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["restaurant"] = self.restaurant
        return context
