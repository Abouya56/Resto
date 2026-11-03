from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import DetailView, FormView, ListView, TemplateView

from apps.core.tenancy import is_platform_admin
from apps.restaurants.forms import ManagerOnboardingForm
from apps.restaurants.models import Restaurant, RestaurantStatus
from apps.restaurants.search import search_restaurants


class RestaurantListView(ListView):
    template_name = "client/restaurant_list.html"
    context_object_name = "restaurants"

    def get_queryset(self):
        # Fermé par son gérant : le restaurant disparaît de la liste jusqu'à sa réouverture.
        return Restaurant.objects.filter(status=RestaurantStatus.ACTIVE, is_accepting_orders=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        results, suggestions = search_restaurants(
            self.object_list, self.request.GET.get("q", ""), self.request.GET.get("city", "")
        )
        context["restaurants"] = results
        context["suggestions"] = suggestions
        context["q"] = self.request.GET.get("q", "").strip()
        return context


class RestaurantDetailView(DetailView):
    template_name = "client/restaurant_detail.html"
    context_object_name = "restaurant"
    slug_field = "slug"

    def get_queryset(self):
        return Restaurant.objects.filter(status=RestaurantStatus.ACTIVE)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object.is_accepting_orders:
            # Fermé aujourd'hui : ni carte ni commande, seulement un mot poli.
            return render(request, "client/restaurant_closed.html", {"restaurant": self.object})
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        from apps.orders.views import ordering_context

        context = super().get_context_data(**kwargs)
        context.update(ordering_context(self.request, self.object))
        return context


@method_decorator(ensure_csrf_cookie, name="dispatch")
class RestaurantOnboardingView(FormView):
    """Demande d'ouverture : sans compte ni mot de passe. La plateforme crée ensuite le compte gérant."""

    form_class = ManagerOnboardingForm
    template_name = "auth/register_restaurant.html"

    def dispatch(self, request, *args, **kwargs):
        if is_platform_admin(request.user):
            return redirect("backoffice:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.save()
        return redirect("restaurants:request_sent")


class RestaurantRequestSentView(TemplateView):
    template_name = "auth/request_sent.html"


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
