from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/auth/", include("apps.users.api_urls")),
    path("api/restaurants/", include("apps.restaurants.api_urls")),
    path("api/menus/", include("apps.menus.api_urls")),
    path("api/tables/", include("apps.tables.api_urls")),
    path("api/orders/", include("apps.orders.api_urls")),
    path("api/payments/", include("apps.payments.api_urls")),
    path("api/deliveries/", include("apps.deliveries.api_urls")),
    path("api/inventory/", include("apps.inventory.api_urls")),
    path("api/expenses/", include("apps.finance.api_urls")),
    path("api/notifications/", include("apps.notifications.api_urls")),
    path("", include("apps.core.urls")),
    path("", include("apps.users.urls")),
    path("", include("apps.restaurants.urls")),
    path("", include("apps.menus.urls")),
    path("", include("apps.tables.urls")),
    path("", include("apps.orders.urls")),
    path("", include("apps.inventory.urls")),
    path("", include("apps.finance.urls")),
    path("", include("apps.backoffice.urls")),
]

if getattr(settings, "SERVE_MEDIA", False):
    # Démonstration sur Render uniquement (en vrai serveur, Caddy sert les photos).
    from django.views.static import serve

    urlpatterns += [
        path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
    ]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

admin.site.site_header = "Resto — Administration"
admin.site.site_title = "Resto"
admin.site.index_title = "Supervision de la plateforme"
