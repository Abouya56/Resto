import uuid

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.core.models import RestaurantScopedModel, TimeStampedModel


class OrderType(models.TextChoices):
    DINE_IN = "dine_in", "Sur place"
    TAKEAWAY = "takeaway", "À emporter"
    DELIVERY = "delivery", "Livraison"
    PREORDER = "preorder", "À l'avance"
    COUNTER = "counter", "Vente au comptoir"


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
    # Commandée de chez soi, mangée au restaurant à l'heure d'arrivée choisie.
    OrderType.PREORDER: [
        OrderStatus.PENDING,
        OrderStatus.ACCEPTED,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.SERVED,
        OrderStatus.COMPLETED,
    ],
    # Vendue et encaissée sur le moment par la réception, pour un client qui n'a pas commandé sur le site.
    OrderType.COUNTER: [OrderStatus.PENDING, OrderStatus.ACCEPTED, OrderStatus.COMPLETED],
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

    @property
    def item_count(self):
        return sum((item.quantity for item in self.items.all()), start=0)

    @property
    def missing_for_delivery(self):
        if self.order_type != OrderType.DELIVERY:
            return 0
        missing = self.restaurant.min_delivery_amount - self.subtotal
        return missing if missing > 0 else 0


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("menus.Product", on_delete=models.CASCADE)
    # Le prix choisi quand le plat en a plusieurs (vide : le prix principal).
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("cart", "product", "price")

    @property
    def unit_price(self):
        # Un prix retiré entre-temps par le gérant : on revient au prix principal.
        if self.price is not None and self.price in self.product.price_options:
            return self.price
        return self.product.price

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    @property
    def label(self):
        return self.product.label_for(self.unit_price)


class Order(RestaurantScopedModel):
    number = models.CharField("référence", max_length=20, unique=True, editable=False)
    # Numéro court, remis à zéro chaque jour par restaurant : celui qu'on annonce au comptoir.
    service_date = models.DateField("jour de service", null=True, blank=True, editable=False)
    daily_number = models.PositiveIntegerField("numéro du jour", null=True, blank=True, editable=False)
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
    scheduled_for = models.DateField("jour de livraison", null=True, blank=True)
    arrival_at = models.DateTimeField("heure d'arrivée", null=True, blank=True)
    delivery_address_text = models.CharField("adresse", max_length=400, blank=True)
    delivery_city = models.CharField("ville", max_length=120, blank=True)
    delivery_district = models.CharField("quartier", max_length=120, blank=True)
    delivery_landmark = models.CharField("point de repère", max_length=255, blank=True)
    latitude = models.DecimalField("latitude", max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField("longitude", max_digits=9, decimal_places=6, null=True, blank=True)
    customer_first_name = models.CharField("prénom", max_length=150, blank=True)
    customer_last_name = models.CharField("nom", max_length=150, blank=True)
    customer_phone = models.CharField("téléphone", max_length=30, blank=True)
    customer_email = models.EmailField("e-mail", blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "commande"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["restaurant", "service_date", "daily_number"],
                name="unique_daily_number_per_restaurant",
            )
        ]

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = self._generate_number()
        if self.pk is None and self.daily_number is None:
            with transaction.atomic():
                self._assign_daily_number()
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)

    def _generate_number(self):
        stamp = timezone.now().strftime("%y%m%d")
        suffix = uuid.uuid4().hex[:6].upper()
        return f"R{stamp}{suffix}"

    def _assign_daily_number(self):
        from apps.restaurants.models import Restaurant

        # Verrou sur le restaurant : deux commandes simultanées n'obtiennent pas le même numéro.
        Restaurant.objects.select_for_update().filter(pk=self.restaurant_id).first()
        self.service_date = timezone.localdate()
        last = Order.objects.filter(restaurant_id=self.restaurant_id, service_date=self.service_date).aggregate(
            last=models.Max("daily_number")
        )["last"]
        self.daily_number = (last or 0) + 1

    @property
    def short_number(self):
        """« 042 » : le numéro à annoncer au comptoir ou au serveur."""
        return f"{self.daily_number:03d}" if self.daily_number else ""

    @property
    def reference(self):
        """La référence unique, découpée pour être recopiée sans erreur : R261012-3E4FE3."""
        if len(self.number) == 13 and self.number.startswith("R"):
            return f"{self.number[:7]}-{self.number[7:]}"
        return self.number

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

    @property
    def waiting_minutes(self):
        """Minutes écoulées depuis la commande (pour l'écran cuisine)."""
        return int((timezone.now() - self.created_at).total_seconds() // 60)

    @property
    def waiting_label(self):
        """« 12 min », « 2 h 05 » ou « 3 j » : une durée qu'on lit d'un coup d'œil."""
        minutes = self.waiting_minutes
        if minutes < 60:
            return f"{minutes} min"
        if minutes < 24 * 60:
            return f"{minutes // 60} h {minutes % 60:02d}"
        return f"{minutes // (24 * 60)} j"

    @property
    def is_late(self):
        if self.order_type == OrderType.PREORDER:
            return False  # le client arrive à l'heure choisie : le restaurant n'est pas en retard avant
        return self.waiting_minutes > self.restaurant.estimated_prep_minutes

    @property
    def arrival_label(self):
        """« 12:30 » : l'heure à laquelle le client de la commande à l'avance arrive."""
        return timezone.localtime(self.arrival_at).strftime("%H:%M") if self.arrival_at else ""

    @property
    def arrival_in_label(self):
        """« dans 25 min », « dans 1 h 10 » ou « heure passée »."""
        if not self.arrival_at:
            return ""
        minutes = int((self.arrival_at - timezone.now()).total_seconds() // 60)
        if minutes < 0:
            return "heure passée"
        if minutes < 60:
            return f"dans {minutes} min"
        return f"dans {minutes // 60} h {minutes % 60:02d}"

    @property
    def contact_name(self):
        full = f"{self.customer_first_name} {self.customer_last_name}".strip()
        if full:
            return full
        if self.customer_id:
            return self.customer.get_full_name()
        return ""

    @property
    def is_for_later(self):
        """Commande de livraison prévue un autre jour qu'aujourd'hui (« demain »)."""
        return bool(self.scheduled_for and self.scheduled_for > timezone.localdate())

    @property
    def day_label(self):
        if not self.scheduled_for:
            return ""
        return "Demain" if self.is_for_later else "Aujourd'hui"

    @property
    def location_display(self):
        parts = [
            self.delivery_address_text,
            self.delivery_district,
            self.delivery_city,
        ]
        return ", ".join(part for part in parts if part)


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
