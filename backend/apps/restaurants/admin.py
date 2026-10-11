from django.contrib import admin

from apps.restaurants.approval import approve_restaurant
from apps.restaurants.models import Employee, Restaurant, RestaurantStatus


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "status", "owner", "subscription_plan", "is_accepting_orders")
    list_filter = ("status", "subscription_plan", "city")
    search_fields = ("name", "email", "phone", "slug", "owner__email")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("reviewed_at", "reviewed_by")
    actions = ("validate_restaurants",)

    @admin.action(description="Valider les restaurants sélectionnés")
    def validate_restaurants(self, request, queryset):
        count = 0
        for restaurant in queryset.filter(status=RestaurantStatus.PENDING):
            approve_restaurant(restaurant, request.user)
            count += 1
        self.message_user(request, f"{count} restaurant(s) validé(s).")


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("user", "restaurant", "role", "status")
    list_filter = ("role", "status", "restaurant")
    search_fields = ("user__email", "restaurant__name")
