from django import forms


class FrenchClearableFileInput(forms.ClearableFileInput):
    initial_text = "Actuellement"
    input_text = "Modifier"
    clear_checkbox_label = "Supprimer"


def style_form(form):
    for field in form.fields.values():
        if isinstance(field.widget, forms.ClearableFileInput):
            field.widget.initial_text = "Actuellement"
            field.widget.input_text = "Modifier"
            field.widget.clear_checkbox_label = "Supprimer"
            field.widget.attrs["class"] = "form-control"
        elif isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs["class"] = "form-check-input"
        elif isinstance(field.widget, forms.Select):
            field.widget.attrs["class"] = "form-select"
        elif isinstance(field.widget, forms.Textarea):
            field.widget.attrs.setdefault("class", "form-control")
            field.widget.attrs.setdefault("rows", 3)
        else:
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css} form-control".strip()
