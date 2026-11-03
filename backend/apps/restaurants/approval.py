from django.db import transaction
from django.db.models import Q
from django.utils.crypto import get_random_string
from django.utils import timezone

from apps.notifications.services import notify_user
from apps.restaurants.models import Employee, RestaurantStatus
from apps.users.models import User
from apps.users.roles import Role


def notify_platform_admins(title, message, url=""):
    admins = User.objects.filter(
        Q(role=Role.PLATFORM_ADMIN) | Q(is_superuser=True),
        is_active=True,
    ).distinct()
    for admin in admins:
        notify_user(admin, title, message, "restaurant", url)


PASSWORD_CHARS = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sans les lettres qui se ressemblent


def create_manager_account(restaurant):
    """Donne au demandeur son compte gérant, d'après les informations de sa demande.

    Renvoie (compte, mot de passe provisoire). Le mot de passe est None si le compte existait déjà.
    """
    if restaurant.owner_id:
        return restaurant.owner, None
    email = (restaurant.applicant_email or restaurant.email or "").lower()
    if not email:
        return None, None
    user = User.objects.filter(email=email).first()
    password = None
    if user is None:
        first, _, last = (restaurant.applicant_name or restaurant.name).partition(" ")
        password = get_random_string(10, PASSWORD_CHARS)
        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first,
            last_name=last or first,
            phone=restaurant.applicant_phone or restaurant.phone,
            role=Role.MANAGER,
        )
    elif user.role == Role.CUSTOMER:
        user.role = Role.MANAGER
        user.save(update_fields=["role"])
    Employee.objects.get_or_create(user=user, restaurant=restaurant, defaults={"role": Role.MANAGER})
    restaurant.owner = user
    return user, password


@transaction.atomic
def approve_restaurant(restaurant, admin_user, note=""):
    # Identité validée, mais le restaurant ne s'ouvre qu'au premier paiement de licence.
    restaurant.status = RestaurantStatus.UNPAID
    restaurant.is_accepting_orders = False
    restaurant.reviewed_at = timezone.now()
    restaurant.reviewed_by = admin_user
    restaurant.review_note = note
    user, password = create_manager_account(restaurant)
    restaurant.manager_password = password  # à communiquer au gérant ; jamais relu ensuite (le mot de passe est chiffré)
    restaurant.save(
        update_fields=[
            "status",
            "is_accepting_orders",
            "reviewed_at",
            "reviewed_by",
            "review_note",
            "owner",
            "updated_at",
        ]
    )
    if restaurant.owner_id:
        notify_user(
            restaurant.owner,
            "Demande validée",
            f"{restaurant.name} est validé. Il s'ouvrira dès que votre licence sera réglée auprès de la plateforme.",
            "restaurant",
            "/demande-en-attente/",
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


def suspend_restaurant(restaurant, admin_user, note):
    """Coupe l'accès : plus de commandes, le personnel ne peut plus travailler dessus."""
    restaurant.status = RestaurantStatus.SUSPENDED
    restaurant.is_accepting_orders = False
    restaurant.reviewed_at = timezone.now()
    restaurant.reviewed_by = admin_user
    restaurant.review_note = note
    restaurant.save(
        update_fields=["status", "is_accepting_orders", "reviewed_at", "reviewed_by", "review_note", "updated_at"]
    )
    if restaurant.owner_id:
        notify_user(restaurant.owner, "Restaurant suspendu", f"{restaurant.name} a été suspendu : {note}", "restaurant")
    return restaurant


def reactivate_restaurant(restaurant, admin_user, note=""):
    from django.utils import timezone as tz

    licence_over = restaurant.license_until is not None and restaurant.license_until < tz.localdate()
    # Une suspension levée ne rouvre pas un restaurant dont la licence est finie.
    restaurant.status = RestaurantStatus.UNPAID if licence_over else RestaurantStatus.ACTIVE
    restaurant.is_accepting_orders = not licence_over
    restaurant.reviewed_at = timezone.now()
    restaurant.reviewed_by = admin_user
    restaurant.review_note = note
    restaurant.save(
        update_fields=["status", "is_accepting_orders", "reviewed_at", "reviewed_by", "review_note", "updated_at"]
    )
    if restaurant.owner_id:
        notify_user(
            restaurant.owner,
            "Restaurant réactivé",
            f"{restaurant.name} est de nouveau ouvert aux commandes.",
            "restaurant",
            "/gerant/",
        )
    return restaurant
