from django.db.models import Sum
from django.views.generic import ListView, TemplateView

from apps.core.mixins import PlatformAdminRequiredMixin
from apps.orders.models import Order
from apps.payments.models import Payment, PaymentStatus
from apps.restaurants.models import Restaurant
from apps.users.models import User


class PlatformDashboardView(PlatformAdminRequiredMixin, TemplateView):
    template_name = "admin_panel/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["restaurant_count"] = Restaurant.objects.count()
        context["user_count"] = User.objects.count()
        context["order_count"] = Order.objects.count()
        context["revenue"] = (
            Payment.objects.filter(status=PaymentStatus.PAID).aggregate(total=Sum("amount"))["total"] or 0
        )
        context["recent_orders"] = Order.objects.select_related("restaurant")[:10]
        return context


class PlatformRestaurantListView(PlatformAdminRequiredMixin, ListView):
    template_name = "admin_panel/restaurants.html"
    context_object_name = "restaurants"
    queryset = Restaurant.objects.all()


class PlatformUserListView(PlatformAdminRequiredMixin, ListView):
    template_name = "admin_panel/users.html"
    context_object_name = "users"
    queryset = User.objects.all()
