from django.db.models import Q
from django.utils import timezone

from apps.notifications.services import notify_user
from apps.restaurants.models import RestaurantStatus
from apps.users.models import User
from apps.users.roles import Role


def notify_platform_admins(title, message, url=""):
    admins = User.objects.filter(
        Q(role=Role.PLATFORM_ADMIN) | Q(is_superuser=True),
        is_active=True,
    ).distinct()
    for admin in admins:
        notify_user(admin, title, message, "restaurant", url)


def approve_restaurant(restaurant, admin_user, note=""):
    restaurant.status = RestaurantStatus.ACTIVE
    restaurant.is_accepting_orders = False
    restaurant.reviewed_at = timezone.now()
    restaurant.reviewed_by = admin_user
    restaurant.review_note = note
    restaurant.save(
        update_fields=[
            "status",
            "is_accepting_orders",
            "reviewed_at",
            "reviewed_by",
            "review_note",
            "updated_at",
        ]
    )
    if restaurant.owner_id:
        notify_user(
            restaurant.owner,
            "Restaurant validé",
            f"{restaurant.name} a été validé. Connectez-vous pour renseigner vos informations.",
            "restaurant",
            "/gerant/etablissement/",
        )
    return restaurant


def reject_restaurant(restaurant, admin_user, note=""):
    restaurant.status = RestaurantStatus.REJECTED
    restaurant.is_accepting_orders = False
    restaurant.reviewed_at = timezone.now()
    restaurant.reviewed_by = admin_user
    restaurant.review_note = note
    restaurant.save(
        update_fields=[
            "status",
            "is_accepting_orders",
            "reviewed_at",
            "reviewed_by",
            "review_note",
            "updated_at",
        ]
    )
    if restaurant.owner_id:
        notify_user(
            restaurant.owner,
            "Demande refusée",
            note or f"La demande pour {restaurant.name} n'a pas été validée.",
            "restaurant",
            "/demande-en-attente/",
        )
    return restaurant
