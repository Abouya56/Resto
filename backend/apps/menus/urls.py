from django.urls import path

from apps.menus import views

app_name = "menus"

urlpatterns = [
    path("gerant/categories/", views.CategoryListView.as_view(), name="categories"),
    path("gerant/categories/nouvelle/", views.CategoryCreateView.as_view(), name="category_create"),
    path("gerant/categories/<int:pk>/", views.CategoryUpdateView.as_view(), name="category_update"),
    path("gerant/produits/", views.ProductListView.as_view(), name="products"),
    path("gerant/produits/nouveau/", views.ProductCreateView.as_view(), name="product_create"),
    path("gerant/produits/<int:pk>/", views.ProductUpdateView.as_view(), name="product_update"),
    path("gerant/produits/<int:pk>/disponibilite/", views.toggle_product, name="product_toggle"),
]
