from django.urls import path

from apps.core import pwa, views

app_name = "core"

urlpatterns = [
    path("manifest.webmanifest", pwa.manifest, name="manifest"),
    path("sw.js", pwa.service_worker, name="service_worker"),
    path("hors-ligne/", pwa.offline, name="offline"),
    path("credits-photos/", views.PhotoCreditsView.as_view(), name="photo_credits"),
    path("", views.HomeView.as_view(), name="home"),
    path("notifications/", views.NotificationListView.as_view(), name="notifications"),
]
