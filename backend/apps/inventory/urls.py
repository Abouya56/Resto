from django.urls import path

from apps.inventory import views
from apps.inventory.feature import stock_only

app_name = "inventory"

urlpatterns = [
    path("gerant/stocks/", stock_only(views.StockListView.as_view()), name="list"),
    path("gerant/stocks/nouveau/", stock_only(views.StockCreateView.as_view()), name="create"),
    path("gerant/stocks/<int:pk>/", stock_only(views.StockUpdateView.as_view()), name="update"),
    path("gerant/stocks/<int:pk>/mouvement/", stock_only(views.stock_move), name="move"),
    path("gerant/stocks/historique/", stock_only(views.MovementListView.as_view()), name="movements"),
    path("gerant/plats/<int:pk>/recette/", stock_only(views.ProductRecipeView.as_view()), name="recipe"),
    path("gerant/recette/<int:pk>/retirer/", stock_only(views.recipe_remove), name="recipe_remove"),
]
