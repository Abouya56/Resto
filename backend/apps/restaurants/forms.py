from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.validators import FileExtensionValidator
from django.db import transaction

from apps.core.forms import style_form
from apps.restaurants.approval import notify_platform_admins
from apps.restaurants.team import RECEPTION_LIMIT_MESSAGE, reception_slot_taken
from apps.restaurants.models import Employee, IdentityDocumentType, Restaurant, RestaurantStatus
from apps.users.models import User
from apps.users.roles import Role


class RestaurantForm(forms.ModelForm):
    class Meta:
        model = Restaurant
        fields = (
            "name",
            "description",
            "logo",
            "cover",
            "phone",
            "email",
            "address",
            "city",
            "district",
            "delivery_fee",
            "min_delivery_amount",
            "estimated_prep_minutes",
        )
        labels = {
            "name": "Nom du restaurant",
            "logo": "Logo",
            "cover": "Photo de couverture",
            "email": "E-mail",
            "district": "Quartier",
            "delivery_fee": "Frais de livraison",
            "min_delivery_amount": "Commande minimum pour livrer",
            "estimated_prep_minutes": "Temps de préparation moyen",
        }
        help_texts = {
            "description": "Deux ou trois phrases : votre cuisine, vos spécialités, l'ambiance.",
            "logo": "Image carrée, fond uni de préférence. Sans logo, un logo avec vos initiales est affiché.",
            "cover": "Grande photo de la salle ou d'un plat, affichée sur votre page et dans la liste des restaurants.",
            "delivery_fee": "Mettez 0 si la livraison est offerte.",
            "min_delivery_amount": "Mettez 0 pour livrer toutes les commandes.",
            "estimated_prep_minutes": "Au-delà, la commande s'affiche « en retard » à la réception.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["address"].required = True
        self.fields["city"].required = True
        self.fields["phone"].required = True
        style_form(self)
        self.fields["description"].widget.attrs["rows"] = 3
        placeholders = {
            "phone": "Ex. 70 00 00 00",
            "email": "contact@monrestaurant.com",
            "address": "Ex. Avenue de la Nation, près du marché",
            "city": "Ex. Bobo-Dioulasso",
            "district": "Ex. Koko",
        }
        for name, text in placeholders.items():
            self.fields[name].widget.attrs["placeholder"] = text
        for name in ("delivery_fee", "min_delivery_amount", "estimated_prep_minutes"):
            self.fields[name].widget.attrs["inputmode"] = "numeric"


class ManagerOnboardingForm(forms.Form):
    """La demande : qui vous êtes, votre restaurant et une pièce d'identité. Le compte gérant est donné après validation."""

    first_name = forms.CharField(label="Prénom", max_length=150)
    last_name = forms.CharField(label="Nom", max_length=150)
    email = forms.EmailField(label="Votre e-mail")
    phone = forms.CharField(label="Téléphone", max_length=30)
    restaurant_name = forms.CharField(label="Nom du restaurant", max_length=180)
    identity_type = forms.ChoiceField(
        label="Type de pièce d'identité",
        choices=IdentityDocumentType.choices,
    )
    identity_document = forms.FileField(
        label="Pièce d'identité",
        help_text="CNI, passeport ou titre de séjour. PDF, JPG ou PNG. 5 Mo max.",
        validators=[FileExtensionValidator(["pdf", "jpg", "jpeg", "png"])],
    )
    business_document = forms.FileField(
        label="Justificatif d'activité (facultatif)",
        required=False,
        help_text="Patente, RCCM ou équivalent. PDF, JPG ou PNG.",
        validators=[FileExtensionValidator(["pdf", "jpg", "jpeg", "png"])],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form(self)

    def clean_identity_document(self):
        uploaded = self.cleaned_data["identity_document"]
        if uploaded and uploaded.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Le fichier ne doit pas dépasser 5 Mo.")
        return uploaded

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Un compte existe déjà avec cet e-mail. Contactez la plateforme.")
        return email

    def save(self):
        data = self.cleaned_data
        restaurant = Restaurant.objects.create(
            name=data["restaurant_name"],
            phone=data["phone"],
            email=data["email"],
            status=RestaurantStatus.PENDING,
            is_accepting_orders=False,
            applicant_name=f"{data['first_name']} {data['last_name']}".strip(),
            applicant_email=data["email"],
            applicant_phone=data["phone"],
            identity_type=data["identity_type"],
            identity_document=data["identity_document"],
            business_document=data.get("business_document"),
        )
        notify_platform_admins(
            "Nouvelle demande de restaurant",
            f"{restaurant.name} attend une validation.",
            "/admin-plateforme/restaurants/",
        )
        return restaurant


class EmployeeForm(forms.ModelForm):
    email = forms.EmailField(label="E-mail de l'employé")
    first_name = forms.CharField(label="Prénom")
    last_name = forms.CharField(label="Nom")
    phone = forms.CharField(label="Téléphone", required=False)
    password = forms.CharField(
        label="Mot de passe initial",
        widget=forms.PasswordInput,
        required=False,
        help_text="Obligatoire uniquement pour un nouveau compte.",
    )

    class Meta:
        model = Employee
        fields = ("role", "status")

    def __init__(self, *args, restaurant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.restaurant = restaurant
        style_form(self)
        # Le gérant ne choisit pas le poste : il crée uniquement la réception. Un poste existant ne change pas.
        role = self.instance.role if self.instance.pk else Role.RECEPTION
        self.fields["role"].choices = [(role, dict(Role.CHOICES).get(role, role))]
        self.fields["role"].initial = role
        self.fields["role"].disabled = True
        # Le gérant ne suspend personne : le statut reste celui du compte (actif pour un nouveau compte).
        status = self.instance.status if self.instance.pk else "active"
        self.fields["status"].choices = [(status, dict(self.fields["status"].choices).get(status, status))]
        self.fields["status"].initial = status
        self.fields["status"].disabled = True
        self.existing_user = None
        if self.instance.pk:
            user = self.instance.user
            self.existing_user = user
            self.fields["email"].initial = user.email
            self.fields["first_name"].initial = user.first_name
            self.fields["last_name"].initial = user.last_name
            self.fields["phone"].initial = user.phone
            # L'identité du compte ne se modifie pas depuis un autre établissement.
            self.fields["email"].disabled = True
            self.fields["password"].required = False
            if not self._owns_identity(user):
                for name in ("first_name", "last_name", "phone"):
                    self.fields[name].disabled = True

    def _owns_identity(self, user):
        """Le gérant ne modifie nom et téléphone que d'un compte propre à son établissement."""
        if user.is_platform_admin or user.is_staff:
            return False
        return not user.employments.exclude(restaurant=self.restaurant).exists()

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk:
            return cleaned
        if reception_slot_taken(self.restaurant):
            raise forms.ValidationError(RECEPTION_LIMIT_MESSAGE)
        email = (cleaned.get("email") or "").lower()
        if not email:
            return cleaned
        user = User.objects.filter(email=email).first()
        if user is None:
            password = cleaned.get("password")
            if not password:
                self.add_error("password", "Un mot de passe est requis pour créer le compte.")
            else:
                try:
                    validate_password(password)
                except forms.ValidationError as exc:
                    self.add_error("password", exc)
        else:
            if user.is_platform_admin or user.is_staff:
                self.add_error("email", "Ce compte ne peut pas être ajouté comme employé.")
            elif Employee.objects.filter(user=user, restaurant=self.restaurant).exists():
                self.add_error("email", "Cette personne fait déjà partie de votre équipe.")
        self.existing_user = user
        return cleaned

    def save(self, restaurant=None, commit=True):
        restaurant = restaurant or self.restaurant
        if self.instance.pk:
            user = self.instance.user
            if self._owns_identity(user):
                user.first_name = self.cleaned_data["first_name"]
                user.last_name = self.cleaned_data["last_name"]
                user.phone = self.cleaned_data.get("phone", "")
                user.save(update_fields=["first_name", "last_name", "phone"])
        else:
            user = self.existing_user
            if user is None:
                user = User.objects.create_user(
                    email=self.cleaned_data["email"].lower(),
                    password=self.cleaned_data["password"],
                    first_name=self.cleaned_data["first_name"],
                    last_name=self.cleaned_data["last_name"],
                    phone=self.cleaned_data.get("phone", ""),
                    role=self.cleaned_data["role"],
                )
            elif user.role == Role.CUSTOMER:
                user.role = self.cleaned_data["role"]
                user.save(update_fields=["role"])
        employee = super().save(commit=False)
        employee.user = user
        employee.restaurant = restaurant
        if commit:
            employee.save()
        return employee
