from decimal import Decimal

from django import forms

from apps.core.forms import RestaurantScopedFormMixin, style_form
from apps.inventory.models import RecipeIngredient, StockItem

UNIT_CHOICES = [
    ("kg", "kg (kilo)"),
    ("g", "g (gramme)"),
    ("L", "L (litre)"),
    ("cl", "cl (centilitre)"),
    ("unité", "unité / pièce"),
    ("bouteille", "bouteille"),
    ("sac", "sac"),
    ("boîte", "boîte"),
]


def _decimal_input(field, placeholder=""):
    field.localize = True
    field.widget = forms.TextInput(attrs={"inputmode": "decimal", "placeholder": placeholder, "autocomplete": "off"})


class StockItemForm(RestaurantScopedFormMixin, forms.ModelForm):
    """La quantité se saisit à la création ; ensuite elle ne bouge que par des mouvements (traçables)."""

    class Meta:
        model = StockItem
        fields = ("name", "unit", "quantity", "min_threshold", "is_active")
        labels = {
            "name": "Nom de l'article",
            "quantity": "Quantité en stock aujourd'hui",
            "min_threshold": "M'alerter quand il reste",
            "is_active": "Article suivi",
        }
        help_texts = {
            "min_threshold": "Ex. 5 : vous êtes prévenu quand il reste 5 ou moins.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        units = list(UNIT_CHOICES)
        current = self.instance.unit if self.instance.pk else None
        if current and current not in dict(units):
            units.append((current, current))
        self.fields["unit"] = forms.ChoiceField(label="Unité", choices=units, initial="kg")
        _decimal_input(self.fields["quantity"], "Ex. 20")
        _decimal_input(self.fields["min_threshold"], "Ex. 5")
        if self.instance.pk:
            # Une fois créé, on corrige la quantité avec « Compter » : l'historique reste juste.
            del self.fields["quantity"]
        style_form(self)
        self.fields["name"].widget.attrs["placeholder"] = "Ex. Riz, Huile, Coca 33 cl"


class StockMovementForm(forms.Form):
    action = forms.ChoiceField(choices=[("in", "Ajouter"), ("out", "Retirer"), ("adjust", "Compter")])
    quantity = forms.DecimalField(label="Quantité", min_value=0, decimal_places=3, max_digits=12, localize=True)
    reason = forms.CharField(label="Motif (facultatif)", max_length=255, required=False)


class RecipeIngredientForm(forms.ModelForm):
    """On demande « 1 kg de riz sert combien de plats ? » : c'est ainsi qu'un cuisinier compte."""

    servings = forms.DecimalField(
        label="Combien de plats ?",
        max_digits=8,
        decimal_places=2,
        localize=True,
        help_text="Ex. 1 kg de riz sert 4 plats → tapez 4. 1 bouteille de Brakina = 1 Brakina → tapez 1.",
    )

    class Meta:
        model = RecipeIngredient
        fields = ("stock_item",)
        labels = {"stock_item": "Quel article du stock ?"}

    def __init__(self, *args, product=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.product = product
        self.fields["stock_item"].queryset = StockItem.objects.filter(
            restaurant=product.restaurant, is_active=True
        ).order_by("name")
        self.fields["stock_item"].empty_label = "Choisir un article…"
        self.fields["stock_item"].label_from_instance = lambda item: f"{item.name} (en {item.unit})"
        _decimal_input(self.fields["servings"], "Ex. 4")
        style_form(self)

    def clean_servings(self):
        servings = self.cleaned_data["servings"]
        if servings is None or servings <= 0:
            raise forms.ValidationError("Indiquez un nombre plus grand que 0 (ex. 4).")
        if servings > 10000:
            raise forms.ValidationError("Nombre trop grand : vérifiez l'unité de l'article.")
        return servings

    def clean_stock_item(self):
        item = self.cleaned_data["stock_item"]
        if RecipeIngredient.objects.filter(product=self.product, stock_item=item).exists():
            raise forms.ValidationError(
                f"{item.name} est déjà relié à ce plat. Supprimez la ligne pour changer la quantité."
            )
        return item

    def save(self, commit=True):
        self.instance.product = self.product
        servings = self.cleaned_data["servings"]
        self.instance.quantity = (Decimal(1) / servings).quantize(Decimal("0.000001"))
        return super().save(commit)
