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


class ProductForm(StyledModelForm):
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
