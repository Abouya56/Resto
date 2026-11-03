"""Suivi d'une commande sans compte : numéro de commande + téléphone donné à la commande."""

import re
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.orders.models import Order

SESSION_KEY = "tracked_orders"
MAX_TRACKED = 10
MAX_FAILURES = 10  # essais ratés par adresse IP
FAILURE_WINDOW = 15 * 60  # secondes


def normalize_number(number):
    return re.sub(r"[^A-Za-z0-9]", "", number or "").upper()


def _last_digits(phone):
    return "".join(c for c in phone or "" if c.isdigit())[-8:]


SHORT_NUMBER_DAYS = 3  # un numéro court (012) ne désigne une commande que pendant quelques jours


def is_short_number(number):
    """« 12 », « 012 », « N° 012 » : le numéro du jour, remis à zéro chaque matin."""
    digits = re.sub(r"[^0-9]", "", number or "")
    return bool(digits) and len(digits) <= 4 and not re.search(r"[A-Za-z]", re.sub(r"^[Nn°º#.\s]+", "", number or ""))


def find_by_short_number(number, phone):
    """Le numéro du jour + le téléphone donné à la commande : la vérification la plus simple pour un client."""
    given = _last_digits(phone)
    if len(given) < 8:
        return None
    daily = int(re.sub(r"[^0-9]", "", number))
    since = timezone.localdate() - timedelta(days=SHORT_NUMBER_DAYS)
    candidates = (
        Order.objects.filter(daily_number=daily, service_date__gte=since)
        .exclude(customer_phone="")
        .select_related("restaurant")
        .order_by("-created_at")
    )
    return next((o for o in candidates if _last_digits(o.customer_phone) == given), None)


def find_order(number, phone):
    """La commande si le numéro existe et que le téléphone correspond (quand la commande en a un)."""
    if is_short_number(number):
        return find_by_short_number(number, phone)
    order = Order.objects.filter(number=normalize_number(number)).select_related("restaurant").first()
    if order is None:
        return None
    if order.customer_phone:
        given = _last_digits(phone)
        if len(given) < 8 or given != _last_digits(order.customer_phone):
            return None
    return order


def _failure_key(request):
    return f"order-tracking-failures:{request.META.get('REMOTE_ADDR', '')}"


def too_many_failures(request):
    return cache.get(_failure_key(request), 0) >= MAX_FAILURES


def record_failure(request):
    key = _failure_key(request)
    cache.add(key, 0, FAILURE_WINDOW)
    cache.incr(key)


def remember(session, order):
    """Autorise ce navigateur à voir la commande (et ses mises à jour en direct)."""
    tracked = [pk for pk in session.get(SESSION_KEY, []) if pk != order.pk]
    session[SESSION_KEY] = [order.pk, *tracked][:MAX_TRACKED]


def can_view(session, order_id):
    if session is None:
        return False
    return order_id in session.get(SESSION_KEY, []) or session.get("last_order_id") == order_id
