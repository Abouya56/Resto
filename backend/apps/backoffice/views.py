from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.db.models import Count, Max, Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView, UpdateView

from apps.backoffice.forms import SiteSettingsForm, UserEditForm, UserPasswordForm
from apps.core.mixins import PlatformAdminRequiredMixin
from apps.core.models import SiteSettings
from apps.orders.models import Order, OrderStatus
from apps.payments.models import Payment, PaymentStatus
from apps.restaurants.approval import (
    approve_restaurant,
    reactivate_restaurant,
    reject_restaurant,
    suspend_restaurant,
)
from apps.restaurants.licenses import LICENSE_MONTHS, license_info, record_license_payment
from apps.restaurants.models import Restaurant, RestaurantStatus
from apps.users.models import User
from apps.users.roles import Role


class PlatformDashboardView(PlatformAdminRequiredMixin, TemplateView):
    template_name = "backoffice/dashboard.html"

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
        context["activity"] = sorted(restaurant_activity(), key=lambda r: (-r["today"], -r["total"]))[:6]
        context["pending_restaurants"] = Restaurant.objects.filter(status=RestaurantStatus.PENDING).select_related(
            "owner"
        )[:8]
        return context


class PlatformRestaurantListView(PlatformAdminRequiredMixin, ListView):
    template_name = "backoffice/restaurants.html"
    context_object_name = "restaurants"

    def get_queryset(self):
        qs = Restaurant.objects.select_related("owner").order_by("-created_at")
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for restaurant in context["restaurants"]:
            restaurant.license = license_info(restaurant)
        return context


class PlatformRestaurantDetailView(PlatformAdminRequiredMixin, DetailView):
    template_name = "backoffice/restaurant_detail.html"
    context_object_name = "restaurant"
    queryset = Restaurant.objects.select_related("owner", "reviewed_by")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        restaurant = self.object
        context["license"] = license_info(restaurant)
        context["license_months"] = LICENSE_MONTHS
        context["license_payments"] = restaurant.license_payments.select_related("recorded_by")[:10]
        context["can_take_license"] = restaurant.status in (RestaurantStatus.ACTIVE, RestaurantStatus.UNPAID)
        return context


class PlatformRestaurantLicenseView(PlatformAdminRequiredMixin, View):
    """Le restaurant a payé : on enregistre la licence, il s'ouvre (ou reste ouvert plus longtemps)."""

    def post(self, request, pk):
        restaurant = get_object_or_404(Restaurant, pk=pk)
        try:
            months = int(request.POST.get("months", ""))
            amount = Decimal(request.POST.get("amount") or "0")
            if amount < 0:
                raise InvalidOperation
            payment = record_license_payment(
                restaurant, months, request.user, amount=amount, note=(request.POST.get("note") or "").strip()
            )
        except (ValueError, InvalidOperation):
            messages.error(request, "Paiement non enregistré : vérifiez la durée et le montant.")
        else:
            messages.success(
                request, f"Licence enregistrée : {restaurant.name} est ouvert jusqu'au {payment.valid_until:%d/%m/%Y}."
            )
        return redirect("backoffice:restaurant_detail", pk=pk)


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
            return redirect("backoffice:restaurant_detail", pk=pk)
        approve_restaurant(restaurant, request.user, request.POST.get("note", ""))
        email = restaurant.manager_email
        if getattr(restaurant, "manager_password", None):
            messages.success(
                request,
                f"{restaurant.name} est validé. Compte gérant créé · e-mail : {email} · mot de passe provisoire : "
                f"{restaurant.manager_password} · Notez-les et donnez-les au gérant : le mot de passe ne s'affichera plus.",
            )
        else:
            messages.success(request, f"{restaurant.name} est validé. Le compte {email} existait déjà : il devient gérant.")
        return redirect("backoffice:restaurant_detail", pk=restaurant.pk)


