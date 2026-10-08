from django.urls import path

from apps.users import views

app_name = "users"

urlpatterns = [
    path("connexion/", views.UserLoginView.as_view(), name="login"),
    path("deconnexion/", views.UserLogoutView.as_view(), name="logout"),
    path("inscription/", views.RegisterView.as_view(), name="register"),
    path("profil/", views.ProfileView.as_view(), name="profile"),
    path("profil/adresses/", views.AddressListView.as_view(), name="addresses"),
    path("profil/adresses/nouvelle/", views.AddressCreateView.as_view(), name="address_create"),
    path("profil/adresses/<int:pk>/", views.AddressUpdateView.as_view(), name="address_update"),
    path("mot-de-passe-oublie/", views.PasswordResetStartView.as_view(), name="password_reset"),
    path("mot-de-passe-oublie/envoye/", views.PasswordResetDonePage.as_view(), name="password_reset_done"),
    path(
        "mot-de-passe-oublie/<uidb64>/<token>/",
        views.PasswordResetConfirmPage.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "mot-de-passe-oublie/termine/",
        views.PasswordResetCompletePage.as_view(),
        name="password_reset_complete",
    ),
]
