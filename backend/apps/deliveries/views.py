from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from apps.core.mixins import DriverRequiredMixin, ManagerRequiredMixin, RestaurantContextMixin
from apps.core.tenancy import require_restaurant_role
from apps.deliveries.models import Delivery
from apps.deliveries.services import assign_driver, driver_transition
from apps.restaurants.models import Employee
from apps.users.roles import Role


class ManagerDeliveryListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    template_name = "manager/deliveries.html"
    context_object_name = "deliveries"

    def get_queryset(self):
        return Delivery.objects.filter(order__restaurant=self.restaurant).select_related("order", "driver")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["drivers"] = Employee.objects.filter(
            restaurant=self.restaurant, role=Role.DRIVER, is_active=True
        ).select_related("user")
        return context


@login_required
@require_POST
def assign_delivery(request, pk):
    delivery = get_object_or_404(Delivery.objects.select_related("order"), pk=pk)
    require_restaurant_role(request.user, delivery.order.restaurant, (Role.MANAGER,))
    from apps.users.models import User

    driver = get_object_or_404(User, pk=request.POST.get("driver_id"))
    try:
        assign_driver(delivery, driver)
        messages.success(request, "Livreur attribué.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("deliveries:manage")


class DriverDeliveryListView(DriverRequiredMixin, ListView):
    template_name = "driver/list.html"
    context_object_name = "deliveries"

    def get_queryset(self):
        return Delivery.objects.filter(driver=self.request.user).select_related("order", "order__restaurant")


class DriverDeliveryDetailView(DriverRequiredMixin, DetailView):
    template_name = "driver/detail.html"
    context_object_name = "delivery"

    def get_queryset(self):
        return Delivery.objects.filter(driver=self.request.user).select_related("order", "order__restaurant")


@login_required
@require_POST
def driver_status(request, pk):
    delivery = get_object_or_404(Delivery, pk=pk, driver=request.user)
    try:
        driver_transition(delivery, request.POST.get("status"), request.user)
        messages.success(request, "Statut de livraison mis à jour.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("deliveries:detail", pk=delivery.pk)
