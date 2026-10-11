from django import forms

from apps.core.forms import RestaurantScopedFormMixin, style_form
from apps.inventory.models import StockItem, StockMovementType


class StockItemForm(RestaurantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = StockItem
        fields = ("name", "unit", "quantity", "min_threshold", "product", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form(self)
        restaurant = self.restaurant
        if restaurant:
            from apps.menus.models import Product

            self.fields["product"].queryset = Product.objects.filter(restaurant=restaurant)
            self.fields["product"].required = False


class StockMovementForm(forms.Form):
    movement_type = forms.ChoiceField(label="Type de mouvement", choices=StockMovementType.choices)
    quantity = forms.DecimalField(label="Quantité", min_value=0.001, decimal_places=3)
    reason = forms.CharField(label="Motif", max_length=255)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["movement_type"].widget.attrs["class"] = "form-select"
        self.fields["quantity"].widget.attrs["class"] = "form-control"
        self.fields["reason"].widget.attrs["class"] = "form-control"
