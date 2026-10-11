from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import ListView, TemplateView

from apps.notifications.models import Notification
from apps.restaurants.models import Restaurant, RestaurantStatus
from apps.users.views import dashboard_redirect


class HomeView(TemplateView):
    template_name = "client/home.html"

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if user.is_authenticated and (
            getattr(request, "current_employment", None) or getattr(user, "is_platform_admin", False)
        ):
            return redirect(reverse(dashboard_redirect(user)))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["restaurants"] = Restaurant.objects.filter(
            status=RestaurantStatus.ACTIVE,
        ).order_by("name")[:8]
        return context


def csrf_failure(request, reason=""):
    return render(request, "errors/csrf.html", status=403)


class NotificationListView(LoginRequiredMixin, ListView):
    template_name = "client/notifications.html"
    context_object_name = "notifications"

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        qs.filter(is_read=False).update(is_read=True)
        return qs
