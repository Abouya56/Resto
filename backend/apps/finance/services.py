from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.utils import timezone

from apps.finance.models import Expense
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


def dashboard_metrics(restaurant, period="today"):
    start, end = period_bounds(period)
    payments = revenue_queryset(restaurant, start, end)
    revenue = payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    expenses = (
        Expense.objects.filter(restaurant=restaurant, date__gte=start, date__lte=end).aggregate(total=Sum("amount"))[
            "total"
        ]
        or Decimal("0")
    )
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
    low_stock = StockItem.objects.filter(restaurant=restaurant, is_active=True).filter(
        quantity__lte=models_f("min_threshold")
    )
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
        "today_orders": Order.objects.filter(
            restaurant=restaurant, created_at__date=timezone.localdate()
        ).count(),
    }


def models_f(field):
    from django.db.models import F

    return F(field)


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
