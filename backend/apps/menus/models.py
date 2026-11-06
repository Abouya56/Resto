from decimal import Decimal, InvalidOperation

from django.db import models

from apps.core.models import RestaurantScopedModel


class Category(RestaurantScopedModel):
    name = models.CharField("nom", max_length=120)
    description = models.TextField("description", blank=True)
    sort_order = models.PositiveIntegerField("ordre", default=0)
    is_active = models.BooleanField("active", default=True)

    class Meta:
        verbose_name = "catégorie"
        ordering = ["sort_order", "name"]
        unique_together = ("restaurant", "name")

    def __str__(self):
        return f"{self.name} ({self.restaurant})"


class Product(RestaurantScopedModel):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products", verbose_name="catégorie")
    name = models.CharField("nom", max_length=180)
    description = models.TextField("description", blank=True)
    price = models.DecimalField("prix", max_digits=10, decimal_places=2)
    # Le même plat à d'autres prix (quantités différentes), ex. riz à 500 et à 1 000 : sans nom de portion.
    extra_prices = models.JSONField("autres prix", default=list, blank=True)
    image = models.ImageField("image", upload_to="products/", blank=True, null=True)
    is_available = models.BooleanField("disponible", default=True)
    # Calculé par le stock : un ingrédient de la recette manque pour faire une portion.
    out_of_stock = models.BooleanField("épuisé (stock)", default=False, editable=False)
    is_active = models.BooleanField("actif", default=True)
    prep_minutes = models.PositiveIntegerField("temps de préparation (min)", default=15)

    class Meta:
        verbose_name = "produit"
        ordering = ["category__sort_order", "name"]
        unique_together = ("restaurant", "name")

    def __str__(self):
        return self.name

    @property
    def sold_out(self):
        """Épuisé d'après le stock. Sans gestion de stock, un plat n'est jamais épuisé."""
        from apps.inventory.feature import stock_enabled

        return stock_enabled() and self.out_of_stock

    @property
    def price_options(self):
        """Tous les prix du plat, du moins cher au plus cher (le prix principal compris)."""
        prices = {Decimal(self.price)}
        for value in self.extra_prices or []:
            try:
                amount = Decimal(str(value))
            except (InvalidOperation, ValueError):
                continue
            if amount > 0:
                prices.add(amount)
        return sorted(prices)

    @property
    def has_several_prices(self):
        return len(self.price_options) > 1

    def label_for(self, price):
        """Nom écrit sur la commande et le reçu : avec le prix quand le plat en a plusieurs."""
        if not self.has_several_prices:
            return self.name
        from apps.core.templatetags.resto import prix

        suffix = f" · {prix(price)}"
        return self.name[: 180 - len(suffix)] + suffix

    @property
    def can_be_ordered(self):
        return self.is_active and self.is_available and not self.sold_out

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.category_id and self.category.restaurant_id != self.restaurant_id:
            raise ValidationError("La catégorie doit appartenir au même restaurant.")
