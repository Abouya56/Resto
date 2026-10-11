from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import DetailView, FormView, ListView, TemplateView

from apps.core.tenancy import is_platform_admin
from apps.restaurants.forms import ManagerOnboardingForm
from apps.restaurants.models import Restaurant, RestaurantStatus


class RestaurantListView(ListView):
    template_name = "client/restaurant_list.html"
    context_object_name = "restaurants"

    def get_queryset(self):
        qs = Restaurant.objects.filter(status=RestaurantStatus.ACTIVE)
        q = self.request.GET.get("q")
        city = self.request.GET.get("city")
        if q:
            qs = qs.filter(name__icontains=q)
        if city:
            qs = qs.filter(city__icontains=city)
        return qs


class RestaurantDetailView(DetailView):
    template_name = "client/restaurant_detail.html"
    context_object_name = "restaurant"
    slug_field = "slug"

    def get_queryset(self):
        return Restaurant.objects.filter(status=RestaurantStatus.ACTIVE)

    def get_context_data(self, **kwargs):
        from apps.orders.views import ordering_context

        context = super().get_context_data(**kwargs)
        context.update(ordering_context(self.request, self.object))
        return context


@method_decorator(ensure_csrf_cookie, name="dispatch")
class RestaurantOnboardingView(FormView):
    form_class = ManagerOnboardingForm
    template_name = "auth/register_restaurant.html"

    def dispatch(self, request, *args, **kwargs):
        if is_platform_admin(request.user):
            return redirect("backoffice:dashboard")
        user = request.user
        if user.is_authenticated:
            pending = (
                Restaurant.objects.filter(owner=user, status=RestaurantStatus.PENDING).order_by("-created_at").first()
            )
            if pending:
                return redirect("restaurants:pending")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        user, restaurant = form.save()
        if not self.request.user.is_authenticated:
            login(self.request, user)
        self.request.session["current_restaurant_id"] = restaurant.pk
        messages.success(
            self.request,
            "Demande envoyée. L'espace restaurant s'ouvrira après validation.",
        )
        return redirect("restaurants:pending")


class RestaurantPendingView(LoginRequiredMixin, TemplateView):
    template_name = "auth/restaurant_pending.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        restaurant = Restaurant.objects.filter(owner=request.user).order_by("-created_at").first()
        if restaurant is None:
            employment = getattr(request, "current_employment", None)
            restaurant = getattr(employment, "restaurant", None)
        if restaurant is None:
            return redirect("restaurants:onboard")
        if restaurant.is_approved:
            if restaurant.is_profile_complete:
                return redirect("orders:manager_dashboard")
            return redirect("restaurants:manage")
        self.restaurant = restaurant
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["restaurant"] = self.restaurant
        return context
