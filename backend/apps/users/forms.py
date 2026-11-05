from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm

from apps.core.forms import style_form
from apps.users import lockout
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

    def clean(self):
        email = (self.data.get("username") or "").strip()
        if lockout.is_locked(email):
            raise forms.ValidationError(lockout.LOCKED_MESSAGE, code="locked")
        try:
            cleaned = super().clean()
        except forms.ValidationError:
            lockout.register_failure(email)
            raise
        lockout.reset(email)
        return cleaned


class NewPasswordForm(StyledFormMixin, forms.Form):
    """Choisir un nouveau mot de passe. Règle simple : 6 caractères au moins."""

    MIN_LENGTH = 6

    new_password1 = forms.CharField(
        label="Nouveau mot de passe",
        strip=False,
        widget=forms.PasswordInput,
        help_text=f"Au moins {MIN_LENGTH} caractères.",
    )
    new_password2 = forms.CharField(label="Confirmer le mot de passe", strip=False, widget=forms.PasswordInput)

    def __init__(self, user, *args, refuse_current=False, **kwargs):
        self.user = user
        self.refuse_current = refuse_current
        super().__init__(*args, **kwargs)
        self._style()
        for field in self.fields.values():
            field.widget.attrs["autocomplete"] = "new-password"

    def clean_new_password1(self):
        password = self.cleaned_data["new_password1"]
        if len(password) < self.MIN_LENGTH:
            raise forms.ValidationError(f"Trop court : au moins {self.MIN_LENGTH} caractères.")
        if password != password.strip():
            raise forms.ValidationError("Enlevez les espaces au début ou à la fin.")
        if self.refuse_current and self.user.check_password(password):
            raise forms.ValidationError("Choisissez un mot de passe différent de celui qu'on vous a donné.")
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("new_password1") and cleaned.get("new_password1") != cleaned.get("new_password2"):
            self.add_error("new_password2", "Les deux mots de passe ne sont pas identiques.")
        return cleaned

    def save(self, must_change=False):
        self.user.set_password(self.cleaned_data["new_password1"])
        self.user.must_change_password = must_change
        self.user.save(update_fields=["password", "must_change_password"])
        return self.user


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
