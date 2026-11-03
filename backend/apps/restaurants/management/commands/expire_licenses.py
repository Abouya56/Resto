from django.core.management.base import BaseCommand

from apps.restaurants.licenses import expire_licenses


class Command(BaseCommand):
    help = "Ferme les restaurants dont la licence est arrivée à terme (à lancer chaque nuit si possible)."

    def handle(self, *args, **options):
        closed = expire_licenses()
        self.stdout.write(f"{closed} restaurant(s) fermé(s) pour licence expirée.")
