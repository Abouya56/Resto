import secrets
import uuid
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.urls import reverse

from apps.core.models import RestaurantScopedModel, TimeStampedModel


class TableStatus(models.TextChoices):
    FREE = "free", "Libre"
    OCCUPIED = "occupied", "Occupée"
    RESERVED = "reserved", "Réservée"
    INACTIVE = "inactive", "Inactive"


class DiningTable(RestaurantScopedModel):
    number = models.CharField("numéro / nom", max_length=40)
    capacity = models.PositiveIntegerField(default=4)
    status = models.CharField(max_length=20, choices=TableStatus.choices, default=TableStatus.FREE)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "table"
        unique_together = ("restaurant", "number")
        ordering = ["number"]

    def __str__(self):
        return f"Table {self.number} — {self.restaurant}"

    def public_path(self):
        return reverse(
            "orders:table_menu",
            kwargs={"restaurant_slug": self.restaurant.slug, "table_id": self.pk},
        )


class QRCode(TimeStampedModel):
    table = models.OneToOneField(DiningTable, on_delete=models.CASCADE, related_name="qrcode")
    token = models.CharField(max_length=64, unique=True, default=uuid.uuid4)
    public_url = models.URLField(blank=True)
    image = models.ImageField(upload_to="qrcodes/", blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "QR code"

    def __str__(self):
        return f"QR {self.table}"

    def build_url(self):
        base = settings.SITE_URL.rstrip("/")
        return f"{base}{self.table.public_path()}?token={self.token}"

    def generate_image(self):
        import qrcode

        self.public_url = self.build_url()
        qr = qrcode.QRCode(version=1, box_size=10, border=3)
        qr.add_data(self.public_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#1a1a1a", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        filename = f"table-{self.table.restaurant.slug}-{self.table.pk}.png"
        self.image.save(filename, ContentFile(buffer.getvalue()), save=False)

    def regenerate(self):
        self.token = secrets.token_urlsafe(24)
        self.is_active = True
        self.generate_image()
        self.save()

    def save(self, *args, **kwargs):
        if not self.public_url or not self.image:
            self.generate_image()
        super().save(*args, **kwargs)
