from django.db import models

from apps.core.models import RestaurantScopedModel


class Category(RestaurantScopedModel):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField("ordre", default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "catégorie"
        ordering = ["sort_order", "name"]
        unique_together = ("restaurant", "name")

    def __str__(self):
        return f"{self.name} ({self.restaurant})"


class Product(RestaurantScopedModel):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    is_available = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    prep_minutes = models.PositiveIntegerField("temps de préparation (min)", default=15)

    class Meta:
        verbose_name = "produit"
        ordering = ["category__sort_order", "name"]
        unique_together = ("restaurant", "name")

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.category_id and self.category.restaurant_id != self.restaurant_id:
            raise ValidationError("La catégorie doit appartenir au même restaurant.")
