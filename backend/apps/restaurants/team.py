"""Équipe d'un restaurant : un seul compte réception ; le compte gérant est donné par la plateforme."""

from apps.restaurants.models import Employee
from apps.users.roles import Role

RECEPTION_LIMIT_MESSAGE = (
    "Votre restaurant a déjà son compte réception. Modifiez-le, ou retirez-le de l'équipe avant d'en créer un autre."
)
MANAGER_CREATION_MESSAGE = "Les comptes gérant sont donnés par la plateforme : vous ne pouvez pas en créer."


def reception_slot_taken(restaurant, exclude_pk=None):
    """Vrai si le restaurant a déjà un compte réception (actif ou suspendu)."""
    accounts = Employee.objects.filter(restaurant=restaurant, role=Role.RECEPTION)
    if exclude_pk:
        accounts = accounts.exclude(pk=exclude_pk)
    return accounts.exists()
