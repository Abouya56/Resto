from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.mixins import ManagerRequiredMixin, RestaurantContextMixin
from apps.core.tenancy import is_platform_admin, require_restaurant_role
from apps.restaurants.forms import EmployeeForm, RestaurantForm
from apps.restaurants.models import Employee, EmployeeStatus
from apps.restaurants.team import RECEPTION_LIMIT_MESSAGE, reception_slot_taken
from apps.users.roles import Role


class RestaurantUpdateView(ManagerRequiredMixin, RestaurantContextMixin, UpdateView):
    form_class = RestaurantForm
    template_name = "manager/restaurant_form.html"
    success_url = reverse_lazy("orders:manager_dashboard")
    allow_incomplete_profile = True

    def get_object(self):
        return self.restaurant

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            "Informations enregistrées. Vous pouvez maintenant gérer le menu, les tables et l'équipe.",
        )
        return response


REMOVAL_MESSAGE = "La réception est essentielle à votre restaurant : pour la suspendre, la retirer ou la remplacer, contactez la plateforme."


# L'équipe par poste, avec ce que chaque poste voit dans l'appli.
ROLE_GROUPS = (
    (Role.MANAGER, "Gérants", "Voient tout : commandes, carte, argent, équipe.", "bi-briefcase"),
    (Role.RECEPTION, "Réception", "Reçoit les commandes, les sert ou les livre, et encaisse.", "bi-bell"),
)
MISSING_ROLE_HINTS = {
    Role.RECEPTION: "Personne à la réception : les commandes ne seront vues que par vous.",
}


class EmployeeListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    template_name = "manager/employees.html"
    context_object_name = "employees"

    def get_queryset(self):
        return (
            Employee.objects.filter(restaurant=self.restaurant)
            .select_related("user")
            .order_by("-is_active", "user__first_name", "user__last_name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employees = list(context["employees"])
        for employee in employees:
            employee.is_me = employee.user_id == self.request.user.pk
            employee.is_owner = employee.user_id == self.restaurant.owner_id
            employee.can_remove = not (employee.is_me or employee.is_owner)
        groups = []
        for role, title, help_text, icon in ROLE_GROUPS:
            members = [e for e in employees if e.role == role]
            active = [e for e in members if e.is_active]
            groups.append(
                {
                    "title": title,
                    "help": help_text,
                    "icon": icon,
                    "members": members,
                    "missing": MISSING_ROLE_HINTS.get(role) if not active and role != Role.MANAGER else "",
                }
            )
        context["groups"] = groups
        context["can_add"] = not reception_slot_taken(self.restaurant)
        context["active_count"] = sum(1 for e in employees if e.is_active)
        context["inactive_count"] = sum(1 for e in employees if not e.is_active)
        return context


@login_required
@require_POST
def toggle_employee(request, pk):
    """Suspendre quelqu'un (congé, essai) sans le supprimer : il ne peut plus ouvrir l'espace du restaurant."""
    employee = get_object_or_404(Employee.objects.select_related("user", "restaurant"), pk=pk)
    require_restaurant_role(request.user, employee.restaurant, (Role.MANAGER,))
    if not is_platform_admin(request.user):
        # La réception est essentielle au restaurant : seule la plateforme peut la suspendre ou la retirer.
        messages.info(request, REMOVAL_MESSAGE)
        return redirect("restaurants:employees")
    if employee.user_id == request.user.pk or employee.user_id == employee.restaurant.owner_id:
        messages.error(request, "Vous ne pouvez pas suspendre ce compte.")
    else:
        employee.status = EmployeeStatus.INACTIVE if employee.is_active else EmployeeStatus.ACTIVE
        employee.save()
        if employee.is_active:
            messages.success(request, f"{employee.user} peut de nouveau travailler dans l'appli.")
        else:
            messages.success(request, f"{employee.user} est suspendu : il ne peut plus ouvrir l'espace du restaurant.")
    return redirect(f"{reverse('restaurants:employees')}#employe-{employee.pk}")


class EmployeeCreateView(ManagerRequiredMixin, RestaurantContextMixin, CreateView):
    form_class = EmployeeForm
    template_name = "manager/employee_form.html"
    success_url = reverse_lazy("restaurants:employees")

    def get(self, request, *args, **kwargs):
        if reception_slot_taken(self.restaurant):
            messages.info(request, RECEPTION_LIMIT_MESSAGE)
            return redirect(self.success_url)
        return super().get(request, *args, **kwargs)

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


class EmployeeDeleteView(ManagerRequiredMixin, RestaurantContextMixin, DeleteView):
    """Retire l'employé de l'équipe : le compte utilisateur et son historique sont conservés."""

    template_name = "manager/employee_confirm_delete.html"
    context_object_name = "employee"
    success_url = reverse_lazy("restaurants:employees")

    def get_queryset(self):
        return Employee.objects.filter(restaurant=self.restaurant).select_related("user")

    def dispatch(self, request, *args, **kwargs):
        # Une seule réception par restaurant : un retrait par erreur est trop risqué, la plateforme s'en charge.
        if request.user.is_authenticated and not is_platform_admin(request.user):
            self.denied = True
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if getattr(self, "denied", False):
            messages.info(request, REMOVAL_MESSAGE)
            return redirect(self.success_url)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if getattr(self, "denied", False):
            messages.info(request, REMOVAL_MESSAGE)
            return redirect(self.success_url)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        employee = self.object
        if employee.user_id == self.request.user.pk:
            messages.error(self.request, "Vous ne pouvez pas vous retirer vous-même de l'équipe.")
            return redirect(self.success_url)
        if employee.user_id == self.restaurant.owner_id:
            messages.error(self.request, "Le propriétaire du restaurant ne peut pas être retiré.")
            return redirect(self.success_url)
        user = employee.user
        employee.delete()
        # Sans autre établissement, le compte redevient un simple client.
        if not user.employments.exists() and user.role in Role.STAFF:
            user.role = Role.CUSTOMER
            user.save(update_fields=["role"])
        messages.success(self.request, f"{user} a été retiré de l'équipe.")
        return redirect(self.success_url)


@login_required
@require_POST
def toggle_open(request):
    """Ouvrir ou fermer le restaurant : fermé, il disparaît de la liste et ne prend plus de commandes."""
    restaurant = getattr(request, "current_restaurant", None)
    if restaurant is None:
        return redirect("users:dashboard")
    require_restaurant_role(request.user, restaurant, (Role.MANAGER,))
    restaurant.is_accepting_orders = not restaurant.is_accepting_orders
    restaurant.save(update_fields=["is_accepting_orders", "updated_at"])
    if restaurant.is_accepting_orders:
        messages.success(request, "Votre restaurant est ouvert : les clients le voient et peuvent commander.")
    else:
        messages.success(request, "Votre restaurant est fermé : il n'est plus visible par les clients.")
    return redirect("orders:manager_dashboard")
