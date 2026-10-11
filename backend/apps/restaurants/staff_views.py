from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.mixins import ManagerRequiredMixin, RestaurantContextMixin
from apps.restaurants.forms import EmployeeForm, RestaurantForm
from apps.restaurants.models import Employee


class RestaurantUpdateView(ManagerRequiredMixin, RestaurantContextMixin, UpdateView):
    form_class = RestaurantForm
    template_name = "manager/restaurant_form.html"
    success_url = reverse_lazy("orders:manager_dashboard")
    allow_incomplete_profile = True

    def get_object(self):
        return self.restaurant

    def form_valid(self, form):
        was_incomplete = not self.restaurant.is_profile_complete
        response = super().form_valid(form)
        self.restaurant.refresh_from_db()
        if was_incomplete and self.restaurant.is_profile_complete:
            self.restaurant.is_accepting_orders = True
            self.restaurant.save(update_fields=["is_accepting_orders", "updated_at"])
        messages.success(
            self.request,
            "Informations enregistrées. Vous pouvez maintenant gérer le menu, les tables et l'équipe.",
        )
        return response


class EmployeeListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    template_name = "manager/employees.html"
    context_object_name = "employees"

    def get_queryset(self):
        return Employee.objects.filter(restaurant=self.restaurant).select_related("user")


class EmployeeCreateView(ManagerRequiredMixin, RestaurantContextMixin, CreateView):
    form_class = EmployeeForm
    template_name = "manager/employee_form.html"
    success_url = reverse_lazy("restaurants:employees")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["restaurant"] = self.restaurant
        return kwargs

    def form_valid(self, form):
        form.save(restaurant=self.restaurant)
        messages.success(self.request, "Employé enregistré.")
        return redirect(self.success_url)


class EmployeeUpdateView(ManagerRequiredMixin, RestaurantContextMixin, UpdateView):
    form_class = EmployeeForm
    template_name = "manager/employee_form.html"
    success_url = reverse_lazy("restaurants:employees")

    def get_queryset(self):
        return Employee.objects.filter(restaurant=self.restaurant)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["restaurant"] = self.restaurant
        return kwargs

    def form_valid(self, form):
        form.save(restaurant=self.restaurant)
        messages.success(self.request, "Employé mis à jour.")
        return redirect(self.success_url)
