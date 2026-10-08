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
    success_url = reverse_lazy("restaurants:manage")

    def get_object(self):
        return self.restaurant

    def form_valid(self, form):
        messages.success(self.request, "Informations du restaurant mises à jour.")
        return super().form_valid(form)


class EmployeeListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    template_name = "manager/employees.html"
    context_object_name = "employees"

    def get_queryset(self):
        return Employee.objects.filter(restaurant=self.restaurant).select_related("user")


class EmployeeCreateView(ManagerRequiredMixin, RestaurantContextMixin, CreateView):
    form_class = EmployeeForm
    template_name = "manager/employee_form.html"
    success_url = reverse_lazy("restaurants:employees")

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

    def form_valid(self, form):
        form.save(restaurant=self.restaurant)
        messages.success(self.request, "Employé mis à jour.")
        return redirect(self.success_url)