class PlatformRestaurantRejectView(PlatformAdminRequiredMixin, View):
    def post(self, request, pk):
        restaurant = get_object_or_404(Restaurant, pk=pk)
        note = (request.POST.get("note") or "").strip()
        if not note:
            messages.error(request, "Indiquez un motif de refus.")
            return redirect("backoffice:restaurant_detail", pk=pk)
        if restaurant.status != RestaurantStatus.PENDING:
            messages.warning(request, "Cette demande n'est plus en attente.")
            return redirect("backoffice:restaurant_detail", pk=pk)
        reject_restaurant(restaurant, request.user, note)
        messages.success(request, f"{restaurant.name} a été refusé.")
        return redirect("backoffice:restaurants")


class PlatformRestaurantSuspendView(PlatformAdminRequiredMixin, View):
    def post(self, request, pk):
        restaurant = get_object_or_404(Restaurant, pk=pk)
        note = (request.POST.get("note") or "").strip()
        if restaurant.status != RestaurantStatus.ACTIVE:
            messages.warning(request, "Seul un restaurant actif peut être suspendu.")
        elif not note:
            messages.error(request, "Indiquez le motif de la suspension.")
        else:
            suspend_restaurant(restaurant, request.user, note)
            messages.success(request, f"{restaurant.name} est suspendu.")
        return redirect("backoffice:restaurant_detail", pk=pk)


class PlatformRestaurantReactivateView(PlatformAdminRequiredMixin, View):
    def post(self, request, pk):
        restaurant = get_object_or_404(Restaurant, pk=pk)
        if restaurant.status != RestaurantStatus.SUSPENDED:
            messages.warning(request, "Ce restaurant n'est pas suspendu.")
        else:
            reactivate_restaurant(restaurant, request.user, request.POST.get("note", "").strip())
            messages.success(request, f"{restaurant.name} est réactivé.")
        return redirect("backoffice:restaurant_detail", pk=pk)


class PlatformUserListView(PlatformAdminRequiredMixin, ListView):
    template_name = "backoffice/users.html"
    context_object_name = "users"

    def get_queryset(self):
        qs = User.objects.all().order_by("role", "last_name", "first_name")
        role = self.request.GET.get("role")
        q = self.request.GET.get("q")
        if role:
            qs = qs.filter(role=role)
        if q:
            qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["roles"] = Role.CHOICES
        return context


