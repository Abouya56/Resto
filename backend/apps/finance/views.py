from datetime import date, timedelta

from django.contrib import messages
from django.db.models import Count, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.views.generic import CreateView, ListView, TemplateView

from apps.core.daterange import PRESETS, get_date_range
from apps.core.mixins import ManagerRequiredMixin, RestaurantContextMixin
from apps.finance.forms import ExpenseForm
from apps.finance.models import Expense, ExpenseCategory
from apps.finance.services import (
    daily_summary,
    dashboard_metrics,
    day_journal,
    sales_between,
    sales_by_day,
)


class FinanceDashboardView(ManagerRequiredMixin, RestaurantContextMixin, TemplateView):
    """Le journal d'une journée (aujourd'hui par défaut) et le résumé des 14 derniers jours."""

    template_name = "manager/finance.html"

    def get_day(self):
        today = timezone.localdate()
        try:
            day = date.fromisoformat(self.request.GET.get("jour", ""))
        except ValueError:
            return today
        return min(day, today)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        day = self.get_day()
        today = timezone.localdate()
        context["journal"] = day_journal(self.restaurant, day)
        context["is_today"] = day == today
        context["today"] = today
        context["previous_day"] = day - timedelta(days=1)
        context["next_day"] = day + timedelta(days=1) if day < today else None
        summary = daily_summary(self.restaurant)
        context["summary"] = summary
        context["active_days"] = [row for row in summary if row["cashed"] or row["spent"]]
        context["quiet_days"] = len(summary) - len(context["active_days"])
        context["period_totals"] = {
            "cashed": sum(row["cashed"] for row in summary),
            "spent": sum(row["spent"] for row in summary),
            "balance": sum(row["balance"] for row in summary),
        }
        # Pour le graphique : du plus ancien au plus récent, de gauche à droite.
        context["chart_days"] = [
            {
                "day": row["day"].isoformat(),
                "label": date_format(row["day"], "D j M"),
                "short": date_format(row["day"], "j"),
                "weekday": date_format(row["day"], "D"),
                "cashed": float(row["cashed"]),
                "spent": float(row["spent"]),
                "selected": row["day"] == day,
            }
            for row in reversed(summary)
        ]
        context["month"] = dashboard_metrics(self.restaurant, "month")
        return context


class SalesView(ManagerRequiredMixin, RestaurantContextMixin, TemplateView):
    """Ventes : l'argent reçu chaque jour, avec le mode de paiement et ce qui reste à encaisser."""

    template_name = "manager/sales.html"

    def get_month(self):
        this_month = timezone.localdate().replace(day=1)
        try:
            year, month = (int(part) for part in self.request.GET.get("mois", "").split("-"))
            return min(date(year, month, 1), this_month)
        except ValueError:
            return this_month

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        this_month = today.replace(day=1)
        dr = get_date_range(self.request)
        # Un mois choisi s'affiche comme la vue par mois (flèches ‹ › comprises).
        by_month = not dr.active or dr.key == "mois_choisi"
        month = self.get_month() if by_month else dr.start.replace(day=1)
        if not by_month:
            sales = sales_between(self.restaurant, dr.start, dr.end)
            expenses_qs = Expense.objects.filter(restaurant=self.restaurant, **dr.contains_filter("date"))
        else:
            sales = sales_by_day(self.restaurant, month.year, month.month)
            expenses_qs = Expense.objects.filter(
                restaurant=self.restaurant, date__year=month.year, date__month=month.month
            )
        today_row = next((row for row in sales["days"] if row["day"] == today), None)
        following = (month + timedelta(days=32)).replace(day=1)
        context.update(
            {
                "sales": sales,
                "month": month,
                "dr": dr,
                "presets": PRESETS,
                "is_range": not by_month,
                "show_today": month == this_month if by_month else dr.start <= today <= dr.end,
                "is_current_month": month == this_month and by_month,
                "previous_month": (month - timedelta(days=1)).replace(day=1),
                "next_month": following if following <= this_month else None,
                "today": today,
                "today_received": today_row["received"] if today_row else 0,
                "today_count": today_row["count"] if today_row else 0,
                "month_expenses": expenses_qs.aggregate(t=Sum("amount"))["t"] or 0,
            }
        )
        return context


class ExpenseListView(ManagerRequiredMixin, RestaurantContextMixin, ListView):
    template_name = "manager/expenses.html"
    context_object_name = "expenses"

    paginate_by = 60

    def get_queryset(self):
        self.dr = get_date_range(self.request)
        self.category = self.request.GET.get("categorie", "")
        qs = Expense.objects.filter(restaurant=self.restaurant).select_related("user").order_by("-date", "-created_at")
        if self.dr.active:
            qs = qs.filter(**self.dr.contains_filter("date"))
        if self.category in ExpenseCategory.values:
            qs = qs.filter(category=self.category)
        else:
            self.category = ""
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        groups = []
        for expense in context["expenses"]:
            month = expense.date.replace(day=1)
            if not groups or groups[-1]["month"] != month:
                groups.append({"month": month, "expenses": []})
            groups[-1]["expenses"].append(expense)
        # Total de chaque mois affiché (sur tout le mois, pas seulement la page).
        all_expenses = Expense.objects.filter(restaurant=self.restaurant)
        for group in groups:
            month = group["month"]
            group["total"] = (
                all_expenses.filter(date__year=month.year, date__month=month.month).aggregate(t=Sum("amount"))["t"] or 0
            )
        today = timezone.localdate()
        this_month = all_expenses.filter(date__year=today.year, date__month=today.month)
        month_total = this_month.aggregate(t=Sum("amount"))["t"] or 0
        by_category = [
            {
                "label": ExpenseCategory(row["category"]).label,
                "key": row["category"],
                "amount": row["total"],
                "percent": round(row["total"] * 100 / month_total) if month_total else 0,
            }
            for row in this_month.values("category").annotate(total=Sum("amount")).order_by("-total")
        ]
        filtered = self.get_queryset().order_by()
        range_total = filtered.aggregate(total=Sum("amount"), n=Count("id"))
        context.update(
            {
                "dr": self.dr,
                "presets": PRESETS,
                "category": self.category,
                "category_choices": ExpenseCategory.choices,
                "filtering": self.dr.active or bool(self.category),
                "range_total": range_total["total"] or 0,
                "range_count": range_total["n"],
                "groups": groups,
                "month_total": month_total,
                "by_category": by_category,
                "today": today,
                "month_received": sales_by_day(self.restaurant, today.year, today.month)["total"],
            }
        )
        return context


class ExpenseCreateView(ManagerRequiredMixin, RestaurantContextMixin, CreateView):
    form_class = ExpenseForm
    template_name = "manager/expense_form.html"

    def get_initial(self):
        # Ouvert depuis le journal d'un jour : la dépense est datée de ce jour-là.
        try:
            day = date.fromisoformat(self.request.GET.get("jour", ""))
        except ValueError:
            day = timezone.localdate()
        return {"date": day}

    def get_success_url(self):
        return f"{reverse('finance:dashboard')}?jour={self.object.date.isoformat()}"

    def form_valid(self, form):
        form.instance.restaurant = self.restaurant
        form.instance.user = self.request.user
        messages.success(self.request, "Dépense enregistrée.")
        return super().form_valid(form)
