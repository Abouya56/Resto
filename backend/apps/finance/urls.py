from django.urls import path

from apps.finance import views

app_name = "finance"

urlpatterns = [
    path("gerant/finances/", views.FinanceDashboardView.as_view(), name="dashboard"),
    path("gerant/depenses/", views.ExpenseListView.as_view(), name="expenses"),
    path("gerant/depenses/nouvelle/", views.ExpenseCreateView.as_view(), name="expense_create"),
]
