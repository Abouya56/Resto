from django.urls import path

from apps.notifications.consumers import NotificationConsumer
from apps.orders.consumers import KitchenConsumer, OrderTrackingConsumer

websocket_urlpatterns = [
    path("ws/kitchen/<int:restaurant_id>/", KitchenConsumer.as_asgi()),
    path("ws/orders/<int:order_id>/", OrderTrackingConsumer.as_asgi()),
    path("ws/notifications/", NotificationConsumer.as_asgi()),
]
