from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.inventory.api_views import StockItemViewSet, StockMovementViewSet

router = DefaultRouter()
router.register("items", StockItemViewSet, basename="stock-item")
router.register("movements", StockMovementViewSet, basename="stock-movement")

urlpatterns = [path("", include(router.urls))]
