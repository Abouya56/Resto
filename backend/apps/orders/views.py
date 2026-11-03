from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Exists, OuterRef, Prefetch, Q, Sum
from django.db.models.functions import TruncDate
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView, View

from apps.core.daterange import PRESETS, DateRange, get_date_range
from apps.core.mixins import ManagerRequiredMixin, ReceptionRequiredMixin, RestaurantContextMixin
from apps.core.tenancy import require_restaurant_role, user_can_access_restaurant
from apps.deliveries.services import ensure_delivery
from apps.finance.services import dashboard_metrics
from apps.inventory.feature import stock_enabled, stock_filter
from apps.inventory.models import StockItem
from apps.menus.models import Category, Product
from apps.orders import receipts, tracking
from apps.orders.forms import CheckoutForm, TrackOrderForm
from apps.orders.models import Order, OrderStatus, OrderType
from apps.orders.services import (
    record_counter_sale,
    add_to_cart,
    checkout_cart,
    find_cart,
    get_or_create_cart,
    owned_cart_item,
    transition_order,
    update_cart_item,
)
from apps.payments.models import Payment, PaymentMethod, PaymentStatus
from apps.restaurants.licenses import license_info
from apps.payments.providers import CashPaymentProvider
from apps.payments.services import collected_method, mark_order_paid
from apps.restaurants.models import Restaurant, RestaurantStatus
from apps.tables.models import DiningTable, QRCode
from apps.users.roles import Role


def _public_restaurant(slug):
    return get_object_or_404(Restaurant, slug=slug, status=RestaurantStatus.ACTIVE)


HOME_ORDER_TYPES = (OrderType.TAKEAWAY, OrderType.PREORDER, OrderType.DELIVERY)

