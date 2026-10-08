from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users.api_views import (
    AddressViewSet,
    AdminUserViewSet,
    ChangePasswordAPIView,
    LoginAPIView,
    MeAPIView,
    RegisterAPIView,
)

router = DefaultRouter()
router.register("addresses", AddressViewSet, basename="address")
router.register("users", AdminUserViewSet, basename="admin-users")

urlpatterns = [
    path("register/", RegisterAPIView.as_view(), name="api-register"),
    path("login/", LoginAPIView.as_view(), name="api-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("me/", MeAPIView.as_view(), name="api-me"),
    path("me/password/", ChangePasswordAPIView.as_view(), name="api-change-password"),
    path("", include(router.urls)),
]
