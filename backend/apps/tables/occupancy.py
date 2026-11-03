"""État réel des tables, calculé à partir des commandes en cours (le champ « status » n'est pas tenu à jour)."""

from django.db.models import Exists, OuterRef

# Du plus urgent au plus calme : une table prend l'état de sa commande la plus urgente.
TABLE_STATES = (
    ("pending", "À accepter", ("pending",)),
    ("busy", "Occupée", ("accepted", "preparing", "ready", "served")),
)
OPEN_STATUSES = tuple(status for _, _, statuses in TABLE_STATES for status in statuses)


def open_dine_in_orders(restaurant):
    from apps.orders.models import Order, OrderType
    from apps.payments.models import Payment, PaymentStatus

    paid = Payment.objects.filter(order=OuterRef("pk"), status=PaymentStatus.PAID)
    return (
        Order.objects.filter(restaurant=restaurant, order_type=OrderType.DINE_IN, status__in=OPEN_STATUSES)
        .select_related("restaurant", "table")
        .prefetch_related("items")
        .annotate(is_paid=Exists(paid))
        .order_by("created_at")
    )


def attach_states(tables, orders):
    """Ajoute à chaque table : .orders (ses commandes ouvertes), .state et .state_label."""
    for table in tables:
        table.orders = [order for order in orders if order.table_id == table.pk]
        table.state, table.state_label = "free", "Libre"
        for state, label, statuses in TABLE_STATES:
            if any(order.status in statuses for order in table.orders):
                table.state, table.state_label = state, label
                break
        table.open_total = sum(order.total for order in table.orders)
    return tables
