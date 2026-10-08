import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import RestaurantScopedModel, TimeStampedModel


class OrderType(models.TextChoices):
    DINE_IN = "dine_in", "Sur place"
    TAKEAWAY = "takeaway", "À emporter"
    DELIVERY = "delivery", "Livraison"


class OrderStatus(models.TextChoices):
    PENDING = "pending", "En attente"
    ACCEPTED = "accepted", "Acceptée"
    PREPARING = "preparing", "En préparation"
    READY = "ready", "Prête"
    SERVED = "served", "Servie"
    PICKED_UP = "picked_up", "Récupérée"
    OUT_FOR_DELIVERY = "out_for_delivery", "En livraison"
    DELIVERED = "delivered", "Livrée"
    COMPLETED = "completed", "Terminée"
    CANCELLED = "cancelled", "Annulée"


STATUS_FLOW = {
    OrderType.DINE_IN: [
        OrderStatus.PENDING,
        OrderStatus.ACCEPTED,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.SERVED,
        OrderStatus.COMPLETED,
    ],
    OrderType.TAKEAWAY: [
        OrderStatus.PENDING,
        OrderStatus.ACCEPTED,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.PICKED_UP,
        OrderStatus.COMPLETED,
    ],
    OrderType.DELIVERY: [
        OrderStatus.PENDING,
        OrderStatus.ACCEPTED,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.OUT_FOR_DELIVERY,
        OrderStatus.DELIVERED,
        OrderStatus.COMPLETED,
    ],
}

ACTIVE_STATUSES = [
    OrderStatus.PENDING,
    OrderStatus.ACCEPTED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.SERVED,
    OrderStatus.PICKED_UP,
    OrderStatus.OUT_FOR_DELIVERY,
    OrderStatus.DELIVERED,
]


class Cart(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="carts",
    )
    session_key = models.CharField(max_length=40, blank=True)
    restaurant = models.ForeignKey("restaurants.Restaurant", on_delete=models.CASCADE, related_name="carts")
    table = models.ForeignKey("tables.DiningTable", on_delete=models.SET_NULL, null=True, blank=True)
    order_type = models.CharField(max_length=20, choices=OrderType.choices, default=OrderType.DINE_IN)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "panier"

    def __str__(self):
        return f"Panier {self.pk} — {self.restaurant}"

    @property
    def subtotal(self):
        return sum((item.subtotal for item in self.items.all()), start=0)

    @property
    def delivery_fee(self):
        if self.order_type == OrderType.DELIVERY:
            return self.restaurant.delivery_fee
        return 0

    @property
    def total(self):
        return self.subtotal + self.delivery_fee


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("menus.Product", on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("cart", "product")

    @property
    def unit_price(self):
        return self.product.price

    @property
    def subtotal(self):
        return self.product.price * self.quantity


class Order(RestaurantScopedModel):
    number = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    table = models.ForeignKey("tables.DiningTable", on_delete=models.SET_NULL, null=True, blank=True)
    order_type = models.CharField(max_length=20, choices=OrderType.choices)
    status = models.CharField(max_length=30, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    note = models.TextField(blank=True)
    delivery_address = models.ForeignKey(
        "users.CustomerAddress",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    delivery_address_text = models.CharField(max_length=400, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "commande"
        ordering = ["-created_at"]

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = self._generate_number()
        super().save(*args, **kwargs)

    def _generate_number(self):
        stamp = timezone.now().strftime("%y%m%d")
        suffix = uuid.uuid4().hex[:6].upper()
        return f"R{stamp}{suffix}"

    @property
    def allowed_next_statuses(self):
        flow = STATUS_FLOW[self.order_type]
        if self.status == OrderStatus.CANCELLED:
            return []
        if self.status not in flow:
            return []
        index = flow.index(self.status)
        nxt = flow[index + 1 :][:1]
        return nxt

    def can_cancel(self):
        return self.status in (OrderStatus.PENDING, OrderStatus.ACCEPTED)

    @property
    def next_status(self):
        nxt = self.allowed_next_statuses
        return nxt[0] if nxt else ""

    @property
    def next_status_label(self):
        nxt = self.next_status
        return OrderStatus(nxt).label if nxt else ""


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("menus.Product", on_delete=models.PROTECT)
    product_name = models.CharField(max_length=180)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.quantity} × {self.product_name}"
