from django import forms

from apps.finance.models import Expense


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ("category", "amount", "description", "date", "receipt")
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"
            elif isinstance(field.widget, forms.ClearableFileInput):
                field.widget.attrs["class"] = "form-control"
            else:
                field.widget.attrs["class"] = "form-control"
