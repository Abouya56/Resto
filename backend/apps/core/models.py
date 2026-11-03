from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class RestaurantScopedModel(TimeStampedModel):
    """Toutes les données métier d'un restaurant héritent de ce modèle."""

    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    class Meta:
        abstract = True


class SiteSettings(models.Model):
    """Réglages de la page d'accueil, modifiables par le super-admin. Une seule ligne dans la base."""

    site_name = models.CharField("nom du site", max_length=40, blank=True, default="Resto")
    logo = models.ImageField("logo du site", upload_to="site/", blank=True, null=True)
    hero_image = models.ImageField("photo de couverture", upload_to="site/", blank=True, null=True)
    banner_text = models.CharField("bandeau d'annonce", max_length=160, blank=True)
    hero_kicker = models.CharField("petit titre", max_length=80, default="Commander au restaurant")
    hero_title = models.CharField("grand titre", max_length=120, default="Les restaurants,\nchez vous.")
    hero_lead = models.TextField(
        "texte d'introduction",
        max_length=300,
        default=(
            "Commandez à table, à emporter ou en livraison. "
            "Vous payez au restaurant, en espèces ou en mobile money."
        ),
    )
    hero_button_label = models.CharField("bouton principal", max_length=40, default="Voir les restaurants")
    restaurants_kicker = models.CharField("petit titre de la liste", max_length=80, default="Près de chez vous")
    restaurants_title = models.CharField("titre de la liste", max_length=80, default="Restaurants ouverts")
    closing_image = models.ImageField("photo du bloc restaurateur", upload_to="site/", blank=True, null=True)
    closing_title = models.CharField("titre du bloc restaurateur", max_length=100, default="Vous tenez un resto ?")
    closing_text = models.TextField(
        "texte du bloc restaurateur",
        max_length=300,
        default="Envoyez votre demande, nous la validons, puis vous remplissez la fiche de votre établissement.",
    )
    closing_button_label = models.CharField(
        "bouton du bloc restaurateur", max_length=40, default="Ouvrir mon restaurant"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "page d'accueil"
        verbose_name_plural = "page d'accueil"

    def __str__(self):
        return "Page d'accueil"

    def save(self, *args, **kwargs):
        self.pk = 1  # une seule ligne
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
