from rest_framework import serializers

from apps.finance.models import Expense


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = ("id", "restaurant", "category", "amount", "description", "date", "user", "receipt")
        read_only_fields = ("id", "restaurant", "user")
