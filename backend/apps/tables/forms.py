from django import forms

from apps.core.forms import RestaurantScopedFormMixin, style_form
from apps.tables.models import DiningTable


class DiningTableForm(RestaurantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = DiningTable
        # « status » n'est pas proposé : l'état d'une table se calcule tout seul d'après ses commandes.
        fields = ("number", "capacity", "is_active")
        labels = {
            "number": "Numéro ou nom de la table",
            "capacity": "Nombre de places",
            "is_active": "Table utilisée",
        }
        help_texts = {
            "number": "Ex. 4, ou un nom comme « Terrasse 2 ». C'est ce qui est écrit sur le QR code.",
            "is_active": "Décochez pour retirer la table sans perdre son historique. Son QR code ne marchera plus.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form(self)
        self.fields["capacity"].widget.attrs.update({"min": 1, "max": 50})
