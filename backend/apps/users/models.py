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
    role = models.CharField("rôle", max_length=32, choices=Role.CHOICES, default=Role.CUSTOMER)
    is_active = models.BooleanField("actif", default=True)
    is_staff = models.BooleanField("accès admin", default=False)

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
