from django import forms
from django.core.files.images import get_image_dimensions

from apps.core.forms import style_form
from apps.core.models import SiteSettings
from apps.users.models import User

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MIN_IMAGE_WIDTH = 1200
ALLOWED_TYPES = ("image/jpeg", "image/png", "image/webp")


class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = (
            "site_name",
            "logo",
            "hero_image",
            "banner_text",
            "hero_kicker",
            "hero_title",
            "hero_lead",
            "hero_button_label",
            "restaurants_kicker",
            "restaurants_title",
            "closing_image",
            "closing_title",
            "closing_text",
            "closing_button_label",
        )
        widgets = {
            "hero_title": forms.Textarea(attrs={"rows": 2}),
            "hero_lead": forms.Textarea(attrs={"rows": 3}),
            "closing_text": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form(self)
        for name in ("logo", "hero_image", "closing_image"):
            self.fields[name].widget.attrs["accept"] = ",".join(ALLOWED_TYPES)
        for name in ("hero_kicker", "hero_title", "hero_lead", "hero_button_label", "closing_title", "closing_text"):
            self.fields[name].required = True

    def _clean_image(self, name):
        image = self.cleaned_data.get(name)
        if not image or not hasattr(image, "content_type"):
            return image  # inchangée ou supprimée
        if image.size > MAX_IMAGE_BYTES:
            raise forms.ValidationError("L'image ne doit pas dépasser 5 Mo.")
        if image.content_type not in ALLOWED_TYPES:
            raise forms.ValidationError("Formats acceptés : JPG, PNG ou WebP.")
        width, _height = get_image_dimensions(image)
        if width and width < MIN_IMAGE_WIDTH:
            raise forms.ValidationError(
                f"Image trop petite ({width} px de large). Prenez une photo d'au moins {MIN_IMAGE_WIDTH} px de large."
            )
        return image

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if not logo or not hasattr(logo, "content_type"):
            return logo  # inchangé ou supprimé
        if logo.size > 2 * 1024 * 1024:
            raise forms.ValidationError("Le logo ne doit pas dépasser 2 Mo.")
        if logo.content_type not in ALLOWED_TYPES:
            raise forms.ValidationError("Formats acceptés : JPG, PNG ou WebP.")
        return logo

    def clean_hero_image(self):
        return self._clean_image("hero_image")

    def clean_closing_image(self):
        return self._clean_image("closing_image")


class UserEditForm(forms.ModelForm):
    """Ce que le super admin peut corriger sur un compte. Le rôle se règle depuis l'équipe du restaurant."""

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone", "is_active")
        labels = {
            "first_name": "Prénom",
            "last_name": "Nom",
            "email": "Adresse e-mail (sert à se connecter)",
            "phone": "Téléphone",
            "is_active": "Compte actif",
        }
        help_texts = {"is_active": "Décochez pour empêcher cette personne de se connecter, sans supprimer son compte."}

    def __init__(self, *args, editor=None, **kwargs):
        self.editor = editor
        super().__init__(*args, **kwargs)
        style_form(self)
        self.fields["email"].widget.attrs["autocomplete"] = "off"

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_is_active(self):
        active = self.cleaned_data["is_active"]
        if not active and self.editor is not None and self.instance.pk == self.editor.pk:
            raise forms.ValidationError("Vous ne pouvez pas désactiver votre propre compte.")
        return active


PASSWORD_MIN_LENGTH = 6


class UserPasswordForm(forms.Form):
    """Définir un nouveau mot de passe (l'ancien n'est jamais lisible : il est chiffré).

    Règle simple, car c'est le super admin qui le donne : 6 caractères au moins.
    """

    new_password1 = forms.CharField(
        label="Nouveau mot de passe",
        strip=False,
        widget=forms.PasswordInput(),
        help_text=f"Au moins {PASSWORD_MIN_LENGTH} caractères. Notez-le : il ne sera plus affiché.",
    )
    new_password2 = forms.CharField(label="Confirmer le mot de passe", strip=False, widget=forms.PasswordInput())

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        style_form(self)
        for field in self.fields.values():
            field.widget.attrs["autocomplete"] = "new-password"

    def clean_new_password1(self):
        password = self.cleaned_data["new_password1"]
        if len(password) < PASSWORD_MIN_LENGTH:
            raise forms.ValidationError(f"Trop court : au moins {PASSWORD_MIN_LENGTH} caractères.")
        if password != password.strip():
            raise forms.ValidationError("Enlevez les espaces au début ou à la fin.")
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("new_password1") and cleaned.get("new_password1") != cleaned.get("new_password2"):
            self.add_error("new_password2", "Les deux mots de passe ne sont pas identiques.")
        return cleaned

    def save(self):
        self.user.set_password(self.cleaned_data["new_password1"])
        self.user.save(update_fields=["password"])
        return self.user
