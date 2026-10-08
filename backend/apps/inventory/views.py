from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.mixins import ManagerRequiredMixin, RestaurantContextMixin
from apps.core.tenancy import user_can_access_restaurant
from apps.inventory.forms import StockItemForm, StockMovementForm
from apps.inventory.models import StockItem, StockMovement
from apps.inventory.services import apply_movement


class StockListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    template_name = "manager/stocks.html"
    context_object_name = "items"

    def get_queryset(self):
        return StockItem.objects.filter(restaurant=self.restaurant)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["movement_form"] = StockMovementForm()
        return context


class StockCreateView(ManagerRequiredMixin, RestaurantContextMixin, CreateView):
    form_class = StockItemForm
    template_name = "manager/stock_form.html"
    success_url = reverse_lazy("inventory:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["restaurant"] = self.restaurant
        return kwargs

    def form_valid(self, form):
        form.instance.restaurant = self.restaurant
        messages.success(self.request, "Article de stock ajouté.")
        return super().form_valid(form)


class StockUpdateView(ManagerRequiredMixin, RestaurantContextMixin, UpdateView):
    form_class = StockItemForm
    template_name = "manager/stock_form.html"
    success_url = reverse_lazy("inventory:list")

    def get_queryset(self):
        return StockItem.objects.filter(restaurant=self.restaurant)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["restaurant"] = self.restaurant
        return kwargs


def stock_move(request, pk):
    item = get_object_or_404(StockItem, pk=pk)
    if not user_can_access_restaurant(request.user, item.restaurant):
        messages.error(request, "Accès refusé.")
        return redirect("inventory:list")
    form = StockMovementForm(request.POST)
    if form.is_valid():
        try:
            apply_movement(
                item,
                form.cleaned_data["movement_type"],
                form.cleaned_data["quantity"],
                form.cleaned_data["reason"],
                request.user,
            )
            messages.success(request, "Mouvement enregistré.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    return redirect("inventory:list")


class MovementListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    template_name = "manager/stock_movements.html"
    context_object_name = "movements"

    def get_queryset(self):
        return StockMovement.objects.filter(restaurant=self.restaurant).select_related("item", "user")
