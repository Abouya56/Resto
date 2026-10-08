from django.contrib import admin

from apps.menus.models import Category, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "restaurant", "sort_order", "is_active")
    list_filter = ("is_active", "restaurant")
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "restaurant", "category", "price", "is_available", "is_active")
    list_filter = ("is_available", "is_active", "restaurant")
    search_fields = ("name",)
