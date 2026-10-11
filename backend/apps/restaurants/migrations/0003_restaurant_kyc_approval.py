import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def map_legacy_draft_status(apps, schema_editor):
    Restaurant = apps.get_model("restaurants", "Restaurant")
    Restaurant.objects.filter(status="draft").update(status="pending")


class Migration(migrations.Migration):

    dependencies = [
        ("restaurants", "0002_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="restaurant",
            name="address",
            field=models.CharField(blank=True, max_length=255, verbose_name="adresse"),
        ),
        migrations.AlterField(
            model_name="restaurant",
            name="city",
            field=models.CharField(blank=True, max_length=120, verbose_name="ville"),
        ),
        migrations.AlterField(
            model_name="restaurant",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "En attente de validation"),
                    ("active", "Actif"),
                    ("rejected", "Refusé"),
                    ("suspended", "Suspendu"),
                    ("closed", "Fermé"),
                ],
                default="active",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="restaurant",
            name="identity_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("cni", "Carte nationale d'identité"),
                    ("passport", "Passeport"),
                    ("residence", "Titre de séjour"),
                    ("other", "Autre pièce"),
                ],
                max_length=20,
                verbose_name="type de pièce",
            ),
        ),
        migrations.AddField(
            model_name="restaurant",
            name="identity_document",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="restaurants/kyc/identity/",
                validators=[
                    django.core.validators.FileExtensionValidator(["pdf", "jpg", "jpeg", "png"])
                ],
                verbose_name="pièce d'identité",
            ),
        ),
        migrations.AddField(
            model_name="restaurant",
            name="business_document",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="restaurants/kyc/business/",
                validators=[
                    django.core.validators.FileExtensionValidator(["pdf", "jpg", "jpeg", "png"])
                ],
                verbose_name="justificatif d'activité",
            ),
        ),
        migrations.AddField(
            model_name="restaurant",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="restaurant",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reviewed_restaurants",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="restaurant",
            name="review_note",
            field=models.CharField(blank=True, max_length=255, verbose_name="motif / commentaire"),
        ),
        migrations.RunPython(map_legacy_draft_status, migrations.RunPython.noop),
    ]
