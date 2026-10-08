from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.password_validation import validate_password

from apps.users.models import CustomerAddress, User


class StyledFormMixin:
    def _style(self):
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css} form-control".strip()


class LoginForm(StyledFormMixin, AuthenticationForm):
    username = forms.EmailField(label="Adresse e-mail")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class RegisterForm(StyledFormMixin, forms.ModelForm):
    password1 = forms.CharField(label="Mot de passe", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmation", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()

    def clean_password2(self):
        p1 = self.cleaned_data.get("password1")
        p2 = self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        validate_password(p1)
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class ProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class AddressForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = CustomerAddress
        fields = ("label", "line1", "city", "district", "instructions", "is_default")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()
        self.fields["is_default"].widget.attrs["class"] = "form-check-input"


class StyledPasswordResetForm(StyledFormMixin, PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class StyledSetPasswordForm(StyledFormMixin, SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()
