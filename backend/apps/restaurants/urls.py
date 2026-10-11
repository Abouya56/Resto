from django.urls import path

from apps.restaurants import views
from apps.restaurants import staff_views

app_name = "restaurants"

urlpatterns = [
    path("ouvrir-un-restaurant/", views.RestaurantOnboardingView.as_view(), name="onboard"),
    path("demande-en-attente/", views.RestaurantPendingView.as_view(), name="pending"),
    path("restaurants/", views.RestaurantListView.as_view(), name="list"),
    path("restaurants/<slug:slug>/", views.RestaurantDetailView.as_view(), name="detail"),
    path("gerant/etablissement/", staff_views.RestaurantUpdateView.as_view(), name="manage"),
    path("gerant/employes/", staff_views.EmployeeListView.as_view(), name="employees"),
    path("gerant/employes/nouveau/", staff_views.EmployeeCreateView.as_view(), name="employee_create"),
    path("gerant/employes/<int:pk>/", staff_views.EmployeeUpdateView.as_view(), name="employee_update"),
]
