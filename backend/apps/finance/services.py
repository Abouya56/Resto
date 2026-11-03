from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.utils import timezone

from apps.finance.models import Expense
from apps.inventory.feature import stock_enabled
from apps.inventory.models import StockItem
from apps.orders.models import Order, OrderItem, OrderStatus
from apps.payments.models import Payment, PaymentStatus

PAID_ORDER_STATUSES = (
    OrderStatus.COMPLETED,
    OrderStatus.DELIVERED,
    OrderStatus.SERVED,
    OrderStatus.PICKED_UP,
)


def period_bounds(period="today"):
    now = timezone.localtime()
    today = now.date()
    if period == "today":
        start = today
        end = today
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        end = today
    elif period == "month":
        start = today.replace(day=1)
        end = today
    else:
        start = today - timedelta(days=30)
        end = today
    return start, end


def revenue_queryset(restaurant, start=None, end=None):
    qs = Payment.objects.filter(
        order__restaurant=restaurant,
        status=PaymentStatus.PAID,
    )
    if start:
        qs = qs.filter(paid_at__date__gte=start)
    if end:
        qs = qs.filter(paid_at__date__lte=end)
    return qs


def dashboard_metrics(restaurant, period="today", start=None, end=None):
    """Chiffres d'une période : soit un raccourci (today, week, month), soit des dates précises (start, end)."""
    if start is None or end is None:
        start, end = period_bounds(period)
    payments = revenue_queryset(restaurant, start, end)
    revenue = payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    expenses = Expense.objects.filter(restaurant=restaurant, date__gte=start, date__lte=end).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0")
    orders = Order.objects.filter(restaurant=restaurant, created_at__date__gte=start, created_at__date__lte=end)
    order_count = orders.exclude(status=OrderStatus.CANCELLED).count()
    avg_basket = (revenue / order_count) if order_count else Decimal("0")
    top_products = (
        OrderItem.objects.filter(
            order__restaurant=restaurant,
            order__created_at__date__gte=start,
            order__created_at__date__lte=end,
        )
        .exclude(order__status=OrderStatus.CANCELLED)
        .values("product_name")
        .annotate(qty=Sum("quantity"), sales=Sum("subtotal"))
        .order_by("-qty")[:5]
    )
    low_stock = StockItem.objects.none()
    if stock_enabled():
        low_stock = StockItem.objects.filter(restaurant=restaurant, is_active=True, quantity__lte=F("min_threshold"))
    ongoing = Order.objects.filter(restaurant=restaurant).exclude(
        status__in=[OrderStatus.COMPLETED, OrderStatus.CANCELLED]
    )
    return {
        "period": period,
        "start": start,
        "end": end,
        "revenue": revenue,
        "expenses": expenses,
        "result": revenue - expenses,
        "order_count": order_count,
        "avg_basket": avg_basket,
        "top_products": list(top_products),
        "low_stock_count": low_stock.count(),
        "ongoing_count": ongoing.count(),
        "today_orders": Order.objects.filter(restaurant=restaurant, created_at__date=timezone.localdate()).count(),
    }


def revenue_series(restaurant, grain="day", days=14):
    end = timezone.localdate()
    start = end - timedelta(days=days - 1)
    trunc = {"day": TruncDate, "week": TruncWeek, "month": TruncMonth}[grain]
    qs = (
        revenue_queryset(restaurant, start, end)
        .annotate(bucket=trunc("paid_at"))
        .values("bucket")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("bucket")
    )
    return list(qs)


