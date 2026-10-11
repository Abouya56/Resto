from django import forms

from apps.core.forms import RestaurantScopedFormMixin, style_form
from apps.tables.models import DiningTable


class DiningTableForm(RestaurantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = DiningTable
        fields = ("number", "capacity", "status", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form(self)
