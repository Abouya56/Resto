from collections import Counter

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView, View

from apps.core.mixins import KitchenRequiredMixin, ManagerRequiredMixin, RestaurantContextMixin, WaiterRequiredMixin
from apps.core.tenancy import require_restaurant_role, user_can_access_restaurant
from apps.deliveries.services import ensure_delivery
from apps.finance.services import dashboard_metrics
from apps.inventory.models import StockItem
from apps.menus.models import Category, Product
from apps.orders.forms import CheckoutForm
from apps.orders.models import STATUS_FLOW, Order, OrderStatus, OrderType
from apps.orders.services import (
    add_to_cart,
    checkout_cart,
    find_cart,
    get_or_create_cart,
    owned_cart_item,
    transition_order,
    update_cart_item,
)
from apps.payments.models import PaymentMethod
from apps.payments.services import mark_order_paid
from apps.payments.providers import CashPaymentProvider
from apps.restaurants.models import Restaurant, RestaurantStatus
from apps.tables.models import DiningTable, QRCode
from apps.users.models import CustomerAddress
from apps.users.roles import Role


def _public_restaurant(slug):
    return get_object_or_404(Restaurant, slug=slug, status=RestaurantStatus.ACTIVE)


HOME_ORDER_TYPES = (OrderType.TAKEAWAY, OrderType.DELIVERY)

PAYMENT_BY_TYPE = {
    OrderType.DINE_IN: (PaymentMethod.CASH_ON_SITE, "Vous réglez à table, auprès du serveur."),
    OrderType.TAKEAWAY: (PaymentMethod.CASH_ON_SITE, "Vous réglez au comptoir, en récupérant votre commande."),
    OrderType.DELIVERY: (PaymentMethod.CASH_ON_DELIVERY, "Vous réglez le livreur à la réception."),
}


def ordering_context(request, restaurant, table=None):
    """Tout ce qu'il faut pour commander depuis la page d'un restaurant."""
    if table:
        order_type = OrderType.DINE_IN
        cart = get_or_create_cart(request, restaurant, table=table, order_type=order_type)
    else:
        cart = find_cart(request, restaurant)
        requested = request.GET.get("type")
        if requested in HOME_ORDER_TYPES:
            order_type = requested
        elif cart and cart.order_type in HOME_ORDER_TYPES:
            order_type = cart.order_type
        else:
            order_type = OrderType.TAKEAWAY
        if cart and (cart.order_type != order_type or cart.table_id):
            cart = get_or_create_cart(request, restaurant, order_type=order_type)
    categories = [
        category
        for category in Category.objects.filter(restaurant=restaurant, is_active=True).prefetch_related(
            Prefetch("products", queryset=Product.objects.filter(is_active=True, is_available=True))
        )
        if category.products.all()
    ]
    in_cart = {item.product_id: item.quantity for item in cart.items.all()} if cart else {}
    return {
        "restaurant": restaurant,
        "categories": categories,
        "cart": cart,
        "in_cart": in_cart,
        "order_type": order_type,
        "table": table,
        "payment_hint": PAYMENT_BY_TYPE[order_type][1],
    }


def _safe_next(request, fallback):
    target = request.POST.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback


def _restaurant_url(cart):
    if cart.table_id:
        return cart.table.public_path()
    return f"{reverse('restaurants:detail', args=[cart.restaurant.slug])}?type={cart.order_type}"


class MenuView(View):
    """Ancienne adresse du menu : tout se passe désormais sur la page du restaurant."""

    def get(self, request, restaurant_slug):
        restaurant = _public_restaurant(restaurant_slug)
        order_type = request.GET.get("type")
        url = reverse("restaurants:detail", args=[restaurant.slug])
        if order_type in HOME_ORDER_TYPES:
            url = f"{url}?type={order_type}"
        return redirect(url)


def table_access_granted(request, table):
    """Le QR code de la table (son jeton) est la clé d'accès à la commande sur place."""
    key = f"table_token_{table.pk}"
    token = request.GET.get("token") or request.session.get(key)
    if token and QRCode.objects.filter(table=table, token=token, is_active=True).exists():
        request.session[key] = token
        return True
    request.session.pop(key, None)
    return False


