from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.mixins import ManagerRequiredMixin, RestaurantContextMixin, RestaurantFormKwargsMixin
from apps.core.tenancy import require_restaurant_role, user_can_access_restaurant
from apps.users.roles import Role
from apps.tables.forms import DiningTableForm
from apps.tables.models import DiningTable
from apps.tables.services import ensure_qrcode, regenerate_qrcode


class TableListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    template_name = "manager/tables.html"
    context_object_name = "tables"

    def get_queryset(self):
        return DiningTable.objects.filter(restaurant=self.restaurant).select_related("qrcode")


class TableCreateView(ManagerRequiredMixin, RestaurantContextMixin, RestaurantFormKwargsMixin, CreateView):
    form_class = DiningTableForm
    template_name = "manager/table_form.html"
    success_url = reverse_lazy("tables:list")

    def form_valid(self, form):
        form.instance.restaurant = self.restaurant
        response = super().form_valid(form)
        ensure_qrcode(self.object)
        messages.success(self.request, "Table créée et QR code généré.")
        return response


class TableUpdateView(ManagerRequiredMixin, RestaurantContextMixin, RestaurantFormKwargsMixin, UpdateView):
    form_class = DiningTableForm
    template_name = "manager/table_form.html"
    success_url = reverse_lazy("tables:list")

    def get_queryset(self):
        return DiningTable.objects.filter(restaurant=self.restaurant)


def _owned_table(request, pk):
    table = get_object_or_404(DiningTable.objects.select_related("restaurant"), pk=pk)
    if not user_can_access_restaurant(request.user, table.restaurant):
        raise Http404()
    require_restaurant_role(request.user, table.restaurant, (Role.MANAGER,))
    return table


@login_required
def qrcode_page(request, pk):
    table = _owned_table(request, pk)
    qr = ensure_qrcode(table)
    return render(request, "manager/qrcode.html", {"table": table, "qr": qr, "restaurant": table.restaurant})


@login_required
@require_POST
def regenerate_qr(request, pk):
    table = _owned_table(request, pk)
    regenerate_qrcode(table)
    messages.success(request, "QR code régénéré.")
    return redirect("tables:qrcode", pk=table.pk)


@login_required
def download_qr(request, pk):
    table = _owned_table(request, pk)
    qr = ensure_qrcode(table)
    return FileResponse(qr.image.open("rb"), as_attachment=True, filename=f"qr-table-{table.number}.png")
