from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class DeliveryStatus(models.TextChoices):
    UNASSIGNED = "unassigned", "Non attribuée"
    ASSIGNED = "assigned", "Attribuée"
    ACCEPTED = "accepted", "Acceptée"
    PICKED_UP = "picked_up", "Prise en charge"
    IN_TRANSIT = "in_transit", "En cours"
    DELIVERED = "delivered", "Livrée"
    FAILED = "failed", "Échec"


class Delivery(TimeStampedModel):
    """
    Le suivi GPS, le calcul de distance et les frais automatiques
    pourront s'appuyer plus tard sur latitude/longitude et les dates.
    """

    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="delivery")
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deliveries",
    )
    address_text = models.CharField(max_length=400)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.UNASSIGNED)
    assigned_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "livraison"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Livraison {self.order.number}"

    @property
    def restaurant(self):
        return self.order.restaurant
