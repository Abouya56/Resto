from apps.core.tenancy import get_user_restaurant_ids, is_platform_admin
from apps.users.roles import Role


def staff_context(request):
    user = getattr(request, "user", None)
    restaurant = getattr(request, "current_restaurant", None)
    employment = getattr(request, "current_employment", None)
    unread = 0
    if user and user.is_authenticated:
        unread = user.notifications.filter(is_read=False).count()
    restaurant_approved = bool(restaurant and restaurant.is_approved)
    return {
        "current_restaurant": restaurant,
        "current_employment": employment,
        "restaurant_approved": restaurant_approved,
        "is_platform_admin": bool(user and is_platform_admin(user)),
        "staff_role": getattr(employment, "role", None),
        "Role": Role,
        "unread_notifications": unread,
        "accessible_restaurant_ids": get_user_restaurant_ids(user) if user else set(),
    }