PAYMENT_BY_TYPE = {
    OrderType.DINE_IN: (PaymentMethod.CASH_ON_SITE, "Vous réglez à table, auprès du serveur."),
    OrderType.TAKEAWAY: (PaymentMethod.CASH_ON_SITE, "Vous réglez au comptoir, en récupérant votre commande."),
    OrderType.PREORDER: (PaymentMethod.CASH_ON_SITE, "Vous réglez au restaurant, en arrivant."),
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
            Prefetch("products", queryset=Product.objects.filter(is_active=True, is_available=True, **stock_filter()))
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
        if (
            cart
            and cart.order_type == OrderType.DINE_IN
            and (not cart.table_id or not table_access_granted(request, cart.table))
        ):
            cart.order_type = OrderType.TAKEAWAY
            cart.table = None
            cart.save(update_fields=["order_type", "table", "updated_at"])
        return cart

    def _form(self, request, cart, data=None):
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
        return CheckoutForm(
            data,
            initial=None if data else initial,
            order_type=cart.order_type,
            restaurant=cart.restaurant,
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
        try:
            order = checkout_cart(
                cart,
                customer=request.user if request.user.is_authenticated else None,
                address_text=form.cleaned_data.get("address_text", ""),
                note=form.cleaned_data.get("note", ""),
                contact=form.contact_payload(),
                scheduled_for=form.scheduled_for,
                arrival_at=form.arrival_at,
            )
            if order.order_type == OrderType.DELIVERY:
                ensure_delivery(order)
            CashPaymentProvider().charge(order, method=PAYMENT_BY_TYPE[order.order_type][0])
            request.session["last_order_id"] = order.pk
            tracking.remember(request.session, order)
            receipts.send_order_receipt(order)
            return redirect(f"{reverse('orders:detail', args=[order.pk])}?nouvelle=1")
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
            return render(request, self.template_name, self._context(cart, form))


class TrackOrderView(View):
    """Le client retrouve sa commande avec son numéro, depuis n'importe quel appareil."""

    template_name = "client/track.html"

    def get(self, request):
        initial = {"number": request.GET.get("numero", "")}
        return render(request, self.template_name, {"form": TrackOrderForm(initial=initial)})

    def post(self, request):
        form = TrackOrderForm(request.POST)
        if form.is_valid():
            if tracking.too_many_failures(request):
                form.add_error(None, "Trop d'essais. Réessayez dans quelques minutes.")
            else:
                order = tracking.find_order(form.cleaned_data["number"], form.cleaned_data["phone"])
                if order:
                    tracking.remember(request.session, order)
                    return redirect("orders:detail", pk=order.pk)
                tracking.record_failure(request)
                form.add_error(
                    None,
                    "Aucune commande ne correspond. Vérifiez le numéro et le téléphone donnés lors de la commande.",
                )
        return render(request, self.template_name, {"form": form})


class OrderDetailView(DetailView):
    template_name = "client/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return Order.objects.select_related("restaurant", "table").prefetch_related("items", "payments")

    def get_object(self, queryset=None):
        order = super().get_object(queryset)
        user = self.request.user
        if user.is_authenticated and (
            order.customer_id == user.id or user_can_access_restaurant(user, order.restaurant)
        ):
            return order
        if tracking.can_view(self.request.session, order.pk):
            return order
        raise PermissionDenied("Vous ne pouvez pas consulter cette commande.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        # Le client n'a besoin que d'une réponse : sa commande est prise en charge, ou le restaurant la refuse.
        context["rejected"] = order.status == OrderStatus.CANCELLED
        # Trois réponses possibles pour le client : en attente, acceptée, refusée.
        if context["rejected"]:
            verdict = "rejected"
            headline = "Commande refusée"
            hint = "Le restaurant ne peut pas la préparer. Vous pouvez l'appeler ou choisir un autre restaurant."
            if order.cancellation_reason:
                hint = f"Raison : {order.cancellation_reason}. " + hint
        elif order.status == OrderStatus.PENDING:
            verdict = "pending"
            headline = "En attente de réponse"
            hint = "Le restaurant doit accepter votre commande. Gardez cette page ouverte : elle change dès qu'il répond."
        else:
            verdict = "accepted"
            headline = "Commande acceptée"
            hint = CLIENT_ACCEPTED_HINTS.get(order.order_type, "")
        context.update({"verdict": verdict, "headline": headline, "headline_hint": hint})
        context["just_placed"] = self.request.GET.get("nouvelle") == "1"
        context["receipt_email"] = receipts.receipt_email(order)
        context["payment"] = order.payments.first()
        return context


class OrderReceiptView(OrderDetailView):
    """Reçu imprimable : mêmes droits d'accès que la page de suivi."""

    template_name = "client/receipt.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tracking_url"] = receipts.tracking_url(self.object).split("?")[0]
        return context


CLIENT_ACCEPTED_HINTS = {
    OrderType.DINE_IN: "Installez-vous : on vous sert à votre table.",
    OrderType.TAKEAWAY: "Elle sera prête au comptoir. Annoncez votre numéro pour la récupérer.",
    OrderType.PREORDER: "On prépare votre repas pour l'heure choisie. Annoncez votre numéro en arrivant.",
    OrderType.DELIVERY: "Un livreur vous l'apporte. Gardez votre téléphone à portée de main.",
}


LATE_AFTER_MINUTES = 15


class ManagerDashboardView(ManagerRequiredMixin, RestaurantContextMixin, TemplateView):
    template_name = "manager/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        restaurant = self.restaurant
        context["license"] = license_info(restaurant)
        dr = get_date_range(self.request, default="aujourdhui")
        metrics = dashboard_metrics(
            restaurant, "today" if dr.key == "aujourdhui" else "custom", start=dr.start, end=dr.end
        )
        top_products = list(metrics["top_products"])
        max_qty = max((item["qty"] or 0) for item in top_products) if top_products else 0
        for item in top_products:
            qty = item["qty"] or 0
            item["pct"] = int((qty * 100) / max_qty) if max_qty else 0
        metrics["top_products"] = top_products
        metrics["period_label"] = dr.label

        live_orders = Order.objects.filter(restaurant=restaurant)
        start, end = metrics["start"], metrics["end"]
        period_orders = live_orders.filter(created_at__date__gte=start, created_at__date__lte=end).exclude(
            status=OrderStatus.CANCELLED
        )
        by_type_counts = dict(period_orders.order_by().values_list("order_type").annotate(n=Count("id")))
        biggest = max(by_type_counts.values(), default=0)
        by_type = [
            {
                "label": label,
                "count": by_type_counts.get(value, 0),
                "pct": round(by_type_counts.get(value, 0) * 100 / biggest) if biggest else 0,
            }
            for value, label in OrderType.choices
        ]
        today = timezone.localdate()
        limit = timezone.now() - timedelta(minutes=LATE_AFTER_MINUTES)
        # Retards du jour seulement : au-delà de 24 h, une commande oubliée n'est plus un « retard » à signaler.
        late_count = (
            live_orders.filter(
                status__in=[OrderStatus.PENDING, OrderStatus.ACCEPTED, OrderStatus.PREPARING, OrderStatus.READY],
                created_at__lte=limit,
                created_at__gte=timezone.now() - timedelta(hours=24),
            )
            .filter(Q(scheduled_for__isnull=True) | Q(scheduled_for__lte=today))
            # Commande à l'avance : pas en retard tant que le client n'est pas arrivé.
            .filter(Q(arrival_at__isnull=True) | Q(arrival_at__lte=timezone.now()))
            .count()
        )
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
                "dr": dr,
                "presets": PRESETS,
                "low_stocks": [
                    item for item in StockItem.objects.filter(restaurant=restaurant, is_active=True) if item.is_low
                ][:6]
                if stock_enabled()
                else [],
                "late_count": late_count,
                "late_minutes": LATE_AFTER_MINUTES,
                "by_type": by_type,
                "orders_in_period": sum(by_type_counts.values()),
                "product_count": product_count,
                "category_count": category_count,
                "table_count": table_count,
                "employee_count": staff_count,
                "setup_done": sum(1 for step in setup_steps if step["done"]),
                "setup_total": len(setup_steps),
                "needs_setup": any(not step["done"] for step in setup_steps),
                # Un chiffre par type de commande, sur les mêmes commandes « en cours » que l'écran de la réception.
                "live_types": [
                    {
                        "label": label,
                        "icon": icon,
                        "type": order_type,
                        "open": live_orders.filter(order_type=order_type, status__in=RECEPTION_OPEN_STATUSES).count(),
                        "new": live_orders.filter(order_type=order_type, status=OrderStatus.PENDING).count(),
                    }
                    for _key, label, icon, order_type in RECEPTION_TYPES
                ],
                "live": {
                    "to_serve": live_orders.exclude(order_type=OrderType.DELIVERY)
                    .filter(status__in=RECEPTION_OPEN_STATUSES)
                    .count(),
                    "pending": live_orders.filter(status__in=[OrderStatus.PENDING, OrderStatus.ACCEPTED]).count(),
                    "preparing": live_orders.filter(status=OrderStatus.PREPARING).count(),
                    "ready": live_orders.filter(status=OrderStatus.READY).count(),
                    "delivery": live_orders.filter(order_type=OrderType.DELIVERY, status__in=RECEPTION_OPEN_STATUSES)
                    .count(),
                },
            }
        )
        return context


