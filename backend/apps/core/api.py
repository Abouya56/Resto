from rest_framework.exceptions import PermissionDenied

from apps.core.tenancy import get_active_employment, is_platform_admin, user_can_access_restaurant
from apps.restaurants.models import Restaurant, RestaurantStatus


def resolve_restaurant(request):
    """Détermine le restaurant actif après authentification (session, JWT, header)."""
    current = getattr(request, "current_restaurant", None)
    if current is not None:
        return current
    restaurant_id = None
    headers = getattr(request, "headers", {})
    restaurant_id = headers.get("X-Restaurant-Id") if headers else None
    if not restaurant_id:
        query = getattr(request, "query_params", None) or request.GET
        restaurant_id = query.get("restaurant")
    if not restaurant_id and hasattr(request, "data"):
        restaurant_id = request.data.get("restaurant")
    if not restaurant_id and hasattr(request, "session"):
        restaurant_id = request.session.get("current_restaurant_id")
    if restaurant_id:
        try:
            restaurant = Restaurant.objects.get(pk=int(restaurant_id))
        except (Restaurant.DoesNotExist, TypeError, ValueError):
            return None
        if user_can_access_restaurant(request.user, restaurant):
            request.current_restaurant = restaurant
            return restaurant
        return None
    employment = get_active_employment(request.user)
    if employment:
        request.current_restaurant = employment.restaurant
        request.current_employment = employment
        return employment.restaurant
    return None


class CurrentRestaurantAPIMixin:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        request.current_restaurant = resolve_restaurant(request)
        restaurant = request.current_restaurant
        request.current_employment = get_active_employment(
            request.user, restaurant.pk if restaurant else None
        )
        if (
            restaurant
            and restaurant.status != RestaurantStatus.ACTIVE
            and not is_platform_admin(request.user)
        ):
            raise PermissionDenied("Restaurant en attente de validation.")
