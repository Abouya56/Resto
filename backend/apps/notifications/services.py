from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.notifications.models import Notification
from apps.users.roles import Role


def notify_user(user, title, message, notif_type="info", url=""):
    if user is None:
        return None
    notification = Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notif_type=notif_type,
        url=url,
    )
    layer = get_channel_layer()
    if layer:
        async_to_sync(layer.group_send)(
            f"user_{user.id}",
            {
                "type": "notification.event",
                "id": notification.id,
                "title": title,
                "message": message,
                "notif_type": notif_type,
                "url": url,
            },
        )
    return notification


def notify_restaurant_staff(restaurant, title, message, notif_type="info", url="", roles=None):
    """`url` peut être une adresse, ou une fonction qui donne l'adresse selon le poste de la personne."""
    employees = restaurant.employees.filter(is_active=True)
    if roles:
        employees = employees.filter(role__in=roles)
    for employee in employees.select_related("user"):
        notify_user(employee.user, title, message, notif_type, url(employee.role) if callable(url) else url)


def notify_restaurant_managers(restaurant, title, message, notif_type="info", url=""):
    notify_restaurant_staff(restaurant, title, message, notif_type, url, roles=(Role.MANAGER,))
