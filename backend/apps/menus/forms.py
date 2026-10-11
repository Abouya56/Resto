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
        fields = ("name", "description", "sort_order", "is_active")


class ProductForm(StyledModelForm):
    class Meta:
        model = Product
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
