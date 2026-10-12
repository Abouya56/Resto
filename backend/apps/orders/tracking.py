"""Suivi d'une commande sans compte : numéro de commande + téléphone donné à la commande."""

import re

from django.core.cache import cache

from apps.orders.models import Order

SESSION_KEY = "tracked_orders"
MAX_TRACKED = 10
MAX_FAILURES = 10  # essais ratés par adresse IP
FAILURE_WINDOW = 15 * 60  # secondes


def normalize_number(number):
    return re.sub(r"[^A-Za-z0-9]", "", number or "").upper()


def _last_digits(phone):
    return "".join(c for c in phone or "" if c.isdigit())[-8:]


def find_order(number, phone):
    """La commande si le numéro existe et que le téléphone correspond (quand la commande en a un)."""
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
