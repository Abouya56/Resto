from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.payments.api_views import PaymentViewSet

router = DefaultRouter()
router.register("", PaymentViewSet, basename="payment")

urlpatterns = [path("", include(router.urls))]
