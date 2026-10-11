from django.conf import settings
from django.db import models

from apps.core.models import RestaurantScopedModel


class ExpenseCategory(models.TextChoices):
    SUPPLIES = "supplies", "Approvisionnement"
    SALARIES = "salaries", "Salaires"
    RENT = "rent", "Loyer"
    UTILITIES = "utilities", "Charges"
    MAINTENANCE = "maintenance", "Maintenance"
    MARKETING = "marketing", "Marketing"
    OTHER = "other", "Autre"


class Expense(RestaurantScopedModel):
    category = models.CharField("catégorie", max_length=30, choices=ExpenseCategory.choices, default=ExpenseCategory.OTHER)
    amount = models.DecimalField("montant", max_digits=12, decimal_places=2)
    description = models.CharField("description", max_length=255)
    date = models.DateField("date")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="saisi par")
    receipt = models.FileField("justificatif", upload_to="expenses/", blank=True, null=True)

    class Meta:
        verbose_name = "dépense"
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.amount} — {self.description}"
