from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("admin-plateforme/", views.PlatformDashboardView.as_view(), name="admin_dashboard"),
    path("admin-plateforme/restaurants/", views.PlatformRestaurantListView.as_view(), name="admin_restaurants"),
    path(
        "admin-plateforme/restaurants/<int:pk>/",
        views.PlatformRestaurantDetailView.as_view(),
        name="admin_restaurant_detail",
    ),
    path(
        "admin-plateforme/restaurants/<int:pk>/valider/",
        views.PlatformRestaurantApproveView.as_view(),
        name="admin_restaurant_approve",
    ),
    path(
        "admin-plateforme/restaurants/<int:pk>/refuser/",
        views.PlatformRestaurantRejectView.as_view(),
        name="admin_restaurant_reject",
    ),
    path("admin-plateforme/utilisateurs/", views.PlatformUserListView.as_view(), name="admin_users"),
    path("admin-plateforme/commandes/", views.PlatformOrderListView.as_view(), name="admin_orders"),
]
