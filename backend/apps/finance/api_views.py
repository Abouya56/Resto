from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api import CurrentRestaurantAPIMixin
from apps.core.permissions import IsRestaurantManager, RestaurantQuerysetMixin
from apps.finance.models import Expense
from apps.finance.serializers import ExpenseSerializer
from apps.finance.services import dashboard_metrics, revenue_series


class ExpenseViewSet(CurrentRestaurantAPIMixin, RestaurantQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer
    permission_classes = [IsRestaurantManager]
    queryset = Expense.objects.all()
    filterset_fields = ("category", "date")
    search_fields = ("description",)

    def perform_create(self, serializer):
        serializer.save(restaurant=self.request.current_restaurant, user=self.request.user)

    @action(detail=False, methods=["get"])
    def dashboard(self, request):
        restaurant = request.current_restaurant
        period = request.query_params.get("period", "today")
        return Response(dashboard_metrics(restaurant, period))

    @action(detail=False, methods=["get"])
    def series(self, request):
        restaurant = request.current_restaurant
        grain = request.query_params.get("grain", "day")
        return Response(revenue_series(restaurant, grain=grain))
