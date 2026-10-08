from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("admin-plateforme/", views.PlatformDashboardView.as_view(), name="admin_dashboard"),
    path("admin-plateforme/restaurants/", views.PlatformRestaurantListView.as_view(), name="admin_restaurants"),
    path("admin-plateforme/utilisateurs/", views.PlatformUserListView.as_view(), name="admin_users"),
]
