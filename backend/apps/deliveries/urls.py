from django.urls import path

from apps.deliveries import views

app_name = "deliveries"

urlpatterns = [
    path("gerant/livraisons/", views.ManagerDeliveryListView.as_view(), name="manage"),
    path("gerant/livraisons/<int:pk>/attribuer/", views.assign_delivery, name="assign"),
    path("livreur/", views.DriverDeliveryListView.as_view(), name="list"),
    path("livreur/<int:pk>/", views.DriverDeliveryDetailView.as_view(), name="detail"),
    path("livreur/<int:pk>/statut/", views.driver_status, name="status"),
]
