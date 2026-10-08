from django.conf import settings
from django.db import models
from django.utils.text import slugify

from apps.core.models import TimeStampedModel
from apps.users.roles import Role


class RestaurantStatus(models.TextChoices):
    DRAFT = "draft", "Brouillon"
    ACTIVE = "active", "Actif"
    SUSPENDED = "suspended", "Suspendu"
    CLOSED = "closed", "Fermé"


class SubscriptionPlan(models.TextChoices):
    TRIAL = "trial", "Essai"
    STARTER = "starter", "Starter"
    PRO = "pro", "Professionnel"


class Restaurant(TimeStampedModel):
    name = models.CharField("nom", max_length=180)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to="restaurants/logos/", blank=True, null=True)
    cover = models.ImageField(upload_to="restaurants/covers/", blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField("adresse", max_length=255)
    city = models.CharField("ville", max_length=120)
    district = models.CharField("quartier", max_length=120, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    status = models.CharField(max_length=20, choices=RestaurantStatus.choices, default=RestaurantStatus.ACTIVE)
    delivery_fee = models.DecimalField("frais de livraison", max_digits=10, decimal_places=2, default=0)
    min_delivery_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estimated_prep_minutes = models.PositiveIntegerField(default=25)
    is_accepting_orders = models.BooleanField(default=True)
    subscription_plan = models.CharField(
        max_length=20, choices=SubscriptionPlan.choices, default=SubscriptionPlan.TRIAL
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_restaurants",
    )

    class Meta:
        verbose_name = "restaurant"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "restaurant"
            slug = base
            index = 1
            while Restaurant.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                index += 1
                slug = f"{base}-{index}"
            self.slug = slug
        super().save(*args, **kwargs)


class EmployeeStatus(models.TextChoices):
    ACTIVE = "active", "Actif"
    INACTIVE = "inactive", "Inactif"


class Employee(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employments")
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="employees")
    role = models.CharField(max_length=32, choices=[c for c in Role.CHOICES if c[0] in Role.STAFF])
    status = models.CharField(max_length=20, choices=EmployeeStatus.choices, default=EmployeeStatus.ACTIVE)
    is_active = models.BooleanField(default=True)
    hired_at = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "employé"
        unique_together = ("user", "restaurant")
        ordering = ["restaurant", "role", "user__last_name"]

    def __str__(self):
        return f"{self.user} — {self.get_role_display()} ({self.restaurant})"

    def save(self, *args, **kwargs):
        self.is_active = self.status == EmployeeStatus.ACTIVE
        super().save(*args, **kwargs)
