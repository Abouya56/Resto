from django.utils import timezone

from apps.orders.models import OrderType
from apps.payments.models import PaymentMethod, PaymentStatus

CASH_METHODS = (PaymentMethod.CASH_ON_SITE, PaymentMethod.CASH_ON_DELIVERY)
# Ce que le personnel choisit à l'encaissement : de l'argent liquide ou un paiement mobile.
COLLECT_CHOICES = (("cash", "Espèces"), ("mobile", "Mobile"))


def collected_method(order, choice):
    """Le moyen de paiement à enregistrer, ou None si le personnel n'a rien précisé."""
    if choice == "mobile":
        return PaymentMethod.MOBILE_MONEY
    if choice == "cash":
        return PaymentMethod.CASH_ON_DELIVERY if order.order_type == OrderType.DELIVERY else PaymentMethod.CASH_ON_SITE
    return None


def mark_order_paid(order, only_cash=False, method=None):
    """Passe en « Payé » les paiements en attente d'une commande. Renvoie le nombre de paiements encaissés.

    Avec `method`, on note comment l'argent est arrivé (espèces ou mobile).
    """
    payments = order.payments.filter(status=PaymentStatus.PENDING)
    if only_cash:
        payments = payments.filter(method__in=CASH_METHODS)
    changes = {"status": PaymentStatus.PAID, "paid_at": timezone.now(), "updated_at": timezone.now()}
    if method:
        changes["method"] = method
    return payments.update(**changes)
