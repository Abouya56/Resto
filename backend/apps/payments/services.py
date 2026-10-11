from django.utils import timezone

from apps.payments.models import PaymentMethod, PaymentStatus

CASH_METHODS = (PaymentMethod.CASH_ON_SITE, PaymentMethod.CASH_ON_DELIVERY)


def mark_order_paid(order, only_cash=False):
    """Passe en « Payé » les paiements en attente d'une commande. Renvoie le nombre de paiements encaissés."""
    payments = order.payments.filter(status=PaymentStatus.PENDING)
    if only_cash:
        payments = payments.filter(method__in=CASH_METHODS)
    return payments.update(status=PaymentStatus.PAID, paid_at=timezone.now(), updated_at=timezone.now())
