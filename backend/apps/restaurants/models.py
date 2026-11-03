from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.text import slugify

from apps.core.models import TimeStampedModel
from apps.core.storage import private_storage
from apps.users.roles import Role


class RestaurantStatus(models.TextChoices):
    PENDING = "pending", "En attente de validation"
    ACTIVE = "active", "Actif"
    REJECTED = "rejected", "Refusé"
    SUSPENDED = "suspended", "Suspendu"
    CLOSED = "closed", "Fermé"
    UNPAID = "unpaid", "Licence à payer"


class IdentityDocumentType(models.TextChoices):
    CNI = "cni", "Carte nationale d'identité"
    PASSPORT = "passport", "Passeport"
    RESIDENCE = "residence", "Titre de séjour"
    OTHER = "other", "Autre pièce"


class SubscriptionPlan(models.TextChoices):
    TRIAL = "trial", "Essai"
    STARTER = "starter", "Starter"
    PRO = "pro", "Professionnel"


class Restaurant(TimeStampedModel):
    name = models.CharField("nom", max_length=180)
    slug = models.SlugField("identifiant", max_length=200, unique=True, blank=True)
    description = models.TextField("description", blank=True)
    logo = models.ImageField("logo", upload_to="restaurants/logos/", blank=True, null=True)
    cover = models.ImageField("photo de couverture", upload_to="restaurants/covers/", blank=True, null=True)
    phone = models.CharField("téléphone", max_length=30, blank=True)
    email = models.EmailField("e-mail", blank=True)
    address = models.CharField("adresse", max_length=255, blank=True)
    city = models.CharField("ville", max_length=120, blank=True)
    district = models.CharField("quartier", max_length=120, blank=True)
    latitude = models.DecimalField("latitude", max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField("longitude", max_digits=9, decimal_places=6, null=True, blank=True)
    status = models.CharField(
        "statut", max_length=20, choices=RestaurantStatus.choices, default=RestaurantStatus.ACTIVE
    )
    delivery_fee = models.DecimalField("frais de livraison", max_digits=10, decimal_places=2, default=0)
    min_delivery_amount = models.DecimalField("minimum de livraison", max_digits=10, decimal_places=2, default=0)
    estimated_prep_minutes = models.PositiveIntegerField("temps de préparation (min)", default=25)
    is_accepting_orders = models.BooleanField("accepte les commandes", default=True)
    license_until = models.DateField(
        "licence valable jusqu'au",
        null=True,
        blank=True,
        help_text="Vide = sans limite. Passé cette date, le restaurant se ferme tant que la licence n'est pas payée.",
    )
    subscription_plan = models.CharField(
        "formule", max_length=20, choices=SubscriptionPlan.choices, default=SubscriptionPlan.TRIAL
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_restaurants",
    )
    # Coordonnées données dans la demande : le compte gérant n'existe qu'après validation par la plateforme.
    applicant_name = models.CharField("demandeur", max_length=300, blank=True)
    applicant_email = models.EmailField("e-mail du demandeur", blank=True)
    applicant_phone = models.CharField("téléphone du demandeur", max_length=30, blank=True)
    identity_type = models.CharField(
        "type de pièce",
        max_length=20,
        choices=IdentityDocumentType.choices,
        blank=True,
    )
    identity_document = models.FileField(
        "pièce d'identité",
        upload_to="restaurants/kyc/identity/",
        storage=private_storage,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(["pdf", "jpg", "jpeg", "png"])],
    )
    business_document = models.FileField(
        "justificatif d'activité",
        upload_to="restaurants/kyc/business/",
        storage=private_storage,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(["pdf", "jpg", "jpeg", "png"])],
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_restaurants",
    )
    review_note = models.CharField("motif / commentaire", max_length=255, blank=True)

    class Meta:
        verbose_name = "restaurant"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def manager_name(self):
        """Le gérant : son compte une fois créé, sinon le nom donné dans la demande."""
        if self.owner_id:
            return self.owner.get_full_name() or self.owner.email
        return self.applicant_name

    @property
    def manager_email(self):
        return self.owner.email if self.owner_id else self.applicant_email

    @property
    def manager_phone(self):
        return (self.owner.phone if self.owner_id else "") or self.applicant_phone

    @property
    def is_approved(self):
        return self.status == RestaurantStatus.ACTIVE

    @property
    def is_profile_complete(self):
        return bool((self.address or "").strip() and (self.city or "").strip())

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "restaurant"
            slug = base
            index = 1
            while Restaurant.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                index += 1
                slug = f"{base}-{index}"
            self.slug = slug
        super().save(*args, **kwargs)


class EmployeeStatus(models.TextChoices):
    ACTIVE = "active", "Actif"
    INACTIVE = "inactive", "Inactif"


class Employee(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employments")
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="employees")
    role = models.CharField("rôle", max_length=32, choices=[c for c in Role.CHOICES if c[0] in Role.STAFF])
    status = models.CharField("statut", max_length=20, choices=EmployeeStatus.choices, default=EmployeeStatus.ACTIVE)
    is_active = models.BooleanField("actif", default=True)
    hired_at = models.DateField("embauché le", null=True, blank=True)

    class Meta:
        verbose_name = "employé"
        unique_together = ("user", "restaurant")
        ordering = ["restaurant", "role", "user__last_name"]

    def __str__(self):
        return f"{self.user} — {self.get_role_display()} ({self.restaurant})"

    def save(self, *args, **kwargs):
        self.is_active = self.status == EmployeeStatus.ACTIVE
        super().save(*args, **kwargs)


class LicensePayment(TimeStampedModel):
    """Un paiement de licence enregistré par le super admin : il ouvre ou prolonge l'accès du restaurant."""

    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="license_payments")
    months = models.PositiveSmallIntegerField("durée (mois)")
    amount = models.DecimalField("montant reçu", max_digits=10, decimal_places=2, default=0)
    valid_until = models.DateField("valable jusqu'au")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    note = models.CharField("note", max_length=255, blank=True)

    class Meta:
        verbose_name = "paiement de licence"
        verbose_name_plural = "paiements de licence"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.restaurant} · {self.months} mois · jusqu'au {self.valid_until}"
