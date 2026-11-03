from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.mixins import ManagerRequiredMixin, RestaurantContextMixin, RestaurantFormKwargsMixin
from apps.core.tenancy import require_restaurant_role
from apps.inventory.feature import stock_enabled
from apps.menus.forms import CategoryForm, ProductForm
from apps.menus.models import Category, Product
from apps.orders.models import OrderItem, OrderStatus
from apps.users.roles import Role


def ordered_categories(restaurant):
    """Catégories dans l'ordre de la carte, numérotées 0, 1, 2… sans trou ni doublon."""
    categories = list(Category.objects.filter(restaurant=restaurant).order_by("sort_order", "name", "pk"))
    for position, category in enumerate(categories):
        if category.sort_order != position:
            category.sort_order = position
            category.save(update_fields=["sort_order", "updated_at"])
    return categories


class CategoryListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    """La carte vue par le gérant : l'ordre des rubriques, leurs plats, ce qui est visible ou non."""

    template_name = "manager/categories.html"
    context_object_name = "categories"

    def get_queryset(self):
        categories = ordered_categories(self.restaurant)
        products = Product.objects.filter(restaurant=self.restaurant, is_active=True).order_by("name")
        by_category = {}
        for product in products:
            by_category.setdefault(product.category_id, []).append(product)
        for category in categories:
            dishes = by_category.get(category.pk, [])
            category.dishes = dishes
            category.visible_count = sum(1 for p in dishes if p.is_available and not p.sold_out)
            category.preview = dishes[:5]
        return categories

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["shown_count"] = sum(1 for c in context["categories"] if c.is_active and c.visible_count)
        return context


def _owned_category(request, pk):
    category = get_object_or_404(Category, pk=pk)
    require_restaurant_role(request.user, category.restaurant, (Role.MANAGER,))
    return category


@login_required
@require_POST
def move_category(request, pk):
    category = _owned_category(request, pk)
    categories = ordered_categories(category.restaurant)
    index = next(i for i, c in enumerate(categories) if c.pk == category.pk)
    target = index - 1 if request.POST.get("direction") == "up" else index + 1
    if 0 <= target < len(categories):
        other = categories[target]
        category.sort_order, other.sort_order = other.sort_order, categories[index].sort_order
        category.save(update_fields=["sort_order", "updated_at"])
        other.save(update_fields=["sort_order", "updated_at"])
    return redirect(f"{reverse('menus:categories')}#categorie-{category.pk}")


@login_required
@require_POST
def toggle_category(request, pk):
    category = _owned_category(request, pk)
    category.is_active = not category.is_active
    category.save(update_fields=["is_active", "updated_at"])
    if category.is_active:
        messages.success(request, f"« {category.name} » est de nouveau visible sur la carte.")
    else:
        messages.success(request, f"« {category.name} » est cachée : ses plats n'apparaissent plus aux clients.")
    return redirect(f"{reverse('menus:categories')}#categorie-{category.pk}")


@login_required
@require_POST
def delete_category(request, pk):
    category = _owned_category(request, pk)
    if category.products.exists():
        messages.error(request, f"« {category.name} » contient encore des plats : déplacez-les ou cachez la catégorie.")
    else:
        category.delete()
        messages.success(request, f"Catégorie « {category.name} » supprimée.")
    return redirect("menus:categories")


class CategoryCreateView(ManagerRequiredMixin, RestaurantContextMixin, RestaurantFormKwargsMixin, CreateView):
    form_class = CategoryForm
    template_name = "manager/category_form.html"
    success_url = reverse_lazy("menus:categories")

    def form_valid(self, form):
        form.instance.restaurant = self.restaurant
        last = Category.objects.filter(restaurant=self.restaurant).aggregate(last=Max("sort_order"))["last"]
        form.instance.sort_order = 0 if last is None else last + 1  # à la fin de la carte
        messages.success(self.request, f"Catégorie « {form.instance.name} » créée, en dernière position.")
        return super().form_valid(form)


class CategoryUpdateView(ManagerRequiredMixin, RestaurantContextMixin, RestaurantFormKwargsMixin, UpdateView):
    form_class = CategoryForm
    template_name = "manager/category_form.html"
    success_url = reverse_lazy("menus:categories")

    def get_queryset(self):
        return Category.objects.filter(restaurant=self.restaurant)

    def form_valid(self, form):
        messages.success(self.request, f"Catégorie « {form.instance.name} » enregistrée.")
        return super().form_valid(form)


