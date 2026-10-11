from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.mixins import ManagerRequiredMixin, RestaurantContextMixin, RestaurantFormKwargsMixin
from apps.core.tenancy import require_restaurant_role
from apps.menus.forms import CategoryForm, ProductForm
from apps.menus.models import Category, Product
from apps.users.roles import Role


class CategoryListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    template_name = "manager/categories.html"
    context_object_name = "categories"

    def get_queryset(self):
        return Category.objects.filter(restaurant=self.restaurant)


class CategoryCreateView(ManagerRequiredMixin, RestaurantContextMixin, RestaurantFormKwargsMixin, CreateView):
    form_class = CategoryForm
    template_name = "manager/category_form.html"
    success_url = reverse_lazy("menus:categories")

    def form_valid(self, form):
        form.instance.restaurant = self.restaurant
        messages.success(self.request, "Catégorie créée.")
        return super().form_valid(form)


class CategoryUpdateView(ManagerRequiredMixin, RestaurantContextMixin, RestaurantFormKwargsMixin, UpdateView):
    form_class = CategoryForm
    template_name = "manager/category_form.html"
    success_url = reverse_lazy("menus:categories")

    def get_queryset(self):
        return Category.objects.filter(restaurant=self.restaurant)


class ProductListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    template_name = "manager/products.html"
    context_object_name = "products"

    def get_queryset(self):
        return Product.objects.filter(restaurant=self.restaurant).select_related("category")


class ProductCreateView(ManagerRequiredMixin, RestaurantContextMixin, CreateView):
    form_class = ProductForm
    template_name = "manager/product_form.html"
    success_url = reverse_lazy("menus:products")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["restaurant"] = self.restaurant
        return kwargs

    def form_valid(self, form):
        form.instance.restaurant = self.restaurant
        messages.success(self.request, "Produit créé.")
        return super().form_valid(form)


class ProductUpdateView(ManagerRequiredMixin, RestaurantContextMixin, UpdateView):
    form_class = ProductForm
    template_name = "manager/product_form.html"
    success_url = reverse_lazy("menus:products")

    def get_queryset(self):
        return Product.objects.filter(restaurant=self.restaurant)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["restaurant"] = self.restaurant
        return kwargs


@login_required
@require_POST
def toggle_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    require_restaurant_role(request.user, product.restaurant, (Role.MANAGER,))
    product.is_available = not product.is_available
    product.save(update_fields=["is_available"])
    messages.success(request, f"{product.name} : disponibilité mise à jour.")
    return redirect("menus:products")
