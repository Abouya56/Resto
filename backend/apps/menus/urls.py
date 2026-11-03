from django.urls import path

from apps.menus import views

app_name = "menus"

urlpatterns = [
    path("gerant/categories/", views.CategoryListView.as_view(), name="categories"),
    path("gerant/categories/nouvelle/", views.CategoryCreateView.as_view(), name="category_create"),
    path("gerant/categories/<int:pk>/", views.CategoryUpdateView.as_view(), name="category_update"),
    path("gerant/categories/<int:pk>/deplacer/", views.move_category, name="category_move"),
    path("gerant/categories/<int:pk>/visibilite/", views.toggle_category, name="category_toggle"),
    path("gerant/categories/<int:pk>/supprimer/", views.delete_category, name="category_delete"),
    path("gerant/produits/", views.ProductListView.as_view(), name="products"),
    path("gerant/produits/nouveau/", views.ProductCreateView.as_view(), name="product_create"),
    path("gerant/produits/<int:pk>/", views.ProductUpdateView.as_view(), name="product_update"),
    path("gerant/produits/<int:pk>/disponibilite/", views.toggle_product, name="product_toggle"),
]
