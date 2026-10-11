"""Isolation multi-restaurant : helpers utilisés par les vues, permissions et querysets."""

from django.core.exceptions import PermissionDenied


def is_platform_admin(user):
    return bool(user and user.is_authenticated and user.is_platform_admin)


def get_user_restaurant_ids(user):
    if not user or not user.is_authenticated:
        return set()
    if is_platform_admin(user):
        from apps.restaurants.models import Restaurant

        return set(Restaurant.objects.values_list("id", flat=True))
    return set(
        user.employments.filter(is_active=True).values_list("restaurant_id", flat=True)
    )


def get_active_employment(user, restaurant_id=None):
    if not user or not user.is_authenticated:
        return None
    qs = user.employments.filter(is_active=True).select_related("restaurant")
    if restaurant_id:
        qs = qs.filter(restaurant_id=restaurant_id)
    return qs.first()


def user_can_access_restaurant(user, restaurant):
    if not user or not user.is_authenticated:
        return False
    if is_platform_admin(user):
        return True
    restaurant_id = restaurant if isinstance(restaurant, int) else restaurant.pk
    return user.employments.filter(restaurant_id=restaurant_id, is_active=True).exists()


def require_restaurant_access(user, restaurant):
    if not user_can_access_restaurant(user, restaurant):
        raise PermissionDenied("Accès refusé à ce restaurant.")


def require_restaurant_role(user, restaurant, roles):
    if not user_has_restaurant_role(user, restaurant, roles):
        raise PermissionDenied("Rôle insuffisant pour cette action.")


def user_has_restaurant_role(user, restaurant, roles):
    if is_platform_admin(user):
        return True
    restaurant_id = restaurant if isinstance(restaurant, int) else restaurant.pk
    return user.employments.filter(
        restaurant_id=restaurant_id,
        is_active=True,
        role__in=roles,
    ).exists()
