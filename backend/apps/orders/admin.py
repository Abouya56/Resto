from django.contrib import admin

from apps.orders.models import Cart, CartItem, Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product_name", "quantity", "unit_price", "subtotal")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "restaurant",
        "contact_name",
        "customer_phone",
        "order_type",
        "status",
        "total",
        "created_at",
    )
    list_filter = ("status", "order_type", "restaurant")
    search_fields = ("number", "customer_phone", "customer_last_name", "customer__email")
    inlines = [OrderItemInline]


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "restaurant", "user", "order_type", "updated_at")


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("cart", "product", "quantity")