ORDERS_TO_HANDLE = (
    OrderStatus.PENDING,
    OrderStatus.ACCEPTED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.SERVED,
    OrderStatus.OUT_FOR_DELIVERY,
)
ORDER_TABS = (
    ("a-traiter", "En cours"),
    ("aujourdhui", "Aujourd'hui"),
    ("toutes", "Historique"),
)


class ManagerOrderListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    """Commandes rangées par jour, avec onglets, filtres et recherche : lisible même avec des milliers de lignes."""

    template_name = "manager/orders.html"
    context_object_name = "orders"
    paginate_by = 40

    def get_filters(self):
        params = self.request.GET
        dr = get_date_range(self.request)
        status = params.get("status", "")
        tab = params.get("vue") or ("toutes" if status or dr.active else "a-traiter")
        if tab not in dict(ORDER_TABS):
            tab = "a-traiter"
        return {
            "tab": tab,
            "dr": dr,
            "status": status if status in OrderStatus.values else "",
            "type": params.get("type", "") if params.get("type", "") in OrderType.values else "",
            "q": params.get("q", "").strip()[:60],
        }

    def base_queryset(self):
        return Order.objects.filter(restaurant=self.restaurant)

    def apply_filters(self, qs, filters, with_tab=True):
        if with_tab:
            if filters["tab"] == "a-traiter":
                qs = qs.filter(status__in=ORDERS_TO_HANDLE)
            elif filters["tab"] == "aujourdhui":
                qs = qs.filter(created_at__date=timezone.localdate())
        if filters["dr"].active:
            qs = qs.filter(**filters["dr"].contains_filter("created_at__date"))
        if filters["status"]:
            qs = qs.filter(status=filters["status"])
        if filters["type"]:
            qs = qs.filter(order_type=filters["type"])
        if filters["q"]:
            qs = qs.filter(order_search_filter(filters["q"]))
        return qs

    def get_queryset(self):
        self.filters = self.get_filters()
        qs = self.apply_filters(self.base_queryset(), self.filters)
        # À traiter : la plus ancienne d'abord (c'est elle qui attend). Sinon : la plus récente d'abord.
        order = ("created_at",) if self.filters["tab"] == "a-traiter" else ("-created_at",)
        return qs.select_related("table", "restaurant").order_by(*order)

    def range_summary(self):
        """Total de tout ce qui correspond aux filtres (pas seulement la page affichée), hors annulées."""
        if not self.filters["dr"].active:
            return None
        rows = self.get_queryset().exclude(status=OrderStatus.CANCELLED).order_by()
        total = rows.aggregate(n=Count("id"), amount=Sum("total"))
        return {"count": total["n"], "amount": total["amount"] or 0}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filters = self.filters
        page_orders = list(context["orders"])
        days = {timezone.localdate(order.created_at) for order in page_orders}
        totals = {}
        if days:
            rows = (
                self.get_queryset()
                .filter(created_at__date__in=days)
                .exclude(status=OrderStatus.CANCELLED)
                .order_by()  # sans tri : sinon l'heure entre dans le regroupement et coupe les jours
                .annotate(day=TruncDate("created_at"))
                .values("day")
                .annotate(n=Count("id"), amount=Sum("total"))
            )
            totals = {row["day"]: row for row in rows}
        groups = []
        for order in page_orders:
            day = timezone.localdate(order.created_at)
            if not groups or groups[-1]["day"] != day:
                summary = totals.get(day, {})
                groups.append({"day": day, "orders": [], "count": summary.get("n", 0), "amount": summary.get("amount")})
            groups[-1]["orders"].append(order)
        base_without_tab = self.apply_filters(self.base_queryset(), {**filters, "dr": DateRange()}, with_tab=False)
        counts = {
            "a-traiter": base_without_tab.filter(status__in=ORDERS_TO_HANDLE).count(),
            "aujourdhui": base_without_tab.filter(created_at__date=timezone.localdate()).count(),
        }
        context.update(
            {
                "groups": groups,
                "filters": filters,
                "tabs": [{"key": key, "label": label, "count": counts.get(key)} for key, label in ORDER_TABS],
                "today": timezone.localdate(),
                "status_choices": OrderStatus.choices,
                "type_choices": OrderType.choices,
                "has_filters": filters["dr"].active or any(filters[key] for key in ("status", "type", "q")),
                "presets": PRESETS,
                "range_summary": self.range_summary(),
            }
        )
        return context


