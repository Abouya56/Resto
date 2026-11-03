from django.conf import settings

from apps.core.tenancy import get_user_restaurant_ids, is_platform_admin
from apps.users.roles import Role


def site_identity():
    """Nom et logo de la plateforme, réglés par le super-admin (le texte « Resto » sans logo par défaut)."""
    from apps.core.models import SiteSettings

    try:
        site = SiteSettings.load()
    except Exception:  # noqa: BLE001 - base pas encore migrée : on garde l'identité par défaut
        return {"site_name": "Resto", "site_logo_url": ""}
    return {"site_name": site.site_name or "Resto", "site_logo_url": site.logo.url if site.logo else ""}


def nav_badges(user, restaurant, employment):
    """Ce qui attend une action : demandes à valider (super admin), commandes à accepter (restaurant)."""
    from apps.orders.models import Order, OrderStatus
    from apps.restaurants.models import Restaurant, RestaurantStatus

    if not (user and user.is_authenticated):
        return {}
    if is_platform_admin(user):
        return {
            "pending_requests": Restaurant.objects.filter(status=RestaurantStatus.PENDING).count(),
            "licenses_due": Restaurant.objects.filter(status=RestaurantStatus.UNPAID).count(),
        }
    if restaurant and employment and employment.role in (Role.MANAGER, Role.RECEPTION):
        return {"orders_pending": Order.objects.filter(restaurant=restaurant, status=OrderStatus.PENDING).count()}
    return {}


def staff_context(request):
    user = getattr(request, "user", None)
    restaurant = getattr(request, "current_restaurant", None)
    employment = getattr(request, "current_employment", None)
    unread = 0
    if user and user.is_authenticated:
        unread = user.notifications.filter(is_read=False).count()
    restaurant_approved = bool(restaurant and restaurant.is_approved)
    return {
        **site_identity(),
        "current_restaurant": restaurant,
        "current_employment": employment,
        "restaurant_approved": restaurant_approved,
        "is_platform_admin": bool(user and is_platform_admin(user)),
        "staff_role": getattr(employment, "role", None),
        "Role": Role,
        "demo_logins": getattr(settings, "DEMO_LOGINS", False),
        "stock_enabled": getattr(settings, "STOCK_ENABLED", False),
        "unread_notifications": unread,
        "nav_badges": nav_badges(user, restaurant, employment),
        "accessible_restaurant_ids": get_user_restaurant_ids(user) if user else set(),
    }
