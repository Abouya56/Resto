from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0003_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="customer_email",
            field=models.EmailField(blank=True, max_length=254, verbose_name="e-mail"),
        ),
        migrations.AddField(
            model_name="order",
            name="customer_first_name",
            field=models.CharField(blank=True, max_length=150, verbose_name="prénom"),
        ),
        migrations.AddField(
            model_name="order",
            name="customer_last_name",
            field=models.CharField(blank=True, max_length=150, verbose_name="nom"),
        ),
        migrations.AddField(
            model_name="order",
            name="customer_phone",
            field=models.CharField(blank=True, max_length=30, verbose_name="téléphone"),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_city",
            field=models.CharField(blank=True, max_length=120, verbose_name="ville"),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_district",
            field=models.CharField(blank=True, max_length=120, verbose_name="quartier"),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_landmark",
            field=models.CharField(blank=True, max_length=255, verbose_name="point de repère"),
        ),
        migrations.AddField(
            model_name="order",
            name="latitude",
            field=models.DecimalField(
                blank=True, decimal_places=6, max_digits=9, null=True, verbose_name="latitude"
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="longitude",
            field=models.DecimalField(
                blank=True, decimal_places=6, max_digits=9, null=True, verbose_name="longitude"
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="delivery_address_text",
            field=models.CharField(blank=True, max_length=400, verbose_name="adresse"),
        ),
    ]
