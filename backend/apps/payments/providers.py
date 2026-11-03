"""Pas de paiement en ligne : le restaurant encaisse lui-même, en espèces ou par mobile money."""

import uuid

from apps.payments.models import Payment, PaymentMethod, PaymentStatus


class CashPaymentProvider:
    """Crée un paiement « en attente » : il passe à « payé » quand le personnel encaisse."""

    name = "cash"

    def charge(self, order, method=PaymentMethod.CASH_ON_SITE, extra=None):
        return Payment.objects.create(
            order=order,
            amount=order.total,
            method=method,
            status=PaymentStatus.PENDING,
            reference=f"CASH-{uuid.uuid4().hex[:12].upper()}",
            provider=self.name,
            provider_payload=extra or {},
        )


def get_payment_provider():
    return CashPaymentProvider()
