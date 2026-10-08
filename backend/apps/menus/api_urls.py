from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.menus.api_views import CategoryViewSet, ProductViewSet, PublicMenuViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")
router.register("public", PublicMenuViewSet, basename="public-menu")

urlpatterns = [
    path("", include(router.urls)),
]