class ManagerOrderDetailView(ManagerRequiredMixin, RestaurantContextMixin, DetailView):
    template_name = "manager/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return Order.objects.filter(restaurant=self.restaurant).prefetch_related("items", "payments")


# Qui peut faire passer une commande à quel statut : la réception, et le gérant en cas de besoin.
# Le gérant supervise : il regarde. Seule la réception accepte, refuse et encaisse.
SERVICE_ROLES = (Role.RECEPTION,)
STATUS_ROLES = {
    OrderStatus.ACCEPTED: SERVICE_ROLES,
    OrderStatus.PREPARING: SERVICE_ROLES,
    OrderStatus.READY: SERVICE_ROLES,
    OrderStatus.SERVED: SERVICE_ROLES,
    OrderStatus.PICKED_UP: SERVICE_ROLES,
    OrderStatus.OUT_FOR_DELIVERY: SERVICE_ROLES,
    OrderStatus.DELIVERED: SERVICE_ROLES,
    OrderStatus.COMPLETED: SERVICE_ROLES,
    OrderStatus.CANCELLED: SERVICE_ROLES,
}


def status_message(order):
    """Ce que le personnel doit comprendre après un clic : où est passée la commande, et quoi faire ensuite."""
    name = f"N° {order.short_number}" if order.short_number else order.number
    if order.status in (OrderStatus.ACCEPTED, OrderStatus.PREPARING, OrderStatus.READY):
        return f"{name} : {order.get_status_display()}."
    if order.status == OrderStatus.SERVED:
        return f"{name} servie à table. Il reste à encaisser."
    if order.status == OrderStatus.PICKED_UP:
        return f"{name} remise au client et payée."
    if order.status == OrderStatus.COMPLETED:
        if order.order_type == OrderType.DINE_IN:
            return f"{name} servie et encaissée. La table est libre."
        return f"{name} terminée et encaissée."
    if order.status == OrderStatus.CANCELLED:
        return f"{name} refusée. Le client le voit sur son téléphone."
    return f"{name} : {order.get_status_display()}."


