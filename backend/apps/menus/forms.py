from django import forms

from apps.menus.models import Category, Product


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs["class"] = "form-control"
                field.widget.attrs["rows"] = 3
            else:
                field.widget.attrs["class"] = "form-control"


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

    def __init__(self, *args, restaurant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if restaurant:
            self.fields["category"].queryset = Category.objects.filter(restaurant=restaurant, is_active=True)
