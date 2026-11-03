from rest_framework import serializers

from apps.orders.models import Cart, CartItem, Order, OrderItem


class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ("id", "product", "product_name", "quantity", "note", "unit_price", "subtotal")


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    delivery_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Cart
        fields = (
            "id",
            "restaurant",
            "table",
            "order_type",
            "note",
            "items",
            "subtotal",
            "delivery_fee",
            "total",
        )


class AddCartItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)
    note = serializers.CharField(required=False, allow_blank=True)


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ("id", "product", "product_name", "quantity", "unit_price", "subtotal", "note")


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)
    short_number = serializers.CharField(read_only=True)
    reference = serializers.CharField(read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "number",
            "short_number",
            "reference",
            "restaurant",
            "restaurant_name",
            "customer",
            "table",
            "order_type",
            "status",
            "subtotal",
            "delivery_fee",
            "total",
            "note",
            "customer_first_name",
            "customer_last_name",
            "customer_phone",
            "customer_email",
            "delivery_address_text",
            "delivery_city",
            "delivery_district",
            "delivery_landmark",
            "latitude",
            "longitude",
            "items",
            "created_at",
            "accepted_at",
            "ready_at",
            "completed_at",
        )
        read_only_fields = fields


class CheckoutSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    address_text = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(required=False, allow_blank=True)
    district = serializers.CharField(required=False, allow_blank=True)
    landmark = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.DecimalField(required=False, allow_null=True, max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(required=False, allow_null=True, max_digits=9, decimal_places=6)
    note = serializers.CharField(required=False, allow_blank=True)


class StatusSerializer(serializers.Serializer):
    status = serializers.CharField()
    reason = serializers.CharField(required=False, allow_blank=True)