def day_journal(restaurant, day):
    """Tout ce qui a bougé un jour donné : argent encaissé, argent dépensé, stock."""
    from apps.inventory.models import StockMovement

    payments = list(revenue_queryset(restaurant, day, day).select_related("order").order_by("paid_at"))
    expenses = list(Expense.objects.filter(restaurant=restaurant, date=day).order_by("created_at"))
    cashed = sum((payment.amount for payment in payments), Decimal("0"))
    spent = sum((expense.amount for expense in expenses), Decimal("0"))
    by_method = {}
    for payment in payments:
        label = payment.get_method_display()
        by_method[label] = by_method.get(label, Decimal("0")) + payment.amount
    movements = (
        StockMovement.objects.filter(restaurant=restaurant, created_at__date=day)
        if stock_enabled()
        else StockMovement.objects.none().select_related("item").order_by("item__name")
    )
    stock = {}
    for movement in movements:
        row = stock.setdefault(
            movement.item_id, {"item": movement.item, "in": Decimal("0"), "out": Decimal("0"), "count": None}
        )
        if movement.movement_type == "in":
            row["in"] += movement.quantity
        elif movement.movement_type == "out":
            row["out"] += movement.quantity
        else:
            row["count"] = movement.quantity
    orders = Order.objects.filter(restaurant=restaurant, created_at__date=day).exclude(status=OrderStatus.CANCELLED)
    return {
        "day": day,
        "payments": payments,
        "expenses": expenses,
        "cashed": cashed,
        "spent": spent,
        "balance": cashed - spent,
        "by_method": sorted(by_method.items(), key=lambda pair: -pair[1]),
        "stock": list(stock.values()),
        "order_count": orders.count(),
    }


def daily_summary(restaurant, days=14):
    """Une ligne par jour (le plus récent en haut) : encaissé, dépensé, reste."""
    end = timezone.localdate()
    start = end - timedelta(days=days - 1)
    cashed = {
        row["day"]: row["total"]
        for row in revenue_queryset(restaurant, start, end)
        .annotate(day=TruncDate("paid_at"))
        .values("day")
        .annotate(total=Sum("amount"))
    }
    spent = {
        row["date"]: row["total"]
        for row in Expense.objects.filter(restaurant=restaurant, date__gte=start, date__lte=end)
        .values("date")
        .annotate(total=Sum("amount"))
    }
    rows = []
    for offset in range(days):
        day = end - timedelta(days=offset)
        money_in = cashed.get(day) or Decimal("0")
        money_out = spent.get(day) or Decimal("0")
        rows.append({"day": day, "cashed": money_in, "spent": money_out, "balance": money_in - money_out})
    return rows


PAYMENT_GROUPS = {
    "cash_on_site": ("cash", "Espèces"),
    "cash_on_delivery": ("cash", "Espèces"),
    "mobile_money": ("mobile", "Mobile money"),
    "online": ("online", "En ligne"),
    "simulated": ("test", "Paiement test"),
}


def sales_by_day(restaurant, year, month):
    """L'argent reçu jour par jour pour un mois."""
    return sales_between(restaurant, date(year, month, 1), date(year, month, monthrange(year, month)[1]))


def sales_between(restaurant, first, last):
    """L'argent reçu jour par jour entre deux dates : montant, nombre de paiements, ticket moyen, mode de paiement."""
    rows = {}
    payments = revenue_queryset(restaurant, first, last).annotate(day=TruncDate("paid_at"))
    for payment in payments.values("day", "method").annotate(total=Sum("amount"), n=Count("id")).order_by():
        day = payment["day"]
        row = rows.setdefault(day, {"day": day, "received": Decimal("0"), "count": 0, "methods": {}})
        key, label = PAYMENT_GROUPS.get(payment["method"], ("other", "Autre"))
        row["received"] += payment["total"]
        row["count"] += payment["n"]
        method = row["methods"].setdefault(key, {"label": label, "amount": Decimal("0")})
        method["amount"] += payment["total"]
    days = sorted(rows.values(), key=lambda r: r["day"], reverse=True)
    best = max(days, key=lambda r: r["received"], default=None)
    biggest = best["received"] if best else Decimal("0")
    for row in days:
        row["average"] = row["received"] / row["count"] if row["count"] else Decimal("0")
        row["percent"] = round(float(row["received"] * 100 / biggest)) if biggest else 0
        row["methods"] = sorted(row["methods"].values(), key=lambda m: -m["amount"])
    total = sum((r["received"] for r in days), Decimal("0"))
    return {
        "first": first,
        "last": last,
        "days": days,
        "total": total,
        "count": sum(r["count"] for r in days),
        "best": best,
        "average_per_day": total / len(days) if days else Decimal("0"),
    }
