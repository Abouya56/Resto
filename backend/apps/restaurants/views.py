from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect
from django.views.generic import DetailView, FormView, ListView

from apps.core.tenancy import is_platform_admin
from apps.menus.models import Category
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
        context = super().get_context_data(**kwargs)
        context["categories"] = (
            Category.objects.filter(restaurant=self.object, is_active=True)
            .prefetch_related("products")
        )
        return context


class RestaurantOnboardingView(FormView):
    form_class = ManagerOnboardingForm
    template_name = "auth/register_restaurant.html"

    def dispatch(self, request, *args, **kwargs):
        if is_platform_admin(request.user):
            return redirect("notifications:admin_dashboard")
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
            f"{restaurant.name} est créé. Ajoutez maintenant vos catégories, plats et tables.",
        )
        return redirect("orders:manager_dashboard")
