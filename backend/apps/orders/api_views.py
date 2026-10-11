from django.core.exceptions import ValidationError
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api import CurrentRestaurantAPIMixin
from apps.core.permissions import IsRestaurantStaff, RestaurantQuerysetMixin
from apps.core.tenancy import is_platform_admin, user_can_access_restaurant
from apps.menus.models import Product
from apps.orders.models import Order, OrderStatus
from apps.orders.serializers import (
    AddCartItemSerializer,
    CartSerializer,
    CheckoutSerializer,
    OrderSerializer,
    StatusSerializer,
)
from apps.orders.services import (
    add_to_cart,
    checkout_cart,
    get_or_create_cart,
    transition_order,
    update_cart_item,
)
from apps.payments.models import PaymentMethod
from apps.payments.providers import get_payment_provider
from apps.users.models import CustomerAddress


class CartViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    def _cart(self, request):
        restaurant_id = request.query_params.get("restaurant") or request.data.get("restaurant")
        if not restaurant_id:
            return None
        from apps.restaurants.models import Restaurant, RestaurantStatus

        restaurant = Restaurant.objects.filter(pk=restaurant_id, status=RestaurantStatus.ACTIVE).first()
        if not restaurant:
            return None
        return get_or_create_cart(request, restaurant)

    def list(self, request):
        cart = self._cart(request)
        if cart is None:
            return Response({"detail": "restaurant requis."}, status=400)
        return Response(CartSerializer(cart).data)

    @action(detail=False, methods=["post"])
    def add(self, request):
        cart = self._cart(request)
        if cart is None:
            return Response({"detail": "restaurant requis."}, status=400)
        serializer = AddCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = Product.objects.filter(
            pk=serializer.validated_data["product_id"],
            restaurant=cart.restaurant,
        ).first()
        if not product:
            return Response({"detail": "Produit introuvable."}, status=404)
        try:
            add_to_cart(
                cart,
                product,
                serializer.validated_data["quantity"],
                serializer.validated_data.get("note", ""),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=400)
        return Response(CartSerializer(cart).data)

    @action(detail=False, methods=["post"])
    def update_item(self, request):
        cart = self._cart(request)
        if cart is None:
            return Response({"detail": "restaurant requis."}, status=400)
        item = cart.items.filter(pk=request.data.get("item_id")).first()
        if not item:
            return Response({"detail": "Ligne introuvable."}, status=404)
        quantity = request.data.get("quantity")
        if quantity is not None:
            try:
                quantity = int(quantity)
            except (TypeError, ValueError):
                return Response({"detail": "Quantité invalide."}, status=400)
        update_cart_item(item, quantity=quantity, note=request.data.get("note"))
        return Response(CartSerializer(cart).data)

    @action(detail=False, methods=["post"])
    def checkout(self, request):
        cart = self._cart(request)
        if cart is None:
            return Response({"detail": "restaurant requis."}, status=400)
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        address = None
        if serializer.validated_data.get("address_id") and request.user.is_authenticated:
            address = CustomerAddress.objects.filter(
                pk=serializer.validated_data["address_id"],
                customer=request.user,
            ).first()
        try:
            data = serializer.validated_data
            order = checkout_cart(
                cart,
                customer=request.user if request.user.is_authenticated else None,
                address=address,
                address_text=data.get("address_text", ""),
                note=data.get("note", ""),
                contact={
                    "first_name": data.get("first_name", ""),
                    "last_name": data.get("last_name", ""),
                    "phone": data.get("phone", ""),
                    "email": data.get("email", ""),
                    "city": data.get("city", ""),
                    "district": data.get("district", ""),
                    "landmark": data.get("landmark", ""),
                    "latitude": data.get("latitude"),
                    "longitude": data.get("longitude"),
                },
            )
            provider = get_payment_provider()
            method = serializer.validated_data.get("payment_method", PaymentMethod.SIMULATED)
            provider.charge(order, method=method)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=400)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderViewSet(CurrentRestaurantAPIMixin, RestaurantQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    queryset = Order.objects.select_related("restaurant", "customer", "table").prefetch_related("items")
    filterset_fields = ("status", "order_type", "restaurant")
    search_fields = ("number",)

    def get_permissions(self):
        if self.action in ("list", "retrieve", "mine"):
            return [permissions.IsAuthenticated()]
        return [IsRestaurantStaff()]

    def get_queryset(self):
        user = self.request.user
        qs = Order.objects.select_related("restaurant", "customer", "table").prefetch_related("items")
        if is_platform_admin(user):
            return qs
        if user.employments.filter(is_active=True).exists():
            return super().get_queryset()
        return qs.filter(customer=user)

    @action(detail=False, methods=["get"])
    def mine(self, request):
        qs = Order.objects.filter(customer=request.user).prefetch_related("items")
        page = self.paginate_queryset(qs)
        serializer = OrderSerializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[IsRestaurantStaff])
    def transition(self, request, pk=None):
        order = self.get_object()
        if not user_can_access_restaurant(request.user, order.restaurant):
            return Response({"detail": "Accès refusé."}, status=403)
        serializer = StatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            transition_order(
                order,
                serializer.validated_data["status"],
                request.user,
                reason=serializer.validated_data.get("reason", ""),
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=400)
        return Response(OrderSerializer(order).data)
