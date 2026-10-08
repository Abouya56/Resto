from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.restaurants.api_views import EmployeeViewSet, PublicRestaurantViewSet, RestaurantViewSet

router = DefaultRouter()
router.register("public", PublicRestaurantViewSet, basename="public-restaurant")
router.register("employees", EmployeeViewSet, basename="employee")
router.register("", RestaurantViewSet, basename="restaurant")

urlpatterns = [
    path("", include(router.urls)),
]
