from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.mixins import ManagerRequiredMixin, RestaurantContextMixin
from apps.core.templatetags.resto import qte
from apps.core.tenancy import require_restaurant_role
from apps.inventory.forms import RecipeIngredientForm, StockItemForm, StockMovementForm
from apps.inventory.models import RecipeIngredient, StockItem, StockMovement, StockMovementType
from apps.inventory.services import apply_movement, refresh_product_list, refresh_products
from apps.menus.models import Product
from apps.users.roles import Role


class StockListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    template_name = "manager/stocks.html"
    context_object_name = "items"

    def get_queryset(self):
        return StockItem.objects.filter(restaurant=self.restaurant).prefetch_related(
            Prefetch("recipe_usages", queryset=RecipeIngredient.objects.select_related("product"))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["low_count"] = sum(1 for item in context["items"] if item.is_active and item.is_low)
        context["products_without_recipe"] = Product.objects.filter(
            restaurant=self.restaurant, is_active=True, recipe_items__isnull=True
        ).count()
        return context


class StockCreateView(ManagerRequiredMixin, RestaurantContextMixin, CreateView):
    form_class = StockItemForm
    template_name = "manager/stock_form.html"
    success_url = reverse_lazy("inventory:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["restaurant"] = self.restaurant
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        starting = form.cleaned_data.get("quantity") or 0
        form.instance.restaurant = self.restaurant
        form.instance.quantity = 0
        self.object = form.save()
        if starting:
            # Le stock de départ apparaît dans l'historique comme premier mouvement.
            apply_movement(self.object, StockMovementType.IN, starting, "Stock de départ", self.request.user)
        messages.success(self.request, f"{self.object.name} ajouté au stock.")
        return redirect(self.success_url)


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

    def form_valid(self, form):
        response = super().form_valid(form)
        refresh_products([self.object])
        messages.success(self.request, f"{self.object.name} mis à jour.")
        return response


MOVE_MESSAGES = {
    StockMovementType.IN: "{name} : +{qty} {unit}.",
    StockMovementType.OUT: "{name} : -{qty} {unit}.",
    StockMovementType.ADJUST: "{name} : stock corrigé à {qty} {unit}.",
}


@login_required
@require_POST
def stock_move(request, pk):
    item = get_object_or_404(StockItem, pk=pk)
    require_restaurant_role(request.user, item.restaurant, (Role.MANAGER,))
    form = StockMovementForm(request.POST)
    if not form.is_valid():
        messages.error(request, f"{item.name} : indiquez une quantité valide (ex. 2 ou 0,5).")
        return redirect(f"{reverse('inventory:list')}#article-{item.pk}")
    action = form.cleaned_data["action"]
    quantity = form.cleaned_data["quantity"]
    try:
        apply_movement(item, action, quantity, form.cleaned_data["reason"], request.user)
    except ValidationError as exc:
        messages.error(request, f"{item.name} : {' '.join(exc.messages)}")
    else:
        messages.success(request, MOVE_MESSAGES[action].format(qty=qte(quantity), unit=item.unit, name=item.name))
    return redirect(f"{reverse('inventory:list')}#article-{item.pk}")


class MovementListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    template_name = "manager/stock_movements.html"
    context_object_name = "movements"
    paginate_by = 50

    def get_queryset(self):
        return StockMovement.objects.filter(restaurant=self.restaurant).select_related("item", "user", "order")


class ProductRecipeView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    """La recette d'un plat : les ingrédients retirés du stock pour une portion."""

    template_name = "manager/product_recipe.html"
    context_object_name = "ingredients"

    def get_queryset(self):
        self.product = get_object_or_404(Product, pk=self.kwargs["pk"], restaurant=self.restaurant)
        return self.product.recipe_items.select_related("stock_item").order_by("stock_item__name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ingredients = list(context["ingredients"])
        for ingredient in ingredients:
            # « Il reste de quoi vendre N fois ce plat » : plus parlant qu'une quantité en stock.
            ingredient.enough_for = max(int(ingredient.stock_item.quantity // ingredient.quantity), 0)
        context["ingredients"] = ingredients
        context["enough_for"] = min((i.enough_for for i in ingredients), default=None)
        context["product"] = self.product
        context["form"] = kwargs.get("form") or RecipeIngredientForm(product=self.product)
        stock_items = StockItem.objects.filter(restaurant=self.restaurant, is_active=True)
        context["has_stock_items"] = stock_items.exists()
        context["units"] = {str(item.pk): item.unit for item in stock_items}
        return context

    def post(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        form = RecipeIngredientForm(request.POST, product=self.product)
        if form.is_valid():
            form.save()
            refresh_product_list(Product.objects.filter(pk=self.product.pk))
            messages.success(request, f"{form.instance.stock_item.name} ajouté à la recette.")
            return redirect("inventory:recipe", pk=self.product.pk)
        return render(request, self.template_name, self.get_context_data(form=form))


@login_required
@require_POST
def recipe_remove(request, pk):
    ingredient = get_object_or_404(RecipeIngredient.objects.select_related("product"), pk=pk)
    product = ingredient.product
    require_restaurant_role(request.user, product.restaurant, (Role.MANAGER,))
    ingredient.delete()
    refresh_product_list(Product.objects.filter(pk=product.pk))
    messages.success(request, "Ingrédient retiré de la recette.")
    return redirect("inventory:recipe", pk=product.pk)
