from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView

from apps.core.tenancy import is_platform_admin
from apps.restaurants.models import RestaurantStatus
from apps.users.forms import (
    LoginForm,
    ProfileForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
)
from apps.users.roles import Role


def dashboard_redirect(user):
    if is_platform_admin(user):
        return "backoffice:dashboard"
    employment = user.employments.filter(is_active=True).select_related("restaurant").first()
    if employment:
        restaurant = employment.restaurant
        if restaurant.status != RestaurantStatus.ACTIVE:
            return "restaurants:pending"
        if employment.role == Role.MANAGER and not restaurant.is_profile_complete:
            return "restaurants:manage"
        role_map = {
            Role.MANAGER: "orders:manager_dashboard",
            Role.COOK: "orders:kitchen",
            Role.WAITER: "orders:waiter",
            Role.DRIVER: "deliveries:list",
        }
        return role_map.get(employment.role, "core:home")
    return "restaurants:list"


class UserLoginView(LoginView):
    template_name = "auth/login.html"
    authentication_form = LoginForm

    def get_success_url(self):
        return reverse_lazy(dashboard_redirect(self.request.user))


class UserLogoutView(LogoutView):
    next_page = reverse_lazy("core:home")


class RegisterView(View):
    """Ancienne adresse d'inscription : il n'y a pas de compte client, on commande sans compte."""

    def get(self, request, *args, **kwargs):
        messages.info(
            request,
            "Pas d'inscription publique. Commandez sans compte. Les employés sont ajoutés par le gérant.",
        )
        return redirect("users:login")

    post = get


class ProfileView(LoginRequiredMixin, FormView):
    template_name = "auth/profile.html"
    form_class = ProfileForm
    success_url = reverse_lazy("users:profile")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Profil mis à jour.")
        return super().form_valid(form)


class PasswordResetStartView(PasswordResetView):
    template_name = "auth/password_reset.html"
    email_template_name = "auth/password_reset_email.html"
    form_class = StyledPasswordResetForm
    success_url = reverse_lazy("users:password_reset_done")


class PasswordResetDonePage(PasswordResetDoneView):
    template_name = "auth/password_reset_done.html"


class PasswordResetConfirmPage(PasswordResetConfirmView):
    template_name = "auth/password_reset_confirm.html"
    form_class = StyledSetPasswordForm
    success_url = reverse_lazy("users:password_reset_complete")


class PasswordResetCompletePage(PasswordResetCompleteView):
    template_name = "auth/password_reset_complete.html"
