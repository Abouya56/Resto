from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView, View

from apps.core.mixins import KitchenRequiredMixin, ManagerRequiredMixin, RestaurantContextMixin, WaiterRequiredMixin
from apps.core.tenancy import user_can_access_restaurant
from apps.deliveries.services import ensure_delivery
from apps.finance.services import dashboard_metrics
from apps.inventory.models import StockItem
from apps.menus.models import Category, Product
from apps.orders.models import CartItem, Order, OrderStatus, OrderType
from apps.orders.services import add_to_cart, checkout_cart, get_or_create_cart, transition_order, update_cart_item
from apps.payments.models import PaymentMethod
from apps.payments.providers import get_payment_provider
from apps.restaurants.models import Restaurant, RestaurantStatus
from apps.tables.models import DiningTable
from apps.users.models import CustomerAddress


def _public_restaurant(slug):
    return get_object_or_404(Restaurant, slug=slug, status=RestaurantStatus.ACTIVE)


class MenuView(TemplateView):
    template_name = "client/menu.html"

    def get_context_data(self, **kwargs):
        restaurant = _public_restaurant(self.kwargs["restaurant_slug"])
        order_type = self.request.GET.get("type", OrderType.TAKEAWAY)
        if order_type not in OrderType.values:
            order_type = OrderType.TAKEAWAY
        cart = get_or_create_cart(self.request, restaurant, order_type=order_type)
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "restaurant": restaurant,
                "categories": Category.objects.filter(restaurant=restaurant, is_active=True).prefetch_related(
                    "products"
                ),
                "cart": cart,
                "order_type": order_type,
                "table": None,
            }
        )
        return context


class TableMenuView(TemplateView):
    template_name = "client/menu.html"

    def get_context_data(self, **kwargs):
        restaurant = _public_restaurant(self.kwargs["restaurant_slug"])
        table = get_object_or_404(
            DiningTable,
            pk=self.kwargs["table_id"],
            restaurant=restaurant,
            is_active=True,
        )
        cart = get_or_create_cart(self.request, restaurant, table=table, order_type=OrderType.DINE_IN)
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "restaurant": restaurant,
                "categories": Category.objects.filter(restaurant=restaurant, is_active=True).prefetch_related(
                    "products"
                ),
                "cart": cart,
                "order_type": OrderType.DINE_IN,
                "table": table,
            }
        )
        return context


def _active_cart(request):
    restaurant_id = request.POST.get("restaurant") or request.GET.get("restaurant") or request.session.get("cart_restaurant_id")
    if not restaurant_id:
        return None
    restaurant = get_object_or_404(Restaurant, pk=restaurant_id)
    request.session["cart_restaurant_id"] = restaurant.pk
    return get_or_create_cart(request, restaurant)


@require_POST
def add_item(request):
    from apps.menus.models import Product

    restaurant = get_object_or_404(Restaurant, pk=request.POST.get("restaurant"))
    product = get_object_or_404(Product, pk=request.POST.get("product"), restaurant=restaurant)
    table = None
    if request.POST.get("table"):
        table = get_object_or_404(DiningTable, pk=request.POST.get("table"), restaurant=restaurant)
    order_type = request.POST.get("order_type") or (OrderType.DINE_IN if table else OrderType.TAKEAWAY)
    cart = get_or_create_cart(request, restaurant, table=table, order_type=order_type)
    request.session["cart_restaurant_id"] = restaurant.pk
    try:
        add_to_cart(cart, product, int(request.POST.get("quantity", 1)), request.POST.get("note", ""))
        messages.success(request, f"{product.name} ajouté au panier.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(request.POST.get("next") or reverse("orders:cart"))


@require_POST
def update_item(request, pk):
    item = get_object_or_404(CartItem, pk=pk)
    update_cart_item(item, quantity=int(request.POST.get("quantity", item.quantity)), note=request.POST.get("note"))
    return redirect("orders:cart")


@require_POST
def remove_item(request, pk):
    item = get_object_or_404(CartItem, pk=pk)
    item.delete()
    messages.info(request, "Article retiré.")
    return redirect("orders:cart")


class CartView(TemplateView):
    template_name = "client/cart.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cart"] = _active_cart(self.request)
        return context


