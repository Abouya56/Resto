from django.urls import path

from apps.restaurants import staff_views, views

app_name = "restaurants"

urlpatterns = [
    path("ouvrir-un-restaurant/", views.RestaurantOnboardingView.as_view(), name="onboard"),
    path("demande-envoyee/", views.RestaurantRequestSentView.as_view(), name="request_sent"),
    path("demande-en-attente/", views.RestaurantPendingView.as_view(), name="pending"),
    path("restaurants/", views.RestaurantListView.as_view(), name="list"),
    path("restaurants/<slug:slug>/", views.RestaurantDetailView.as_view(), name="detail"),
    path("gerant/etablissement/", staff_views.RestaurantUpdateView.as_view(), name="manage"),
    path("gerant/ouverture/", staff_views.toggle_open, name="toggle_open"),
    path("gerant/employes/", staff_views.EmployeeListView.as_view(), name="employees"),
    path("gerant/employes/nouveau/", staff_views.EmployeeCreateView.as_view(), name="employee_create"),
    path("gerant/employes/<int:pk>/", staff_views.EmployeeUpdateView.as_view(), name="employee_update"),
    path("gerant/employes/<int:pk>/statut/", staff_views.toggle_employee, name="employee_toggle"),
    path(
        "gerant/employes/<int:pk>/supprimer/",
        staff_views.EmployeeDeleteView.as_view(),
        name="employee_delete",
    ),
]
