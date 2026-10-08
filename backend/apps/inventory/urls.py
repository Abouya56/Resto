from django.urls import path

from apps.inventory import views

app_name = "inventory"

urlpatterns = [
    path("gerant/stocks/", views.StockListView.as_view(), name="list"),
    path("gerant/stocks/nouveau/", views.StockCreateView.as_view(), name="create"),
    path("gerant/stocks/<int:pk>/", views.StockUpdateView.as_view(), name="update"),
    path("gerant/stocks/<int:pk>/mouvement/", views.stock_move, name="move"),
    path("gerant/stocks/historique/", views.MovementListView.as_view(), name="movements"),
]
