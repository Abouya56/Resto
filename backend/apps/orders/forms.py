from datetime import timedelta

from django import forms
from django.utils import timezone

from apps.core.forms import style_form
from apps.orders.models import OrderType
from apps.orders import tracking
from apps.orders.services import phone_is_valid

LOCATION_REQUIRED = {
    "district": "Indiquez votre secteur.",
    "address_text": "Indiquez où livrer.",
}
DELIVERY_DAYS = (("today", "Aujourd'hui"), ("tomorrow", "Demain"))
# Délais proposés pour la commande à l'avance (minutes avant l'arrivée au restaurant).
ARRIVAL_DELAYS = (30, 45, 60, 90, 120, 180)


def _delay_label(minutes):
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h" if not rest else f"{hours} h {rest:02d}"


class CheckoutForm(forms.Form):
    """Le strict nécessaire : le nom sur place ou à emporter ; en livraison, nom, téléphone, secteur et lieu."""

    first_name = forms.CharField(label="Votre nom", max_length=150)
    last_name = forms.CharField(label="Nom", max_length=150, required=False)
    phone = forms.CharField(label="Téléphone", max_length=30, required=False)
    district = forms.CharField(label="Secteur", max_length=120, required=False)
    address_text = forms.CharField(label="Localisation", required=False, widget=forms.Textarea)
    latitude = forms.DecimalField(required=False, max_digits=9, decimal_places=6, widget=forms.HiddenInput)
    longitude = forms.DecimalField(required=False, max_digits=9, decimal_places=6, widget=forms.HiddenInput)
    delivery_day = forms.ChoiceField(
        label="Livrer quand ?", choices=DELIVERY_DAYS, initial="today", widget=forms.RadioSelect, required=False
    )

    arrival_delay = forms.ChoiceField(label="Vous arrivez dans", widget=forms.RadioSelect, required=False)

    def __init__(self, *args, order_type=OrderType.TAKEAWAY, restaurant=None, **kwargs):
        self.order_type = order_type
        super().__init__(*args, **kwargs)
        if order_type == OrderType.PREORDER:
            # Le restaurant a besoin du temps de préparation : pas de délai plus court que cela.
            prep = getattr(restaurant, "estimated_prep_minutes", 0) or 0
            delays = [d for d in ARRIVAL_DELAYS if d >= prep] or [ARRIVAL_DELAYS[-1]]
            self.fields["arrival_delay"].choices = [(str(d), _delay_label(d)) for d in delays]
            self.fields["arrival_delay"].initial = str(delays[0])
            self.fields["arrival_delay"].required = True
            self.fields["arrival_delay"].error_messages["required"] = "Choisissez dans combien de temps vous arrivez."
            self.fields["phone"].required = True
            for name in ("last_name", "district", "address_text", "delivery_day"):
                del self.fields[name]
        else:
            del self.fields["arrival_delay"]
        if order_type == OrderType.DELIVERY:
            self.fields["first_name"].label = "Prénom"
            self.fields["last_name"].required = True
            self.fields["phone"].required = True
            for name, message in LOCATION_REQUIRED.items():
                self.fields[name].required = True
                self.fields[name].error_messages["required"] = message
        elif order_type != OrderType.PREORDER:
            # Sur place ou à emporter, le client est déjà là : le nom suffit. Le téléphone est facultatif :
            # il permet de retrouver sa commande depuis un autre appareil (numéro + téléphone).
            for name in ("last_name", "district", "address_text", "delivery_day"):
                del self.fields[name]
            self.fields["phone"].label = "Téléphone (facultatif)"
            self.fields["phone"].help_text = "Pour suivre votre commande depuis un autre téléphone."
        self.fields["first_name"].error_messages["required"] = (
            "Indiquez votre prénom." if order_type == OrderType.DELIVERY else "Indiquez votre nom."
        )
        style_form(self)
        if order_type == OrderType.DELIVERY:
            self.fields["last_name"].error_messages["required"] = "Indiquez votre nom."
            self.fields["phone"].error_messages["required"] = "Indiquez un numéro où vous joindre."
            self.fields["phone"].widget.attrs.update({"autocomplete": "tel", "inputmode": "tel"})
            self.fields["last_name"].widget.attrs["autocomplete"] = "family-name"
            self.fields["address_text"].widget.attrs["rows"] = 2
            self.fields["delivery_day"].widget.attrs.pop("class", None)
            placeholders = {
                "last_name": "Ex. Koné",
                "phone": "Ex. 07 00 00 00 00",
                "district": "Ex. Secteur 22",
                "address_text": "Ex. près du marché, portail bleu",
            }
            for name, text in placeholders.items():
                self.fields[name].widget.attrs["placeholder"] = text
        if order_type == OrderType.PREORDER:
            self.fields["phone"].error_messages["required"] = "Indiquez un numéro où vous joindre."
            self.fields["phone"].widget.attrs.update(
                {"autocomplete": "tel", "inputmode": "tel", "placeholder": "Ex. 07 00 00 00 00"}
            )
            self.fields["arrival_delay"].widget.attrs.pop("class", None)
        if order_type in (OrderType.DINE_IN, OrderType.TAKEAWAY):
            self.fields["phone"].widget.attrs.update(
                {"autocomplete": "tel", "inputmode": "tel", "placeholder": "Ex. 07 00 00 00 00"}
            )
        self.fields["first_name"].widget.attrs["autocomplete"] = "given-name"
        self.fields["first_name"].widget.attrs["placeholder"] = "Ex. Awa"

    @property
    def needs_location(self):
        return self.order_type == OrderType.DELIVERY

    @property
    def scheduled_for(self):
        """Le jour choisi pour la livraison (aujourd'hui par défaut), ou None hors livraison."""
        if not self.needs_location:
            return None
        today = timezone.localdate()
        return today + timedelta(days=1) if self.cleaned_data.get("delivery_day") == "tomorrow" else today

    @property
    def arrival_at(self):
        """L'heure d'arrivée annoncée (maintenant + le délai choisi), ou None hors commande à l'avance."""
        if self.order_type != OrderType.PREORDER:
            return None
        return timezone.now() + timedelta(minutes=int(self.cleaned_data["arrival_delay"]))

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
            "district": data.get("district", ""),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
        }


class TrackOrderForm(forms.Form):
    number = forms.CharField(label="Numéro de commande", max_length=30)
    phone = forms.CharField(
        label="Téléphone donné à la commande",
        max_length=30,
        required=False,
        help_text="Obligatoire avec le numéro court. Pas besoin si vous avez la référence d'une commande sans téléphone.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form(self)
        self.fields["number"].widget.attrs.update(
            {"placeholder": "Ex. 012", "autocapitalize": "characters", "inputmode": "text", "autocomplete": "off"}
        )
        self.fields["phone"].widget.attrs.update(
            {"placeholder": "Ex. 70 00 00 00", "autocomplete": "tel", "inputmode": "tel"}
        )

    def clean(self):
        cleaned = super().clean()
        number = cleaned.get("number", "")
        if number and tracking.is_short_number(number) and not phone_is_valid(cleaned.get("phone", "")):
            self.add_error("phone", "Indiquez le téléphone donné à la commande : il confirme que c'est bien la vôtre.")
        return cleaned