@login_required
@require_POST
def change_status(request, pk):
    order = get_object_or_404(Order, pk=pk)
    new_status = request.POST.get("status")
    require_restaurant_role(request.user, order.restaurant, STATUS_ROLES.get(new_status, SERVICE_ROLES))
    fallback = reverse("orders:manager_order", args=[order.pk])
    try:
        transition_order(
            order,
            new_status,
            request.user,
            reason=request.POST.get("reason", "")[:255],
            payment_method=collected_method(order, request.POST.get("payment", "")),
        )
        messages.success(request, status_message(order))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    came_from = _safe_next(request, "")
    if came_from:
        # On revient sur la carte qui vient de bouger : la page défile jusqu'à elle et la met en évidence.
        return redirect(f"{came_from.split('#')[0]}#commande-{order.pk}")
    return redirect(fallback)


@login_required
@require_POST
def mark_paid(request, pk):
    order = get_object_or_404(Order, pk=pk)
    require_restaurant_role(request.user, order.restaurant, SERVICE_ROLES)
    if mark_order_paid(order, method=collected_method(order, request.POST.get("payment", ""))):
        messages.success(request, f"Paiement de la commande {order.number} encaissé.")
    else:
        messages.info(request, "Aucun paiement en attente pour cette commande.")
    return redirect(_safe_next(request, reverse("orders:manager_order", args=[order.pk])))


def order_search_filter(q, today_only=False):
    """Recherche par numéro (court ou complet), nom, prénom ou téléphone.

    Un numéro court (1 à 3 chiffres, « 002 ») désigne UNE commande : celle portant ce numéro du jour.
    Il ne cherche donc ni dans les références ni dans les téléphones, où ces chiffres se retrouvent par hasard.
    `today_only` : à la réception, le numéro du jour ne désigne que la commande d'aujourd'hui.
    """
    digits = "".join(c for c in q if c.isdigit())
    is_short_number = bool(digits) and len(digits) <= 3 and digits == "".join(q.split()).lstrip("N°º#.nN")
    if is_short_number:
        match = Q(daily_number=int(digits))
        if today_only:
            match &= Q(service_date=timezone.localdate())
        return match
    match = (
        Q(number__icontains=tracking.normalize_number(q))
        | Q(customer_first_name__icontains=q)
        | Q(customer_last_name__icontains=q)
    )
    if digits:
        match |= Q(customer_phone__icontains=digits)
    return match


RECEPTION_TYPES = (
    ("table", "À table", "bi-cup-hot", OrderType.DINE_IN),
    ("emporter", "À emporter", "bi-bag", OrderType.TAKEAWAY),
    ("avance", "À l'avance", "bi-alarm", OrderType.PREORDER),
    ("livraison", "Livraison", "bi-bicycle", OrderType.DELIVERY),
)
RECEPTION_OPEN_STATUSES = [
    OrderStatus.PENDING,
    OrderStatus.ACCEPTED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.SERVED,
    OrderStatus.OUT_FOR_DELIVERY,
]


