from django.contrib import admin

from apps.inventory.models import RecipeIngredient, StockItem, StockMovement


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ("name", "restaurant", "quantity", "unit", "min_threshold", "is_active")
    list_filter = ("restaurant",)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("item", "movement_type", "quantity", "user", "created_at")


@admin.register(RecipeIngredient)
class RecipeIngredientAdmin(admin.ModelAdmin):
    list_display = ("product", "stock_item", "quantity")
