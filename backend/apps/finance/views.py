from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView

from apps.core.mixins import ManagerRequiredMixin, RestaurantContextMixin
from apps.finance.forms import ExpenseForm
from apps.finance.models import Expense
from apps.finance.services import dashboard_metrics, revenue_series


class FinanceDashboardView(ManagerRequiredMixin, RestaurantContextMixin, TemplateView):
    template_name = "manager/finance.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        period = self.request.GET.get("period", "month")
        context["metrics"] = dashboard_metrics(self.restaurant, period)
        context["series"] = revenue_series(self.restaurant, grain="day")
        return context


class ExpenseListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    template_name = "manager/expenses.html"
    context_object_name = "expenses"

    def get_queryset(self):
        return Expense.objects.filter(restaurant=self.restaurant)


class ExpenseCreateView(ManagerRequiredMixin, RestaurantContextMixin, CreateView):
    form_class = ExpenseForm
    template_name = "manager/expense_form.html"
    success_url = reverse_lazy("finance:expenses")

    def form_valid(self, form):
        form.instance.restaurant = self.restaurant
        form.instance.user = self.request.user
        messages.success(self.request, "Dépense enregistrée.")
        return super().form_valid(form)
