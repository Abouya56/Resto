from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.finance.api_views import ExpenseViewSet

router = DefaultRouter()
router.register("", ExpenseViewSet, basename="expense")

urlpatterns = [path("", include(router.urls))]
