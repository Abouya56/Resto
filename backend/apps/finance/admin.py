from django.contrib import admin

from apps.finance.models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("restaurant", "category", "amount", "date", "user")
    list_filter = ("category", "restaurant")
