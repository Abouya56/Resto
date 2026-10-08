from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, TemplateView

from apps.notifications.models import Notification
from apps.restaurants.models import Restaurant, RestaurantStatus


class HomeView(TemplateView):
    template_name = "client/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["restaurants"] = Restaurant.objects.filter(
            status=RestaurantStatus.ACTIVE
        ).order_by("name")[:8]
        return context


class NotificationListView(LoginRequiredMixin, ListView):
    template_name = "client/notifications.html"
    context_object_name = "notifications"

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        qs.filter(is_read=False).update(is_read=True)
        return qs
