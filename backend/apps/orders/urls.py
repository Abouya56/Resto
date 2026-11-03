from django.urls import path

from apps.orders import views

app_name = "orders"

urlpatterns = [
    path("restaurant/<slug:restaurant_slug>/menu/", views.MenuView.as_view(), name="menu"),
    path(
        "restaurant/<slug:restaurant_slug>/table/<int:table_id>/",
        views.TableMenuView.as_view(),
        name="table_menu",
    ),
    path("panier/", views.CartView.as_view(), name="cart"),
    path("panier/ajouter/", views.add_item, name="add_item"),
    path("panier/ligne/<int:pk>/", views.update_item, name="update_item"),
    path("panier/ligne/<int:pk>/supprimer/", views.remove_item, name="remove_item"),
    path("commander/", views.CheckoutView.as_view(), name="checkout"),
    path("suivi/", views.TrackOrderView.as_view(), name="track"),
    path("commandes/<int:pk>/", views.OrderDetailView.as_view(), name="detail"),
    path("commandes/<int:pk>/recu/", views.OrderReceiptView.as_view(), name="receipt"),
    path("gerant/", views.ManagerDashboardView.as_view(), name="manager_dashboard"),
    path("gerant/commandes/", views.ManagerOrderListView.as_view(), name="manager_orders"),
    path("gerant/commandes/<int:pk>/", views.ManagerOrderDetailView.as_view(), name="manager_order"),
    path("gerant/commandes/<int:pk>/statut/", views.change_status, name="change_status"),
    path("gerant/commandes/<int:pk>/paiement/", views.mark_paid, name="mark_paid"),
    path("reception/", views.ReceptionDashboardView.as_view(), name="reception"),
    path("reception/vente/", views.ReceptionSaleView.as_view(), name="reception_sale"),
    path("reception/<slug:key>/", views.ReceptionTypeView.as_view(), name="reception_type"),
]
