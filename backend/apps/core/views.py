from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import ListView, TemplateView

from apps.core.models import SiteSettings
from apps.notifications.models import Notification
from apps.restaurants.models import Restaurant, RestaurantStatus
from apps.users.views import dashboard_redirect


class HomeView(TemplateView):
    template_name = "client/home.html"

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        # Le super-admin peut voir l'accueil tel que les visiteurs le voient (?apercu=1).
        previewing = request.GET.get("apercu") == "1" and getattr(user, "is_platform_admin", False)
        if (
            user.is_authenticated
            and not previewing
            and (getattr(request, "current_employment", None) or getattr(user, "is_platform_admin", False))
        ):
            return redirect(reverse(dashboard_redirect(user)))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        restaurants = Restaurant.objects.filter(status=RestaurantStatus.ACTIVE, is_accepting_orders=True)
        context["site"] = SiteSettings.load()
        context["restaurants"] = restaurants.order_by("name")[:8]
        context["restaurant_total"] = restaurants.count()
        context["previewing"] = self.request.GET.get("apercu") == "1" and getattr(
            self.request.user, "is_platform_admin", False
        )
        return context


def csrf_failure(request, reason=""):
    return render(request, "errors/csrf.html", status=403)


class PhotoCreditsView(TemplateView):
    """Les auteurs des photos de plats venues de Wikimedia Commons : les licences demandent de les citer."""

    template_name = "client/credits.html"

    def get_context_data(self, **kwargs):
        import json
        from pathlib import Path

        context = super().get_context_data(**kwargs)
        path = Path(__file__).resolve().parent / "data" / "photo_credits.json"
        context["credits"] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        return context


class NotificationListView(LoginRequiredMixin, ListView):
    template_name = "client/notifications.html"
    context_object_name = "notifications"

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        qs.filter(is_read=False).update(is_read=True)
        return qs
