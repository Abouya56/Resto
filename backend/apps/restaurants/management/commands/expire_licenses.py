from django.core.management.base import BaseCommand

from apps.restaurants.licenses import check_licenses


class Command(BaseCommand):
    help = "Ferme les restaurants dont la licence est arrivée à terme (à lancer chaque nuit si possible)."

    def handle(self, *args, **options):
        warned, closed = check_licenses()
        self.stdout.write(
            f"{warned} gérant(s) prévenu(s) d'une fin proche, {closed} restaurant(s) fermé(s) pour licence expirée."
        )