class ReceptionMixin(ReceptionRequiredMixin, RestaurantContextMixin):
    """Ce que partagent le tableau de bord et les pages par type : les commandes en cours, rangées par type."""

    def reception_context(self, current_key):
        paid = Payment.objects.filter(order=OuterRef("pk"), status=PaymentStatus.PAID)
        q = self.request.GET.get("q", "").strip()[:60]
        orders = (
            Order.objects.filter(restaurant=self.restaurant, status__in=RECEPTION_OPEN_STATUSES)
            .select_related("restaurant", "table")
            .prefetch_related("items")
            .annotate(is_paid=Exists(paid))
            .order_by("created_at")
        )
        if q:
            orders = orders.filter(order_search_filter(q, today_only=True))
        # Les commandes à l'avance se rangent par heure d'arrivée : la plus proche en premier.
        queue = sorted(
            orders,
            key=lambda o: (o.arrival_at or o.created_at) if o.order_type == OrderType.PREORDER else o.created_at,
        )
        groups = [
            {
                "key": key,
                "label": label,
                "icon": icon,
                "orders": [o for o in queue if o.order_type == order_type],
                "new": sum(1 for o in queue if o.order_type == order_type and o.status == OrderStatus.PENDING),
            }
            for key, label, icon, order_type in RECEPTION_TYPES
        ]
        return {
            "q": q,
            "queue": queue,
            "groups": groups,
            # Menu : d'abord les types qui ont des commandes à accepter, puis ceux qui ont des commandes en cours.
            "menu_groups": sorted(groups, key=lambda g: (-g["new"], -len(g["orders"]))),
            "current_key": current_key,
            "current": next((g for g in groups if g["key"] == current_key), None),
            "new_total": sum(g["new"] for g in groups),
        }


class ReceptionDashboardView(ReceptionMixin, TemplateView):
    """Le tableau de bord du réceptionniste : où en sont les commandes, et les chiffres du jour."""

    template_name = "reception/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.reception_context("dashboard"))
        today = timezone.localdate()
        day = Order.objects.filter(restaurant=self.restaurant, created_at__date=today)
        collected = Payment.objects.filter(
            order__restaurant=self.restaurant, status=PaymentStatus.PAID, paid_at__date=today
        )
        by_method = dict(collected.order_by().values_list("method").annotate(total=Sum("amount")))
        mobile = by_method.get(PaymentMethod.MOBILE_MONEY) or 0
        cash = sum((total or 0 for method, total in by_method.items() if method != PaymentMethod.MOBILE_MONEY), 0)
        context["today"] = {
            "received": day.exclude(status=OrderStatus.CANCELLED).count(),
            "refused": day.filter(status=OrderStatus.CANCELLED).count(),
            "cash": cash,
            "mobile": mobile,
            "collected": cash + mobile,
            "late": sum(1 for order in context["queue"] if order.is_late),
        }
        return context


class ReceptionTypeView(ReceptionMixin, TemplateView):
    """Une page par type de commande : à table, à emporter, à l'avance, livraison."""

    template_name = "reception/type.html"

    def get_context_data(self, **kwargs):
        key = self.kwargs["key"]
        if key not in {item[0] for item in RECEPTION_TYPES}:
            raise Http404("Type de commande inconnu.")
        context = super().get_context_data(**kwargs)
        context.update(self.reception_context(key))
        return context




class ReceptionSaleView(ReceptionMixin, TemplateView):
    """Vendre à un client qui n'a pas commandé sur le site : on choisit les plats, puis espèces ou mobile."""

    template_name = "reception/sale.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.reception_context("vente"))
        categories = []
        for category in Category.objects.filter(restaurant=self.restaurant, is_active=True).prefetch_related(
            Prefetch("products", queryset=Product.objects.filter(is_active=True, is_available=True))
        ):
            products = [p for p in category.products.all() if p.can_be_ordered]
            if products:
                categories.append({"category": category, "products": products})
        context["categories"] = categories
        return context

    def post(self, request, *args, **kwargs):
        require_restaurant_role(request.user, self.restaurant, (Role.RECEPTION,))  # le gérant supervise : il ne vend pas
        lines = []
        for key, value in request.POST.items():
            if key.startswith("qty_") and key[4:].isdigit():
                try:
                    lines.append((int(key[4:]), int(value or 0)))
                except ValueError:
                    continue
        try:
            order = record_counter_sale(
                self.restaurant,
                lines,
                request.POST.get("payment", ""),
                user=request.user,
                customer_name=request.POST.get("name", ""),
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("orders:reception_sale")
        how = "en mobile" if request.POST.get("payment") == "mobile" else "en espèces"
        messages.success(request, f"Vente N° {order.short_number} enregistrée : {order.total:,.0f} FCFA {how}.".replace(",", " "))
        return redirect("orders:reception_sale")