PRODUCT_FILTERS = (
    ("indisponibles", "Indisponibles"),
    ("epuises", "Épuisés (stock)"),
    ("sans-photo", "Sans photo"),
    ("non-relies", "Non reliés au stock"),
    ("retires", "Retirés de la carte"),
)


class ProductListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    """La carte complète, rangée par catégorie, avec ce qu'il faut voir d'un coup d'œil pour chaque plat."""

    template_name = "manager/products.html"
    context_object_name = "products"

    def base_queryset(self):
        return Product.objects.filter(restaurant=self.restaurant, is_active=True)

    def get_queryset(self):
        params = self.request.GET
        self.state = params.get("etat", "")
        if self.state in ("epuises", "non-relies") and not stock_enabled():
            self.state = ""  # filtres du stock : inexistants quand le stock n'est pas suivi
        if self.state == "retires":
            qs = Product.objects.filter(restaurant=self.restaurant, is_active=False)
        else:
            qs = self.base_queryset()
        self.category = None
        category_id = params.get("categorie", "")
        if category_id.isdigit():
            self.category = Category.objects.filter(restaurant=self.restaurant, pk=category_id).first()
            if self.category:
                qs = qs.filter(category=self.category)
        if self.state == "indisponibles":
            qs = qs.filter(is_available=False)
        elif self.state == "epuises":
            qs = qs.filter(out_of_stock=True)
        elif self.state == "sans-photo":
            qs = qs.filter(Q(image="") | Q(image__isnull=True))
        elif self.state == "non-relies":
            qs = qs.filter(recipe_items__isnull=True)
        elif self.state != "retires":
            self.state = ""
        self.q = params.get("q", "").strip()[:60]
        if self.q:
            qs = qs.filter(Q(name__icontains=self.q) | Q(description__icontains=self.q))
        return (
            qs.select_related("category")
            .prefetch_related("recipe_items__stock_item")
            .order_by("category__sort_order", "category__name", "name")
            .distinct()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        products = list(context["products"])
        week_ago = timezone.now() - timedelta(days=7)
        sold = dict(
            OrderItem.objects.filter(
                order__restaurant=self.restaurant, order__created_at__gte=week_ago, product__in=products
            )
            .exclude(order__status=OrderStatus.CANCELLED)
            .order_by()
            .values_list("product_id")
            .annotate(total=Sum("quantity"))
        )
        groups = []
        for product in products:
            links = list(product.recipe_items.all())
            product.stock_links = links
            # « Encore N » : combien de fois on peut encore vendre ce plat avec le stock actuel.
            product.enough_for = (
                min(max(int(link.stock_item.quantity // link.quantity), 0) for link in links) if links else None
            )
            product.sold_week = sold.get(product.pk, 0)
            if not groups or groups[-1]["category"].pk != product.category_id:
                groups.append({"category": product.category, "products": []})
            groups[-1]["products"].append(product)
        base = self.base_queryset()
        context.update(
            {
                "groups": groups,
                "current_category": self.category,
                "state": self.state,
                "q": self.q,
                "total_count": base.count(),
                "categories": Category.objects.filter(restaurant=self.restaurant)
                .annotate(n=Count("products", filter=Q(products__is_active=True)))
                .order_by("sort_order", "name"),
                "filters": [
                    {
                        "key": key,
                        "label": label,
                        "count": {
                            "indisponibles": base.filter(is_available=False),
                            "epuises": base.filter(out_of_stock=True),
                            "sans-photo": base.filter(Q(image="") | Q(image__isnull=True)),
                            "non-relies": base.filter(recipe_items__isnull=True),
                            "retires": Product.objects.filter(restaurant=self.restaurant, is_active=False),
                        }[key]
                        .distinct()
                        .count(),
                    }
                    for key, label in PRODUCT_FILTERS
                    if stock_enabled() or key not in ("epuises", "non-relies")
                ],
            }
        )
        return context


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
    product.save(update_fields=["is_available", "updated_at"])
    if product.is_available:
        messages.success(request, f"{product.name} est de nouveau proposé aux clients.")
    else:
        messages.success(request, f"{product.name} est indisponible : les clients ne le voient plus.")
    target = request.POST.get("next") or ""
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        target = reverse("menus:products")
    return redirect(f"{target}#plat-{product.pk}")
