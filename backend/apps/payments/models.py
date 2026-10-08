from django.db import models

from apps.core.models import TimeStampedModel


class PaymentMethod(models.TextChoices):
    CASH_ON_SITE = "cash_on_site", "Espèces sur place"
    CASH_ON_DELIVERY = "cash_on_delivery", "Paiement à la livraison"
    MOBILE_MONEY = "mobile_money", "Paiement mobile"
    ONLINE = "online", "Paiement en ligne"
    SIMULATED = "simulated", "Paiement simulé (dev)"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "En attente"
    AUTHORIZED = "authorized", "Autorisé"
    PAID = "paid", "Payé"
    FAILED = "failed", "Échoué"
    REFUNDED = "refunded", "Remboursé"


class Payment(TimeStampedModel):
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=30, choices=PaymentMethod.choices, default=PaymentMethod.SIMULATED)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    reference = models.CharField(max_length=64, unique=True)
    provider = models.CharField(max_length=40, default="simulated")
    provider_payload = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "paiement"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} — {self.amount}"

    @property
    def restaurant(self):
        return self.order.restaurant
