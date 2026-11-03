from django.conf import settings
from django.core.management.base import BaseCommand

from apps.tables.models import DiningTable
from apps.tables.services import ensure_qrcode


class Command(BaseCommand):
    help = "Remet à jour tous les QR codes avec l'adresse actuelle du site (SITE_URL), sans changer leurs jetons."

    def handle(self, *args, **options):
        self.stdout.write(f"Adresse du site : {settings.SITE_URL}")
        count = 0
        for table in (
            DiningTable.objects.filter(is_active=True).select_related("restaurant").order_by("restaurant_id", "number")
        ):
            qr = ensure_qrcode(table)
            count += 1
            self.stdout.write(f"  {table.restaurant.name} · table {table.number} -> {qr.public_url}")
        self.stdout.write(self.style.SUCCESS(f"{count} QR code(s) à jour."))
