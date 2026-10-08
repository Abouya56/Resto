from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.tables.api_views import DiningTableViewSet

router = DefaultRouter()
router.register("", DiningTableViewSet, basename="table")

urlpatterns = [path("", include(router.urls))]
