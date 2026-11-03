from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.mixins import ManagerRequiredMixin, RestaurantContextMixin, RestaurantFormKwargsMixin
from apps.core.tenancy import require_restaurant_role, user_can_access_restaurant
from apps.tables.forms import DiningTableForm
from apps.tables.models import DiningTable
from apps.tables.occupancy import attach_states, open_dine_in_orders
from apps.tables.services import ensure_qrcode, regenerate_qrcode, site_base_url, site_is_local
from apps.users.roles import Role


class TableListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    """Plan de salle : chaque table avec son état réel (d'après les commandes) et son QR code."""

    template_name = "manager/tables.html"
    context_object_name = "tables"

    def get_queryset(self):
        return DiningTable.objects.filter(restaurant=self.restaurant).select_related("qrcode")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tables = sorted(context["tables"], key=lambda t: natural_key(t.number))
        base = site_base_url(self.request)
        for table in tables:
            if table.is_active:
                table.qrcode = ensure_qrcode(table, base)  # remet à jour les QR dont l'adresse du site a changé
        context["site_is_local"] = site_is_local(base)
        context["site_url"] = base
        attach_states(tables, list(open_dine_in_orders(self.restaurant)))
        active = [t for t in tables if t.is_active]
        busy = [t for t in active if t.state != "free"]
        context.update(
            {
                "tables": tables,
                "summary": {
                    "tables": len(active),
                    "seats": sum(t.capacity for t in active),
                    "busy": len(busy),
                    "free": len(active) - len(busy),
                    "to_accept": sum(1 for t in active if t.state == "pending"),
                },
            }
        )
        return context


class TableQrSheetView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    """Une feuille à imprimer avec le QR code de chaque table active."""

    template_name = "manager/qrcode_sheet.html"
    context_object_name = "tables"

    def get_queryset(self):
        tables = list(DiningTable.objects.filter(restaurant=self.restaurant, is_active=True))
        base = site_base_url(self.request)
        for table in tables:
            table.qr = ensure_qrcode(table, base)
        return sorted(tables, key=lambda t: natural_key(t.number))


def natural_key(number):
    """« 2 » avant « 10 », et les noms (« Terrasse ») après les numéros."""
    text = str(number).strip()
    return (0, int(text), "") if text.isdigit() else (1, 0, text.lower())


class TableCreateView(ManagerRequiredMixin, RestaurantContextMixin, RestaurantFormKwargsMixin, CreateView):
    form_class = DiningTableForm
    template_name = "manager/table_form.html"
    success_url = reverse_lazy("tables:list")

    def form_valid(self, form):
        form.instance.restaurant = self.restaurant
        response = super().form_valid(form)
        ensure_qrcode(self.object, site_base_url(self.request))
        messages.success(self.request, f"Table {self.object.number} créée. Son QR code est prêt à imprimer.")
        return response


class TableUpdateView(ManagerRequiredMixin, RestaurantContextMixin, RestaurantFormKwargsMixin, UpdateView):
    form_class = DiningTableForm
    template_name = "manager/table_form.html"
    success_url = reverse_lazy("tables:list")

    def get_queryset(self):
        return DiningTable.objects.filter(restaurant=self.restaurant)

    def form_valid(self, form):
        messages.success(self.request, f"Table {form.instance.number} enregistrée.")
        return super().form_valid(form)


def _owned_table(request, pk):
    table = get_object_or_404(DiningTable.objects.select_related("restaurant"), pk=pk)
    if not user_can_access_restaurant(request.user, table.restaurant):
        raise Http404()
    require_restaurant_role(request.user, table.restaurant, (Role.MANAGER,))
    return table


@login_required
def qrcode_page(request, pk):
    table = _owned_table(request, pk)
    base = site_base_url(request)
    qr = ensure_qrcode(table, base)
    return render(
        request,
        "manager/qrcode.html",
        {
            "table": table,
            "qr": qr,
            "restaurant": table.restaurant,
            "site_is_local": site_is_local(base),
            "site_url": base,
        },
    )


@login_required
@require_POST
def regenerate_qr(request, pk):
    table = _owned_table(request, pk)
    regenerate_qrcode(table, site_base_url(request))
    messages.success(request, "Nouveau QR code créé. Imprimez-le : l'ancien ne marche plus.")
    return redirect("tables:qrcode", pk=table.pk)


@login_required
def download_qr(request, pk):
    table = _owned_table(request, pk)
    qr = ensure_qrcode(table, site_base_url(request))
    return FileResponse(qr.image.open("rb"), as_attachment=True, filename=f"qr-table-{table.number}.png")
