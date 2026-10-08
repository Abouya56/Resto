from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from apps.core.models import TimeStampedModel
from apps.users.managers import UserManager
from apps.users.roles import Role


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    email = models.EmailField("adresse e-mail", unique=True)
    first_name = models.CharField("prénom", max_length=150)
    last_name = models.CharField("nom", max_length=150)
    phone = models.CharField("téléphone", max_length=30, blank=True)
    role = models.CharField(max_length=32, choices=Role.CHOICES, default=Role.CUSTOMER)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.get_full_name() or self.email

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name

    @property
    def is_platform_admin(self):
        return self.role == Role.PLATFORM_ADMIN or self.is_superuser

    @property
    def is_customer(self):
        return self.role == Role.CUSTOMER


class CustomerAddress(TimeStampedModel):
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField("nom", max_length=80, default="Domicile")
    line1 = models.CharField("adresse", max_length=255)
    city = models.CharField("ville", max_length=120)
    district = models.CharField("quartier", max_length=120, blank=True)
    instructions = models.TextField("indications", blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name = "adresse client"
        verbose_name_plural = "adresses clients"
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"{self.label} — {self.line1}, {self.city}"

    def save(self, *args, **kwargs):
        if self.is_default:
            CustomerAddress.objects.filter(customer=self.customer, is_default=True).exclude(
                pk=self.pk
            ).update(is_default=False)
        super().save(*args, **kwargs)
