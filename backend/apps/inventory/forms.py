from django import forms

from apps.inventory.models import StockItem, StockMovementType


class StockItemForm(forms.ModelForm):
    class Meta:
        model = StockItem
        fields = ("name", "unit", "quantity", "min_threshold", "product", "is_active")

    def __init__(self, *args, restaurant=None, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs["class"] = "form-control"
        if restaurant:
            from apps.menus.models import Product

            self.fields["product"].queryset = Product.objects.filter(restaurant=restaurant)
            self.fields["product"].required = False


class StockMovementForm(forms.Form):
    movement_type = forms.ChoiceField(choices=StockMovementType.choices)
    quantity = forms.DecimalField(min_value=0.001, decimal_places=3)
    reason = forms.CharField(max_length=255)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["movement_type"].widget.attrs["class"] = "form-select"
        self.fields["quantity"].widget.attrs["class"] = "form-control"
        self.fields["reason"].widget.attrs["class"] = "form-control"
