from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import RestaurantScopedModel, TimeStampedModel


class StockItem(RestaurantScopedModel):
    """Ingrédient ou article en réserve (riz, huile, boissons…)."""

    name = models.CharField("nom", max_length=160)
    unit = models.CharField("unité", max_length=30, default="unité")
    quantity = models.DecimalField("quantité", max_digits=12, decimal_places=3, default=0)
    min_threshold = models.DecimalField("seuil minimal", max_digits=12, decimal_places=3, default=0)
    product = models.ForeignKey(
        "menus.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_items",
        verbose_name="plat lié",
        help_text="Lien optionnel vers un plat (prépare les recettes futures).",
    )
    is_active = models.BooleanField("actif", default=True)

    class Meta:
        verbose_name = "article de stock"
        unique_together = ("restaurant", "name")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.quantity} {self.unit})"

    @property
    def is_low(self):
        return self.quantity <= self.min_threshold


class StockMovementType(models.TextChoices):
    IN = "in", "Entrée"
    OUT = "out", "Sortie"
    ADJUST = "adjust", "Ajustement"


class StockMovement(TimeStampedModel):
    restaurant = models.ForeignKey("restaurants.Restaurant", on_delete=models.CASCADE, related_name="stock_movements")
    item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name="movements")
    movement_type = models.CharField(max_length=10, choices=StockMovementType.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    reason = models.CharField(max_length=255)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    # Sortie automatique : la commande dont la préparation a consommé l'ingrédient.
    order = models.ForeignKey(
        "orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_movements"
    )

    class Meta:
        verbose_name = "mouvement de stock"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.quantity} {self.item.name}"


class RecipeIngredient(TimeStampedModel):
    """Lien plat ↔ stock. Le gérant dit « 1 kg de riz sert 4 plats » ; on garde ce qu'un plat retire (0,25 kg)."""

    product = models.ForeignKey("menus.Product", on_delete=models.CASCADE, related_name="recipe_items")
    stock_item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name="recipe_usages")
    # Précision fine : 1 kg pour 3 plats = 0,333333 kg par plat, sans dérive au fil des ventes.
    quantity = models.DecimalField(max_digits=14, decimal_places=6)

    class Meta:
        unique_together = ("product", "stock_item")
        verbose_name = "ingrédient de recette"

    @property
    def servings(self):
        """Combien de plats sert 1 unité de l'article (inverse de la quantité retirée par plat)."""
        if not self.quantity:
            return None
        value = Decimal(1) / self.quantity
        rounded = value.quantize(Decimal("1"))
        if abs(value - rounded) < Decimal("0.01"):
            return rounded
        return value.quantize(Decimal("0.1"))