class CheckoutView(View):
    template_name = "client/checkout.html"

    def get(self, request):
        cart = _active_cart(request)
        if cart is None or not cart.items.exists():
            messages.warning(request, "Votre panier est vide.")
            return redirect("restaurants:list")
        addresses = request.user.addresses.all() if request.user.is_authenticated else []
        return render(
            request,
            self.template_name,
            {"cart": cart, "addresses": addresses, "methods": PaymentMethod.choices},
        )

    def post(self, request):
        cart = _active_cart(request)
        if cart is None:
            return redirect("restaurants:list")
        address = None
        address_text = request.POST.get("address_text", "")
        if request.POST.get("address_id") and request.user.is_authenticated:
            address = CustomerAddress.objects.filter(
                pk=request.POST.get("address_id"), customer=request.user
            ).first()
        try:
            if request.POST.get("order_type") in OrderType.values:
                cart.order_type = request.POST.get("order_type")
                cart.save(update_fields=["order_type"])
            order = checkout_cart(
                cart,
                customer=request.user if request.user.is_authenticated else None,
                address=address,
                address_text=address_text,
                note=request.POST.get("note", ""),
            )
            if order.order_type == OrderType.DELIVERY:
                ensure_delivery(order)
            provider = get_payment_provider()
            method = request.POST.get("payment_method") or PaymentMethod.SIMULATED
            if method in (PaymentMethod.CASH_ON_SITE, PaymentMethod.CASH_ON_DELIVERY):
                from apps.payments.providers import CashPaymentProvider

                CashPaymentProvider().charge(order, method=method)
            else:
                provider.charge(order, method=method)
            request.session["last_order_id"] = order.pk
            messages.success(request, f"Commande {order.number} enregistrée.")
            return redirect("orders:detail", pk=order.pk)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("orders:checkout")


class OrderHistoryView(LoginRequiredMixin, ListView):
    template_name = "client/history.html"
    context_object_name = "orders"

    def get_queryset(self):
        return Order.objects.filter(customer=self.request.user).prefetch_related("items")


class OrderDetailView(DetailView):
    template_name = "client/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return Order.objects.select_related("restaurant", "table").prefetch_related("items", "payments")

    def get_object(self, queryset=None):
        order = super().get_object(queryset)
        user = self.request.user
        if user.is_authenticated and (order.customer_id == user.id or user_can_access_restaurant(user, order.restaurant)):
            return order
        if not user.is_authenticated and self.request.session.get("last_order_id") == order.pk:
            return order
        raise PermissionDenied("Vous ne pouvez pas consulter cette commande.")


class ManagerDashboardView(ManagerRequiredMixin, RestaurantContextMixin, TemplateView):
    template_name = "manager/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        metrics = dashboard_metrics(self.restaurant, self.request.GET.get("period", "today"))
        context["metrics"] = metrics
        context["low_stocks"] = StockItem.objects.filter(restaurant=self.restaurant, is_active=True)
        context["low_stocks"] = [s for s in context["low_stocks"] if s.is_low][:6]
        context["recent_orders"] = Order.objects.filter(restaurant=self.restaurant)[:8]
        context["product_count"] = Product.objects.filter(restaurant=self.restaurant).count()
        context["table_count"] = DiningTable.objects.filter(restaurant=self.restaurant).count()
        context["employee_count"] = self.restaurant.employees.count()
        return context


class ManagerOrderListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    template_name = "manager/orders.html"
    context_object_name = "orders"

    def get_queryset(self):
        qs = Order.objects.filter(restaurant=self.restaurant).prefetch_related("items")
        status = self.request.GET.get("status")
        order_type = self.request.GET.get("type")
        if status:
            qs = qs.filter(status=status)
        if order_type:
            qs = qs.filter(order_type=order_type)
        return qs


class ManagerOrderDetailView(ManagerRequiredMixin, RestaurantContextMixin, DetailView):
    template_name = "manager/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return Order.objects.filter(restaurant=self.restaurant).prefetch_related("items", "payments")


@require_POST
def change_status(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if not user_can_access_restaurant(request.user, order.restaurant):
        raise PermissionDenied()
    try:
        transition_order(order, request.POST.get("status"), request.user)
        messages.success(request, f"Commande {order.number} : {order.get_status_display()}.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(request.POST.get("next") or reverse("orders:manager_order", args=[order.pk]))


class KitchenBoardView(KitchenRequiredMixin, RestaurantContextMixin, TemplateView):
    template_name = "kitchen/board.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = Order.objects.filter(restaurant=self.restaurant).exclude(
            status__in=[OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.SERVED, OrderStatus.PICKED_UP, OrderStatus.DELIVERED]
        )
        context["pending"] = qs.filter(status__in=[OrderStatus.PENDING, OrderStatus.ACCEPTED])
        context["preparing"] = qs.filter(status=OrderStatus.PREPARING)
        context["ready"] = qs.filter(status=OrderStatus.READY)
        return context


class WaiterBoardView(WaiterRequiredMixin, RestaurantContextMixin, TemplateView):
    template_name = "waiter/board.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        qs = Order.objects.filter(
            restaurant=self.restaurant,
            order_type=OrderType.DINE_IN,
            created_at__date=today,
        ).select_related("table")
        context["tables"] = DiningTable.objects.filter(restaurant=self.restaurant, is_active=True)
        context["ready"] = qs.filter(status=OrderStatus.READY)
        context["served"] = qs.filter(status=OrderStatus.SERVED)
        context["active"] = qs.exclude(status__in=[OrderStatus.COMPLETED, OrderStatus.CANCELLED])
        return context
