from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.validators import FileExtensionValidator
from django.db import transaction

from apps.core.forms import style_form
from apps.restaurants.approval import notify_platform_admins
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
            "is_accepting_orders",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["address"].required = True
        self.fields["city"].required = True
        self.fields["phone"].required = True
        style_form(self)
        self.fields["description"].widget.attrs["rows"] = 4


class ManagerOnboardingForm(forms.Form):
    """Demande minimale : identité du gérant + pièce + nom du restaurant."""

    first_name = forms.CharField(label="Prénom", max_length=150)
    last_name = forms.CharField(label="Nom", max_length=150)
    email = forms.EmailField(label="Votre e-mail")
    phone = forms.CharField(label="Téléphone", max_length=30)
    password1 = forms.CharField(label="Mot de passe", widget=forms.PasswordInput, min_length=8)
    password2 = forms.CharField(label="Confirmer le mot de passe", widget=forms.PasswordInput)
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

    def __init__(self, *args, user=None, **kwargs):
        self.user = user if (user and getattr(user, "is_authenticated", False)) else None
        super().__init__(*args, **kwargs)
        if self.user:
            for name in ("first_name", "last_name", "email", "phone", "password1", "password2"):
                self.fields.pop(name)
        style_form(self)

    def clean_identity_document(self):
        uploaded = self.cleaned_data["identity_document"]
        if uploaded and uploaded.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Le fichier ne doit pas dépasser 5 Mo.")
        return uploaded

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Un compte existe déjà avec cet e-mail. Connectez-vous.")
        return email

    def clean(self):
        cleaned = super().clean()
        if "password1" in self.fields:
            p1 = cleaned.get("password1")
            p2 = cleaned.get("password2")
            if p1 and p2 and p1 != p2:
                self.add_error("password2", "Les mots de passe ne correspondent pas.")
            elif p1:
                validate_password(p1)
        return cleaned

    def save(self):
        data = self.cleaned_data
        with transaction.atomic():
            if self.user:
                user = self.user
                if user.role == Role.CUSTOMER:
                    user.role = Role.MANAGER
                    user.save(update_fields=["role"])
            else:
                user = User.objects.create_user(
                    email=data["email"],
                    password=data["password1"],
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                    phone=data.get("phone", ""),
                    role=Role.MANAGER,
                )
            restaurant = Restaurant.objects.create(
                name=data["restaurant_name"],
                phone=data.get("phone", "") or user.phone,
                email=user.email,
                status=RestaurantStatus.PENDING,
                is_accepting_orders=False,
                owner=user,
                identity_type=data["identity_type"],
                identity_document=data["identity_document"],
                business_document=data.get("business_document"),
            )
            Employee.objects.get_or_create(
                user=user,
                restaurant=restaurant,
                defaults={"role": Role.MANAGER},
            )
        notify_platform_admins(
            "Nouvelle demande de restaurant",
            f"{restaurant.name} attend une validation.",
            "/admin-plateforme/restaurants/",
        )
        return user, restaurant


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form(self)
        if self.instance.pk:
            self.fields["email"].initial = self.instance.user.email
            self.fields["first_name"].initial = self.instance.user.first_name
            self.fields["last_name"].initial = self.instance.user.last_name
            self.fields["phone"].initial = self.instance.user.phone
            self.fields["password"].required = False

    def save(self, restaurant, commit=True):
        email = self.cleaned_data["email"].lower()
        user = User.objects.filter(email=email).first()
        if user is None:
            password = self.cleaned_data.get("password")
            if not password:
                raise forms.ValidationError("Un mot de passe est requis pour créer le compte.")
            user = User.objects.create_user(
                email=email,
                password=password,
                first_name=self.cleaned_data["first_name"],
                last_name=self.cleaned_data["last_name"],
                phone=self.cleaned_data.get("phone", ""),
                role=self.cleaned_data["role"],
            )
        else:
            user.first_name = self.cleaned_data["first_name"]
            user.last_name = self.cleaned_data["last_name"]
            user.phone = self.cleaned_data.get("phone", "")
            if user.role == Role.CUSTOMER:
                user.role = self.cleaned_data["role"]
            user.save()
        employee = super().save(commit=False)
        employee.user = user
        employee.restaurant = restaurant
        if commit:
            employee.save()
        return employee
