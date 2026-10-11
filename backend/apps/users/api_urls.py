from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users.api_views import (
    AdminUserViewSet,
    ChangePasswordAPIView,
    LoginAPIView,
    MeAPIView,
)

router = DefaultRouter()
router.register("users", AdminUserViewSet, basename="admin-users")

urlpatterns = [
    path("login/", LoginAPIView.as_view(), name="api-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("me/", MeAPIView.as_view(), name="api-me"),
    path("me/password/", ChangePasswordAPIView.as_view(), name="api-change-password"),
    path("", include(router.urls)),
]
