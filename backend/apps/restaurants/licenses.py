"""Licence par restaurant : celui qui paye est ouvert, celui qui ne paye pas reste fermé."""

from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.notifications.services import notify_user
from apps.restaurants.models import LicensePayment, Restaurant, RestaurantStatus

DAYS_PER_MONTH = 30
LICENSE_MONTHS = (1, 3, 6, 12)
WARNING_DAYS = 7  # on prévient le gérant quand il reste moins d'une semaine


def expire_licenses(today=None):
    """Ferme les restaurants dont la licence est dépassée. Renvoie le nombre de restaurants fermés."""
    today = today or timezone.localdate()
    expired = list(
        Restaurant.objects.filter(status=RestaurantStatus.ACTIVE, license_until__lt=today).select_related("owner")
    )
    for restaurant in expired:
        restaurant.status = RestaurantStatus.UNPAID
        restaurant.is_accepting_orders = False
        restaurant.review_note = "Licence expirée : le restaurant rouvre dès que la licence est payée."
        restaurant.save(update_fields=["status", "is_accepting_orders", "review_note", "updated_at"])
        if restaurant.owner_id:
            notify_user(
                restaurant.owner,
                "Licence expirée",
                f"La licence de {restaurant.name} est arrivée à terme : le restaurant est fermé jusqu'au paiement.",
                "restaurant",
            )
    return len(expired)


def warn_ending_licenses(today=None):
    """Prévient le gérant une fois, quand il reste au plus WARNING_DAYS jours. Renvoie le nombre de gérants prévenus."""
    today = today or timezone.localdate()
    ending = (
        Restaurant.objects.filter(
            status=RestaurantStatus.ACTIVE,
            license_until__gte=today,
            license_until__lte=today + timedelta(days=WARNING_DAYS),
        )
        .exclude(license_warned_until=F("license_until"))
        .select_related("owner")
    )
    count = 0
    for restaurant in ending:
        days = (restaurant.license_until - today).days
        when = "aujourd'hui" if days == 0 else f"dans {days} jour{'s' if days > 1 else ''}"
        if restaurant.owner_id:
            notify_user(
                restaurant.owner,
                "Licence bientôt finie",
                f"La licence de {restaurant.name} se termine {when} ({restaurant.license_until:%d/%m/%Y}). "
                "Contactez la plateforme pour la renouveler : sans paiement, le restaurant se fermera.",
                "restaurant",
                "/gerant/licence/",
            )
            count += 1
        restaurant.license_warned_until = restaurant.license_until
        restaurant.save(update_fields=["license_warned_until"])
    return count


def check_licenses(today=None):
    """Le contrôle régulier : prévenir ceux qui arrivent à la fin, fermer ceux qui l'ont dépassée."""
    warned = warn_ending_licenses(today)
    closed = expire_licenses(today)
    return warned, closed


@transaction.atomic
def record_license_payment(restaurant, months, admin_user, amount=0, note=""):
    """Le restaurant a payé : on prolonge sa licence et on l'ouvre. Renvoie le paiement créé."""
    if months not in LICENSE_MONTHS:
        raise ValueError("Durée de licence inconnue.")
    if restaurant.status not in (RestaurantStatus.ACTIVE, RestaurantStatus.UNPAID):
        raise ValueError("Ce restaurant ne peut pas recevoir de licence dans son état actuel.")
    today = timezone.localdate()
    start = today
    if restaurant.status == RestaurantStatus.ACTIVE and restaurant.license_until and restaurant.license_until > today:
        start = restaurant.license_until  # payer en avance ne fait pas perdre de jours
    valid_until = start + timedelta(days=DAYS_PER_MONTH * months)
    payment = LicensePayment.objects.create(
        restaurant=restaurant,
        months=months,
        amount=amount or 0,
        valid_until=valid_until,
        recorded_by=admin_user,
        note=note[:255],
    )
    was_closed = restaurant.status != RestaurantStatus.ACTIVE
    restaurant.license_until = valid_until
    restaurant.status = RestaurantStatus.ACTIVE
    if was_closed:
        restaurant.is_accepting_orders = True
        restaurant.review_note = ""
    restaurant.reviewed_by = admin_user
    restaurant.reviewed_at = timezone.now()
    restaurant.save(
        update_fields=["license_until", "status", "is_accepting_orders", "review_note", "reviewed_by", "reviewed_at", "updated_at"]
    )
    if restaurant.owner_id:
        notify_user(
            restaurant.owner,
            "Licence enregistrée",
            f"Merci : {restaurant.name} est ouvert jusqu'au {valid_until:%d/%m/%Y}.",
            "restaurant",
            "/gerant/",
        )
    return payment


def license_info(restaurant):
    """Ce que le super admin et le gérant doivent savoir : état, date de fin, jours restants."""
    today = timezone.localdate()
    until = restaurant.license_until
    if restaurant.status == RestaurantStatus.UNPAID:
        state = "unpaid"
    elif until is None:
        state = "free"
    elif until < today:
        state = "expired"
    elif (until - today).days <= WARNING_DAYS:
        state = "ending"
    else:
        state = "valid"
    return {
        "state": state,
        "until": until,
        "days_left": (until - today).days if until else None,
    }
