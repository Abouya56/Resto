from django import forms

from apps.core.forms import RestaurantScopedFormMixin, style_form
from apps.menus.models import Category, Product


class StyledModelForm(RestaurantScopedFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form(self)


class CategoryForm(StyledModelForm):
    class Meta:
        model = Category
        # L'ordre se règle avec les flèches de la liste, pas avec un numéro à taper.
        fields = ("name", "description", "is_active")
        labels = {
            "name": "Nom de la catégorie",
            "description": "Petite phrase (facultatif)",
            "is_active": "Visible sur la carte",
        }
        help_texts = {
            "name": "Ex. Grillades, Boissons, Desserts.",
            "description": "Affichée sous le titre sur la carte. Ex. « Servies avec alloco ou attiéké ».",
            "is_active": "Décochez pour cacher toute la catégorie et ses plats aux clients.",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


def parse_prices(text):
    """« 1000, 1 500 » → [1000, 1500]. Erreur claire si un prix n'est pas un nombre."""
    prices = []
    for part in (text or "").replace(";", ",").split(","):
        cleaned = "".join(part.split()).replace("\u202f", "").upper().removesuffix("F").removesuffix("FCFA")
        if not cleaned:
            continue
        if not cleaned.isdigit() or int(cleaned) <= 0:
            raise forms.ValidationError(
                f"« {part.strip()} » n'est pas un prix. Écrivez des nombres séparés par des virgules."
            )
        prices.append(int(cleaned))
    if len(prices) > 6:
        raise forms.ValidationError("6 autres prix au maximum.")
    return sorted(set(prices))


class ProductForm(StyledModelForm):
    other_prices = forms.CharField(
        label="Autres prix (facultatif)",
        required=False,
        help_text="Le même plat à d'autres prix, séparés par des virgules. Ex. : 1000, 1500. "
        "Le client choisit son prix en commandant.",
    )

    class Meta:
        model = Product
        labels = {"image": "Photo du plat"}
        help_texts = {
            "image": "Sans photo, une illustration est affichée à la place. Ajoutez la vôtre à tout moment.",
        }
        fields = (
            "category",
            "name",
            "description",
            "price",
            "image",
            "is_available",
            "is_active",
            "prep_minutes",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        restaurant = self.restaurant
        if restaurant:
            self.fields["category"].queryset = Category.objects.filter(restaurant=restaurant, is_active=True)
        self.fields["price"].label = "Prix"
        if self.instance.pk and self.instance.extra_prices:
            self.fields["other_prices"].initial = ", ".join(str(int(p)) for p in self.instance.extra_prices)
        self.order_fields(["category", "name", "description", "price", "other_prices"])

    def clean_other_prices(self):
        return parse_prices(self.cleaned_data.get("other_prices"))

    def save(self, commit=True):
        product = super().save(commit=False)
        main = int(product.price) if product.price is not None else None
        product.extra_prices = [p for p in self.cleaned_data.get("other_prices", []) if p != main]
        if commit:
            product.save()
            self.save_m2m()
        return product
