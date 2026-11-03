from apps.core.tenancy import get_active_employment


class CurrentRestaurantMiddleware:
    """Attache le restaurant actif du personnel à la requête."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.current_restaurant = None
        request.current_employment = None
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            restaurant_id = (
                request.headers.get("X-Restaurant-Id")
                or request.GET.get("restaurant")
                or request.session.get("current_restaurant_id")
            )
            employment = get_active_employment(user, restaurant_id)
            if employment:
                request.current_employment = employment
                request.current_restaurant = employment.restaurant
                request.session["current_restaurant_id"] = employment.restaurant_id
            elif user.is_platform_admin and restaurant_id:
                from apps.restaurants.models import Restaurant

                request.current_restaurant = Restaurant.objects.filter(pk=restaurant_id).first()
        return self.get_response(request)


class LicenseExpiryMiddleware:
    """Ferme les restaurants dont la licence est finie, sans tâche planifiée (vérifié au plus une fois par minute)."""

    INTERVAL = 60

    def __init__(self, get_response):
        self.get_response = get_response
        self._last_check = 0.0

    def __call__(self, request):
        import time

        now = time.monotonic()
        if now - self._last_check >= self.INTERVAL:
            self._last_check = now
            from apps.restaurants.licenses import expire_licenses

            try:
                expire_licenses()
            except Exception:  # noqa: BLE001 - base indisponible ou pas migrée : on ne bloque jamais la requête
                pass
        return self.get_response(request)
