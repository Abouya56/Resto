from django.conf import settings
from django.db import models

from apps.core.models import RestaurantScopedModel, TimeStampedModel


class StockItem(RestaurantScopedModel):
    """Matière première ou article de stock. Les recettes produits viendront plus tard."""

    name = models.CharField(max_length=160)
    unit = models.CharField(max_length=30, default="unité")
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    min_threshold = models.DecimalField("seuil minimal", max_digits=12, decimal_places=3, default=0)
    product = models.ForeignKey(
        "menus.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_items",
        help_text="Lien optionnel vers un plat (prépare les recettes futures).",
    )
    is_active = models.BooleanField(default=True)

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

    class Meta:
        verbose_name = "mouvement de stock"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.quantity} {self.item.name}"


class RecipeIngredient(TimeStampedModel):
    """Préparé pour relier un plat à ses matières premières (non obligatoire au MVP)."""

    product = models.ForeignKey("menus.Product", on_delete=models.CASCADE, related_name="recipe_items")
    stock_item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name="recipe_usages")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        unique_together = ("product", "stock_item")
        verbose_name = "ingrédient de recette"
