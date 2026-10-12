from django.urls import path

from apps.backoffice import views

app_name = "backoffice"

urlpatterns = [
    path("admin-plateforme/", views.PlatformDashboardView.as_view(), name="dashboard"),
    path("admin-plateforme/restaurants/", views.PlatformRestaurantListView.as_view(), name="restaurants"),
    path(
        "admin-plateforme/restaurants/<int:pk>/",
        views.PlatformRestaurantDetailView.as_view(),
        name="restaurant_detail",
    ),
    path(
        "admin-plateforme/restaurants/<int:pk>/document/<slug:kind>/",
        views.PlatformRestaurantDocumentView.as_view(),
        name="restaurant_document",
    ),
    path(
        "admin-plateforme/restaurants/<int:pk>/valider/",
        views.PlatformRestaurantApproveView.as_view(),
        name="restaurant_approve",
    ),
    path(
        "admin-plateforme/restaurants/<int:pk>/refuser/",
        views.PlatformRestaurantRejectView.as_view(),
        name="restaurant_reject",
    ),
    path(
        "admin-plateforme/restaurants/<int:pk>/suspendre/",
        views.PlatformRestaurantSuspendView.as_view(),
        name="restaurant_suspend",
    ),
    path(
        "admin-plateforme/restaurants/<int:pk>/reactiver/",
        views.PlatformRestaurantReactivateView.as_view(),
        name="restaurant_reactivate",
    ),
    path("admin-plateforme/utilisateurs/", views.PlatformUserListView.as_view(), name="users"),
    path("admin-plateforme/commandes/", views.PlatformOrderListView.as_view(), name="orders"),
]
