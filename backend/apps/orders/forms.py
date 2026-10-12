from django import forms

from apps.core.forms import style_form
from apps.orders.models import OrderType
from apps.orders.services import phone_is_valid

LOCATION_REQUIRED = {
    "city": "Indiquez la ville.",
    "district": "Indiquez le quartier.",
    "address_text": "Indiquez où livrer.",
}


class CheckoutForm(forms.Form):
    """Ce qu'on demande dépend du mode : la table suffit sur place, la livraison exige un lieu."""

    first_name = forms.CharField(label="Prénom", max_length=150)
    last_name = forms.CharField(label="Nom", max_length=150, required=False)
    phone = forms.CharField(label="Téléphone", max_length=30, required=False)
    email = forms.EmailField(label="E-mail (facultatif)", required=False)
    address_text = forms.CharField(
        label="Adresse",
        required=False,
        widget=forms.Textarea,
    )
    city = forms.CharField(label="Ville", max_length=120, required=False)
    district = forms.CharField(label="Quartier", max_length=120, required=False)
    landmark = forms.CharField(label="Point de repère (facultatif)", max_length=255, required=False)
    latitude = forms.DecimalField(required=False, max_digits=9, decimal_places=6, widget=forms.HiddenInput)
    longitude = forms.DecimalField(required=False, max_digits=9, decimal_places=6, widget=forms.HiddenInput)
    note = forms.CharField(
        label="Une précision pour le restaurant ? (facultatif)", required=False, widget=forms.Textarea
    )

    def __init__(self, *args, order_type=OrderType.TAKEAWAY, **kwargs):
        self.order_type = order_type
        super().__init__(*args, **kwargs)
        if order_type != OrderType.DINE_IN:
            self.fields["last_name"].required = True
            self.fields["phone"].required = True
        else:
            self.fields["phone"].label = "Téléphone (facultatif)"
        if order_type == OrderType.DELIVERY:
            for name, message in LOCATION_REQUIRED.items():
                self.fields[name].required = True
                self.fields[name].error_messages["required"] = message
        self.fields["first_name"].error_messages["required"] = "Indiquez votre prénom."
        self.fields["last_name"].error_messages["required"] = "Indiquez votre nom."
        self.fields["phone"].error_messages["required"] = "Indiquez un numéro où vous joindre."
        style_form(self)
        placeholders = {
            "first_name": "Ex. Awa",
            "last_name": "Ex. Koné",
            "phone": "Ex. 07 00 00 00 00",
            "address_text": "Rue, immeuble, porte",
            "city": "Ex. Abidjan",
            "district": "Ex. Cocody",
            "landmark": "Ex. en face de la pharmacie",
            "note": "Ex. sans piment, sonner au portail",
        }
        for name, text in placeholders.items():
            self.fields[name].widget.attrs["placeholder"] = text
        self.fields["phone"].widget.attrs.update({"autocomplete": "tel", "inputmode": "tel"})
        self.fields["first_name"].widget.attrs["autocomplete"] = "given-name"
        self.fields["last_name"].widget.attrs["autocomplete"] = "family-name"
        self.fields["address_text"].widget.attrs["rows"] = 2
        self.fields["note"].widget.attrs["rows"] = 2

    @property
    def needs_location(self):
        return self.order_type == OrderType.DELIVERY

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if phone and not phone_is_valid(phone):
            raise forms.ValidationError("Ce numéro semble incomplet : il faut au moins 8 chiffres.")
        return phone

    def clean(self):
        cleaned = super().clean()
        if self.needs_location:
            for name, message in LOCATION_REQUIRED.items():
                if name not in self.errors and not (cleaned.get(name) or "").strip():
                    self.add_error(name, message)
        return cleaned

    def contact_payload(self):
        data = self.cleaned_data
        return {
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""),
            "phone": data.get("phone", ""),
            "email": data.get("email", ""),
            "city": data.get("city", ""),
            "district": data.get("district", ""),
            "landmark": data.get("landmark", ""),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
        }


class TrackOrderForm(forms.Form):
    number = forms.CharField(label="Numéro de commande", max_length=30)
    phone = forms.CharField(
        label="Téléphone donné à la commande",
        max_length=30,
        required=False,
        help_text="Pas besoin de téléphone pour une commande passée à table sans numéro.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form(self)
        self.fields["number"].widget.attrs.update({"placeholder": "Ex. R261011A76C27", "autocapitalize": "characters"})
        self.fields["phone"].widget.attrs.update(
            {"placeholder": "Ex. 70 00 00 00", "autocomplete": "tel", "inputmode": "tel"}
        )
