from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.core.tenancy import user_can_access_restaurant
from apps.orders import tracking
from apps.orders.models import Order


class KitchenConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        restaurant_id = int(self.scope["url_route"]["kwargs"]["restaurant_id"])
        if user.is_anonymous or not await self._can_access(user, restaurant_id):
            await self.close()
            return
        self.group_name = f"kitchen_{restaurant_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def order_event(self, event):
        await self.send_json(event)

    @database_sync_to_async
    def _can_access(self, user, restaurant_id):
        return user_can_access_restaurant(user, restaurant_id)


class OrderTrackingConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        order_id = int(self.scope["url_route"]["kwargs"]["order_id"])
        guest_allowed = tracking.can_view(self.scope.get("session"), order_id)
        allowed = await self._can_track(user, order_id, guest_allowed)
        if not allowed:
            await self.close()
            return
        self.group_name = f"order_{order_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def order_event(self, event):
        await self.send_json(event)

    @database_sync_to_async
    def _can_track(self, user, order_id, guest_allowed=False):
        if guest_allowed:
            return Order.objects.filter(pk=order_id).exists()
        try:
            order = Order.objects.select_related("restaurant").get(pk=order_id)
        except Order.DoesNotExist:
            return False
        if user.is_authenticated and (
            order.customer_id == user.id or user_can_access_restaurant(user, order.restaurant)
        ):
            return True
        return False
