from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm

from apps.core.forms import style_form
from apps.users.models import User


class StyledFormMixin:
    def _style(self):
        style_form(self)


class LoginForm(StyledFormMixin, AuthenticationForm):
    error_messages = {
        "invalid_login": (
            "E-mail ou mot de passe incorrect. Vérifiez les majuscules : le mot de passe distingue « A » et « a »."
        ),
        "inactive": "Ce compte est désactivé. Contactez votre gérant.",
    }
    username = forms.EmailField(label="Adresse e-mail")
    password = forms.CharField(
        label="Mot de passe",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class ProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class StyledPasswordResetForm(StyledFormMixin, PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].label = "Adresse e-mail"
        self._style()


class StyledSetPasswordForm(StyledFormMixin, SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = "Nouveau mot de passe"
        self.fields["new_password2"].label = "Confirmer le mot de passe"
        self._style()
