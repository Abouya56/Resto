"""Architecture de paiement interchangeable. Aucun prestataire réel n'est branché."""
import uuid
from abc import ABC, abstractmethod

from django.conf import settings
from django.utils import timezone

from apps.payments.models import Payment, PaymentMethod, PaymentStatus


class PaymentProvider(ABC):
    name = "base"

    @abstractmethod
    def charge(self, order, method, extra=None):
        raise NotImplementedError


class SimulatedPaymentProvider(PaymentProvider):
    name = "simulated"

    def charge(self, order, method=PaymentMethod.SIMULATED, extra=None):
        extra = extra or {}
        payment = Payment.objects.create(
            order=order,
            amount=order.total,
            method=method or PaymentMethod.SIMULATED,
            status=PaymentStatus.PAID,
            reference=f"SIM-{uuid.uuid4().hex[:12].upper()}",
            provider=self.name,
            provider_payload={"simulated": True, **extra},
            paid_at=timezone.now(),
        )
        return payment


class CashPaymentProvider(PaymentProvider):
    name = "cash"

    def charge(self, order, method=PaymentMethod.CASH_ON_SITE, extra=None):
        payment = Payment.objects.create(
            order=order,
            amount=order.total,
            method=method,
            status=PaymentStatus.PENDING,
            reference=f"CASH-{uuid.uuid4().hex[:12].upper()}",
            provider=self.name,
            provider_payload=extra or {},
        )
        return payment


def get_payment_provider():
    mapping = {
        "simulated": SimulatedPaymentProvider,
        "cash": CashPaymentProvider,
    }
    cls = mapping.get(getattr(settings, "PAYMENT_PROVIDER", "simulated"), SimulatedPaymentProvider)
    return cls()
