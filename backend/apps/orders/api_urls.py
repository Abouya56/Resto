from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.orders.api_views import CartViewSet, OrderViewSet

router = DefaultRouter()
router.register("cart", CartViewSet, basename="cart")
router.register("", OrderViewSet, basename="order")

urlpatterns = [path("", include(router.urls))]
