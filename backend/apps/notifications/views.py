from django.contrib import messages
from django.http import FileResponse, Http404
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.core.mixins import PlatformAdminRequiredMixin
from apps.orders.models import Order
from apps.payments.models import Payment, PaymentStatus
from apps.restaurants.approval import approve_restaurant, reject_restaurant
from apps.restaurants.models import Restaurant, RestaurantStatus
from apps.users.models import User
from apps.users.roles import Role


class PlatformDashboardView(PlatformAdminRequiredMixin, TemplateView):
    template_name = "admin_panel/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pending_count"] = Restaurant.objects.filter(status=RestaurantStatus.PENDING).count()
        context["active_count"] = Restaurant.objects.filter(status=RestaurantStatus.ACTIVE).count()
        context["restaurant_count"] = Restaurant.objects.count()
        context["user_count"] = User.objects.count()
        context["order_count"] = Order.objects.count()
        context["revenue"] = (
            Payment.objects.filter(status=PaymentStatus.PAID).aggregate(total=Sum("amount"))["total"] or 0
        )
        context["recent_orders"] = Order.objects.select_related("restaurant")[:8]
        context["pending_restaurants"] = Restaurant.objects.filter(
            status=RestaurantStatus.PENDING
        ).select_related("owner")[:8]
        return context


class PlatformRestaurantListView(PlatformAdminRequiredMixin, ListView):
    template_name = "admin_panel/restaurants.html"
    context_object_name = "restaurants"

    def get_queryset(self):
        qs = Restaurant.objects.select_related("owner").order_by("-created_at")
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs


class PlatformRestaurantDetailView(PlatformAdminRequiredMixin, DetailView):
    template_name = "admin_panel/restaurant_detail.html"
    context_object_name = "restaurant"
    queryset = Restaurant.objects.select_related("owner", "reviewed_by")


class PlatformRestaurantDocumentView(PlatformAdminRequiredMixin, View):
    """Pièces KYC : lisibles uniquement par un administrateur de la plateforme."""

    fields = {"identite": "identity_document", "activite": "business_document"}

    def get(self, request, pk, kind):
        field = self.fields.get(kind)
        if field is None:
            raise Http404()
        document = getattr(get_object_or_404(Restaurant, pk=pk), field)
        if not document:
            raise Http404()
        response = FileResponse(document.open("rb"), as_attachment=False)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class PlatformRestaurantApproveView(PlatformAdminRequiredMixin, View):
    def post(self, request, pk):
        restaurant = get_object_or_404(Restaurant, pk=pk)
        if restaurant.status != RestaurantStatus.PENDING:
            messages.warning(request, "Cette demande n'est plus en attente.")
            return redirect("notifications:admin_restaurant_detail", pk=pk)
        approve_restaurant(restaurant, request.user, request.POST.get("note", ""))
        messages.success(request, f"{restaurant.name} est validé. Le gérant peut se connecter.")
        return redirect("notifications:admin_restaurants")


class PlatformRestaurantRejectView(PlatformAdminRequiredMixin, View):
    def post(self, request, pk):
        restaurant = get_object_or_404(Restaurant, pk=pk)
        note = (request.POST.get("note") or "").strip()
        if not note:
            messages.error(request, "Indiquez un motif de refus.")
            return redirect("notifications:admin_restaurant_detail", pk=pk)
        if restaurant.status != RestaurantStatus.PENDING:
            messages.warning(request, "Cette demande n'est plus en attente.")
            return redirect("notifications:admin_restaurant_detail", pk=pk)
        reject_restaurant(restaurant, request.user, note)
        messages.success(request, f"{restaurant.name} a été refusé.")
        return redirect("notifications:admin_restaurants")


class PlatformUserListView(PlatformAdminRequiredMixin, ListView):
    template_name = "admin_panel/users.html"
    context_object_name = "users"

    def get_queryset(self):
        qs = User.objects.all().order_by("role", "last_name", "first_name")
        role = self.request.GET.get("role")
        q = self.request.GET.get("q")
        if role:
            qs = qs.filter(role=role)
        if q:
            qs = qs.filter(
                Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["roles"] = Role.CHOICES
        return context


class PlatformOrderListView(PlatformAdminRequiredMixin, ListView):
    template_name = "admin_panel/orders.html"
    context_object_name = "orders"
    paginate_by = 40
    queryset = Order.objects.select_related("restaurant", "customer")
