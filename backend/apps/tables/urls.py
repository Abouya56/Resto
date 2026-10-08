from django.urls import path

from apps.tables import views

app_name = "tables"

urlpatterns = [
    path("gerant/tables/", views.TableListView.as_view(), name="list"),
    path("gerant/tables/nouvelle/", views.TableCreateView.as_view(), name="create"),
    path("gerant/tables/<int:pk>/", views.TableUpdateView.as_view(), name="update"),
    path("gerant/tables/<int:pk>/qr/", views.qrcode_page, name="qrcode"),
    path("gerant/tables/<int:pk>/qr/regenerer/", views.regenerate_qr, name="regenerate"),
    path("gerant/tables/<int:pk>/qr/telecharger/", views.download_qr, name="download"),
]