class PlatformUserEditView(PlatformAdminRequiredMixin, TemplateView):
    """Corriger les informations d'un compte ou lui donner un nouveau mot de passe."""

    template_name = "backoffice/user_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.target = get_object_or_404(User, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def _context(self, profile_form=None, password_form=None):
        return {
            "target": self.target,
            "profile_form": profile_form or UserEditForm(instance=self.target, editor=self.request.user),
            "password_form": password_form or UserPasswordForm(self.target),
            "employments": self.target.employments.select_related("restaurant"),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self._context())
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "password":
            form = UserPasswordForm(self.target, request.POST)
            if form.is_valid():
                form.save()
                if self.target.pk == request.user.pk:
                    update_session_auth_hash(request, self.target)  # on reste connecté
                messages.success(request, f"Nouveau mot de passe enregistré pour {self.target}.")
                return redirect("backoffice:user_edit", pk=self.target.pk)
            messages.error(request, "Le mot de passe n'a pas été changé : lisez le message en rouge.")
            return self.render_to_response(self.get_context_data(**self._context(password_form=form)))
        form = UserEditForm(request.POST, instance=self.target, editor=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Informations enregistrées.")
            return redirect("backoffice:user_edit", pk=self.target.pk)
        messages.error(request, "Rien n'a été enregistré : corrigez les champs en rouge.")
        return self.render_to_response(self.get_context_data(**self._context(profile_form=form)))


def restaurant_activity():
    """Un chiffre par restaurant : le super admin suit l'activité sans lire les commandes (noms, téléphones)."""
    today = timezone.localdate()
    open_statuses = [
        OrderStatus.PENDING,
        OrderStatus.ACCEPTED,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.SERVED,
        OrderStatus.OUT_FOR_DELIVERY,
    ]
    orders = {
        row["restaurant_id"]: row
        for row in Order.objects.exclude(status=OrderStatus.CANCELLED)
        .order_by()
        .values("restaurant_id")
        .annotate(
            total=Count("id"),
            today=Count("id", filter=Q(created_at__date=today)),
            open=Count("id", filter=Q(status__in=open_statuses)),
            last=Max("created_at"),
        )
    }
    money = {
        row["order__restaurant_id"]: row["total"]
        for row in Payment.objects.filter(status=PaymentStatus.PAID)
        .order_by()
        .values("order__restaurant_id")
        .annotate(total=Sum("amount"))
    }
    rows = []
    for restaurant in Restaurant.objects.filter(
        status__in=[RestaurantStatus.ACTIVE, RestaurantStatus.SUSPENDED]
    ).order_by("name"):
        stats = orders.get(restaurant.pk, {})
        rows.append(
            {
                "restaurant": restaurant,
                "total": stats.get("total", 0),
                "today": stats.get("today", 0),
                "open": stats.get("open", 0),
                "last": stats.get("last"),
                "money": money.get(restaurant.pk) or 0,
            }
        )
    return rows


class PlatformOrderListView(PlatformAdminRequiredMixin, TemplateView):
    """Activité de chaque restaurant : nombre de commandes et argent encaissé, sans le détail des clients."""

    template_name = "backoffice/orders.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = restaurant_activity()
        context["rows"] = rows
        context["totals"] = {
            "total": sum(r["total"] for r in rows),
            "today": sum(r["today"] for r in rows),
            "open": sum(r["open"] for r in rows),
            "money": sum(r["money"] for r in rows),
        }
        return context


class PlatformSiteSettingsView(PlatformAdminRequiredMixin, UpdateView):
    """Le super-admin règle la photo de couverture et les textes de la page d'accueil."""

    form_class = SiteSettingsForm
    template_name = "backoffice/site_settings.html"

    def get_object(self, queryset=None):
        return SiteSettings.load()

    def get_success_url(self):
        return reverse("backoffice:site_settings")

    def form_valid(self, form):
        messages.success(self.request, "Page d'accueil enregistrée. Les visiteurs voient déjà le changement.")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Rien n'a été enregistré : corrigez les champs en rouge.")
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context["form"]
        context["groups"] = [
            {
                "title": "Logo du site",
                "help": "Le logo en haut de toutes les pages et dans l'onglet du navigateur. Un carré, fond transparent (PNG), est idéal.",
                "fields": [form["logo"], form["site_name"]],
            },
            {
                "title": "Photo de couverture",
                "help": "La grande photo tout en haut de l'accueil. Une photo large et lumineuse marche le mieux.",
                "fields": [form["hero_image"]],
            },
            {
                "title": "Texte principal",
                "help": "Ce que le visiteur lit en premier. Un retour à la ligne dans le grand titre le coupe en deux.",
                "fields": [form["hero_kicker"], form["hero_title"], form["hero_lead"], form["hero_button_label"]],
            },
            {
                "title": "Bandeau d'annonce",
                "help": "Une phrase en haut de l'accueil (fermeture, promotion…). Laissez vide pour la cacher.",
                "fields": [form["banner_text"]],
            },
            {
                "title": "Liste des restaurants",
                "help": "Le titre au-dessus des restaurants.",
                "fields": [form["restaurants_kicker"], form["restaurants_title"]],
            },
            {
                "title": "Bloc « Vous tenez un resto ? »",
                "help": "Le bloc en bas de page qui invite les restaurateurs à s'inscrire.",
                "fields": [
                    form["closing_image"],
                    form["closing_title"],
                    form["closing_text"],
                    form["closing_button_label"],
                ],
            },
        ]
        return context
