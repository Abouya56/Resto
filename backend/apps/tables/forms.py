from django import forms

from apps.tables.models import DiningTable


class DiningTableForm(forms.ModelForm):
    class Meta:
        model = DiningTable
        fields = ("number", "capacity", "status", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs["class"] = "form-control"