class TableMenuView(TemplateView):
    template_name = "client/restaurant_detail.html"

    def get_context_data(self, **kwargs):
        restaurant = _public_restaurant(self.kwargs["restaurant_slug"])
        table = get_object_or_404(
            DiningTable,
            pk=self.kwargs["table_id"],
            restaurant=restaurant,
            is_active=True,
        )
        if not table_access_granted(self.request, table):
            raise PermissionDenied("Scannez le QR code de votre table pour commander sur place.")
        context = super().get_context_data(**kwargs)
        context.update(ordering_context(self.request, restaurant, table=table))
        return context


def _active_cart(request):
    restaurant_id = request.GET.get("restaurant") or request.session.get("cart_restaurant_id")
    if not restaurant_id:
        return None
    restaurant = Restaurant.objects.filter(pk=restaurant_id).first()
    if restaurant is None:
        return None
    request.session["cart_restaurant_id"] = restaurant.pk
    return find_cart(request, restaurant)


@require_POST
def add_item(request):
    restaurant = get_object_or_404(Restaurant, pk=request.POST.get("restaurant"), status=RestaurantStatus.ACTIVE)
    product = get_object_or_404(Product, pk=request.POST.get("product"), restaurant=restaurant)
    table = None
    if request.POST.get("table"):
        table = get_object_or_404(DiningTable, pk=request.POST.get("table"), restaurant=restaurant, is_active=True)
    order_type = OrderType.DINE_IN if table else request.POST.get("order_type")
    if order_type not in OrderType.values or (order_type == OrderType.DINE_IN and not table):
        order_type = OrderType.TAKEAWAY
    cart = get_or_create_cart(request, restaurant, table=table, order_type=order_type)
    request.session["cart_restaurant_id"] = restaurant.pk
    try:
        add_to_cart(cart, product, 1)
        messages.success(request, f"{product.name} ajouté à votre commande.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(_safe_next(request, _restaurant_url(cart)))


@require_POST
def update_item(request, pk):
    item = owned_cart_item(request, pk)
    if item is None:
        raise PermissionDenied("Ce panier n'est pas le vôtre.")
    fallback = _restaurant_url(item.cart)
    try:
        quantity = int(request.POST.get("quantity", item.quantity))
    except ValueError:
        quantity = item.quantity
    update_cart_item(item, quantity=quantity)
    return redirect(_safe_next(request, fallback))


@require_POST
def remove_item(request, pk):
    item = owned_cart_item(request, pk)
    if item is None:
        raise PermissionDenied("Ce panier n'est pas le vôtre.")
    fallback = _restaurant_url(item.cart)
    item.delete()
    return redirect(_safe_next(request, fallback))


class CartView(TemplateView):
    template_name = "client/cart.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart = _active_cart(self.request)
        context["cart"] = cart
        if cart:
            context["order_type"] = cart.order_type
            context["table"] = cart.table
            context["restaurant"] = cart.restaurant
            context["back_url"] = _restaurant_url(cart)
        return context


class CheckoutView(View):
    template_name = "client/checkout.html"

    def _addresses(self, request):
        if request.user.is_authenticated:
            return list(request.user.addresses.all())
        return []

    def _context(self, cart, form):
        return {
            "cart": cart,
            "form": form,
            "restaurant": cart.restaurant,
            "order_type": cart.order_type,
            "table": cart.table,
            "back_url": _restaurant_url(cart),
            "payment_hint": PAYMENT_BY_TYPE[cart.order_type][1],
        }

    def _cart(self, request):
        cart = _active_cart(request)
        if cart and cart.order_type == OrderType.DINE_IN and (
            not cart.table_id or not table_access_granted(request, cart.table)
        ):
            cart.order_type = OrderType.TAKEAWAY
            cart.table = None
            cart.save(update_fields=["order_type", "table", "updated_at"])
        return cart

    def _form(self, request, cart, data=None):
        addresses = self._addresses(request) if cart.order_type == OrderType.DELIVERY else []
        initial = {"note": cart.note}
        if request.user.is_authenticated:
            initial.update(
                {
                    "first_name": request.user.first_name,
                    "last_name": request.user.last_name,
                    "phone": request.user.phone,
                    "email": request.user.email,
                }
            )
            default_address = next((item for item in addresses if item.is_default), addresses[0] if addresses else None)
            if default_address:
                initial.update(
                    {
                        "address_id": default_address.pk,
                        "address_text": default_address.line1,
                        "city": default_address.city,
                        "district": default_address.district,
                    }
                )
        return CheckoutForm(
            data,
            initial=None if data else initial,
            order_type=cart.order_type,
            addresses=addresses,
        )

    def get(self, request):
        cart = self._cart(request)
        if cart is None or not cart.items.exists():
            messages.warning(request, "Votre panier est vide. Choisissez d'abord vos plats.")
            return redirect("restaurants:list")
        return render(request, self.template_name, self._context(cart, self._form(request, cart)))

    def post(self, request):
        cart = self._cart(request)
        if cart is None or not cart.items.exists():
            return redirect("restaurants:list")
        form = self._form(request, cart, data=request.POST)
        if not form.is_valid():
            return render(request, self.template_name, self._context(cart, form))
        address = None
        if form.cleaned_data.get("address_id") and request.user.is_authenticated:
            address = CustomerAddress.objects.filter(
                pk=form.cleaned_data["address_id"], customer=request.user
            ).first()
        try:
            contact = form.contact_payload()
            address_text = form.cleaned_data.get("address_text", "")
            if address:
                address_text = address_text or address.line1
                contact["city"] = contact["city"] or address.city
                contact["district"] = contact["district"] or address.district
            order = checkout_cart(
                cart,
                customer=request.user if request.user.is_authenticated else None,
                address=address,
                address_text=address_text,
                note=form.cleaned_data.get("note", ""),
                contact=contact,
            )
            if order.order_type == OrderType.DELIVERY:
                ensure_delivery(order)
            CashPaymentProvider().charge(order, method=PAYMENT_BY_TYPE[order.order_type][0])
            request.session["last_order_id"] = order.pk
            return redirect(f"{reverse('orders:detail', args=[order.pk])}?nouvelle=1")
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
            return render(request, self.template_name, self._context(cart, form))


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        flow = [status for status in STATUS_FLOW[order.order_type] if status != OrderStatus.COMPLETED]
        if order.status == OrderStatus.COMPLETED:
            reached = len(flow)
        elif order.status in flow:
            reached = flow.index(order.status)
        else:
            reached = -1
        context["steps"] = [
            {
                "label": CLIENT_STEP_LABELS[order.order_type].get(status, OrderStatus(status).label),
                "state": "done" if index < reached else ("current" if index == reached else "todo"),
            }
            for index, status in enumerate(flow)
        ]
        context["headline"] = CLIENT_HEADLINES.get(order.status, "")
        context["just_placed"] = self.request.GET.get("nouvelle") == "1"
        context["payment"] = order.payments.first()
        return context


CLIENT_STEP_LABELS = {
    OrderType.DINE_IN: {
        OrderStatus.PENDING: "Envoyée",
        OrderStatus.ACCEPTED: "Acceptée",
        OrderStatus.PREPARING: "En cuisine",
        OrderStatus.READY: "Prête",
        OrderStatus.SERVED: "Servie",
    },
    OrderType.TAKEAWAY: {
        OrderStatus.PENDING: "Envoyée",
        OrderStatus.ACCEPTED: "Acceptée",
        OrderStatus.PREPARING: "En cuisine",
        OrderStatus.READY: "Prête à retirer",
        OrderStatus.PICKED_UP: "Récupérée",
    },
    OrderType.DELIVERY: {
        OrderStatus.PENDING: "Envoyée",
        OrderStatus.ACCEPTED: "Acceptée",
        OrderStatus.PREPARING: "En cuisine",
        OrderStatus.READY: "Prête",
        OrderStatus.OUT_FOR_DELIVERY: "En route",
        OrderStatus.DELIVERED: "Livrée",
    },
}

CLIENT_HEADLINES = {
    OrderStatus.PENDING: "Le restaurant a reçu votre commande. Il va la confirmer.",
    OrderStatus.ACCEPTED: "Votre commande est acceptée.",
    OrderStatus.PREPARING: "Votre commande est en cuisine.",
    OrderStatus.READY: "Votre commande est prête.",
    OrderStatus.SERVED: "Bon appétit !",
    OrderStatus.PICKED_UP: "Commande récupérée. Bon appétit !",
    OrderStatus.OUT_FOR_DELIVERY: "Le livreur est en route.",
    OrderStatus.DELIVERED: "Commande livrée. Bon appétit !",
    OrderStatus.COMPLETED: "Commande terminée. Merci !",
    OrderStatus.CANCELLED: "Cette commande a été annulée.",
}


PERIOD_LABELS = {
    "today": "Aujourd'hui",
    "week": "Cette semaine",
    "month": "Ce mois",
}


class ManagerDashboardView(ManagerRequiredMixin, RestaurantContextMixin, TemplateView):
    template_name = "manager/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        restaurant = self.restaurant
        period = self.request.GET.get("period", "today")
        if period not in PERIOD_LABELS:
            period = "today"
        metrics = dashboard_metrics(restaurant, period)
        top_products = list(metrics["top_products"])
        max_qty = max((item["qty"] or 0) for item in top_products) if top_products else 0
        for item in top_products:
            qty = item["qty"] or 0
            item["pct"] = int((qty * 100) / max_qty) if max_qty else 0
        metrics["top_products"] = top_products
        metrics["period_label"] = PERIOD_LABELS[period]

        live_orders = Order.objects.filter(restaurant=restaurant)
        roles = Counter(restaurant.employees.filter(is_active=True).values_list("role", flat=True))
        product_count = Product.objects.filter(restaurant=restaurant).count()
        category_count = Category.objects.filter(restaurant=restaurant).count()
        table_count = DiningTable.objects.filter(restaurant=restaurant).count()
        staff_count = restaurant.employees.filter(is_active=True).count()
        setup_steps = [
            {"done": category_count > 0 and product_count > 0, "key": "menu"},
            {"done": table_count > 0, "key": "tables"},
            {"done": staff_count > 1, "key": "team"},
        ]
        context.update(
            {
                "metrics": metrics,
                "low_stocks": [item for item in StockItem.objects.filter(restaurant=restaurant, is_active=True) if item.is_low][:6],
                "recent_orders": live_orders.select_related("table")[:8],
                "product_count": product_count,
                "category_count": category_count,
                "table_count": table_count,
                "employee_count": staff_count,
                "setup_done": sum(1 for step in setup_steps if step["done"]),
                "setup_total": len(setup_steps),
                "needs_setup": any(not step["done"] for step in setup_steps),
                "live": {
                    "pending": live_orders.filter(status__in=[OrderStatus.PENDING, OrderStatus.ACCEPTED]).count(),
                    "preparing": live_orders.filter(status=OrderStatus.PREPARING).count(),
                    "ready": live_orders.filter(status=OrderStatus.READY).count(),
                    "delivery": live_orders.filter(status=OrderStatus.OUT_FOR_DELIVERY).count(),
                },
                "team": {
                    "total": staff_count,
                    "cooks": roles.get(Role.COOK, 0),
                    "waiters": roles.get(Role.WAITER, 0),
                    "drivers": roles.get(Role.DRIVER, 0),
                },
            }
        )
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


# Qui peut faire passer une commande à quel statut (le gérant peut tout faire).
KITCHEN_ROLES = (Role.MANAGER, Role.COOK)
SERVICE_ROLES = (Role.MANAGER, Role.WAITER)
STATUS_ROLES = {
    OrderStatus.ACCEPTED: KITCHEN_ROLES,
    OrderStatus.PREPARING: KITCHEN_ROLES,
    OrderStatus.READY: KITCHEN_ROLES,
    OrderStatus.SERVED: SERVICE_ROLES,
    OrderStatus.PICKED_UP: SERVICE_ROLES,
    OrderStatus.COMPLETED: SERVICE_ROLES,
    OrderStatus.CANCELLED: (Role.MANAGER,),
}


@login_required
@require_POST
def change_status(request, pk):
    order = get_object_or_404(Order, pk=pk)
    new_status = request.POST.get("status")
    require_restaurant_role(request.user, order.restaurant, STATUS_ROLES.get(new_status, (Role.MANAGER,)))
    fallback = reverse("orders:manager_order", args=[order.pk])
    try:
        transition_order(order, new_status, request.user, reason=request.POST.get("reason", "")[:255])
        messages.success(request, f"Commande {order.number} : {order.get_status_display()}.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(_safe_next(request, fallback))


@login_required
@require_POST
def mark_paid(request, pk):
    order = get_object_or_404(Order, pk=pk)
    require_restaurant_role(request.user, order.restaurant, SERVICE_ROLES)
    if mark_order_paid(order):
        messages.success(request, f"Paiement de la commande {order.number} encaissé.")
    else:
        messages.info(request, "Aucun paiement en attente pour cette commande.")
    return redirect(_safe_next(request, reverse("orders:manager_order", args=[order.pk])))


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
