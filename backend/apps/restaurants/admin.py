from django.contrib import admin

from apps.restaurants.models import Employee, Restaurant


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "status", "subscription_plan", "is_accepting_orders")
    list_filter = ("status", "subscription_plan", "city")
    search_fields = ("name", "email", "phone", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("user", "restaurant", "role", "status")
    list_filter = ("role", "status", "restaurant")
    search_fields = ("user__email", "restaurant__name")
