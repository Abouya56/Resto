import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.menus.models import Product
from apps.orders.models import (
    STATUS_FLOW,
    Cart,
    CartItem,
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
)
from apps.restaurants.models import RestaurantStatus


def _cart_owner_filters(request):
    if request.user.is_authenticated:
        return {"user": request.user}
    return {"session_key": request.session.session_key or "", "user__isnull": True}


def find_cart(request, restaurant):
    if not request.user.is_authenticated and not request.session.session_key:
        return None
    return Cart.objects.filter(restaurant=restaurant, **_cart_owner_filters(request)).first()


def owned_cart_item(request, pk):
    if not request.user.is_authenticated and not request.session.session_key:
        return None
    owner = {f"cart__{key}": value for key, value in _cart_owner_filters(request).items()}
    return CartItem.objects.select_related("cart").filter(pk=pk, **owner).first()


def get_or_create_cart(request, restaurant, table=None, order_type=None):
    if not request.session.session_key:
        request.session.create()
    filters = {"restaurant": restaurant, **_cart_owner_filters(request)}
    cart = Cart.objects.filter(**filters).first()
    if cart is None:
        cart = Cart.objects.create(
            restaurant=restaurant,
            table=table,
            order_type=order_type or (OrderType.DINE_IN if table else OrderType.TAKEAWAY),
            user=request.user if request.user.is_authenticated else None,
            session_key="" if request.user.is_authenticated else request.session.session_key,
        )
    else:
        updated = False
        if table and cart.table_id != table.pk:
            cart.table = table
            updated = True
        if order_type and cart.order_type != order_type:
            cart.order_type = order_type
            updated = True
        if not table and cart.table_id and cart.order_type != OrderType.DINE_IN:
            cart.table = None
            updated = True
        if updated:
            cart.save(update_fields=["table", "order_type", "updated_at"])
    return cart


def add_to_cart(cart, product, quantity=1, note=""):
    if product.restaurant_id != cart.restaurant_id:
        raise ValidationError("Ce produit n'appartient pas à ce restaurant.")
    if not product.can_be_ordered:
        raise ValidationError(
            f"{product.name} est épuisé pour le moment." if product.sold_out else "Ce produit n'est plus disponible."
        )
    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={"quantity": quantity, "note": note},
    )
    if not created:
        item.quantity += quantity
        if note:
            item.note = note
        item.save()
    return item


def update_cart_item(item, quantity=None, note=None):
    if quantity is not None:
        if quantity < 1:
            item.delete()
            return None
        item.quantity = quantity
    if note is not None:
        item.note = note
    item.save()
    return item


def phone_is_valid(phone):
    return len([character for character in phone or "" if character.isdigit()]) >= 8


def _resolve_contact(customer, contact, order_type):
    contact = contact or {}
    first_name = (contact.get("first_name") or "").strip()
    last_name = (contact.get("last_name") or "").strip()
    phone = (contact.get("phone") or "").strip()
    email = (contact.get("email") or "").strip()
    if customer:
        first_name = first_name or customer.first_name
        last_name = last_name or customer.last_name
        phone = phone or customer.phone
        email = email or customer.email
    if order_type == OrderType.PREORDER:
        if not first_name:
            raise ValidationError("Indiquez votre nom.")
        if not phone_is_valid(phone):
            raise ValidationError("Indiquez un numéro de téléphone joignable.")
    elif order_type == OrderType.DELIVERY:
        if not first_name or not last_name:
            raise ValidationError("Indiquez votre prénom et votre nom.")
        if not phone_is_valid(phone):
            raise ValidationError("Indiquez un numéro de téléphone joignable.")
    else:
        # Sur place ou à emporter, le client est là : son nom suffit.
        if not first_name:
            raise ValidationError("Indiquez votre nom.")
        if phone and not phone_is_valid(phone):
            raise ValidationError("Ce numéro de téléphone n'est pas valide.")
    return {
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "email": email,
        "city": (contact.get("city") or "").strip(),
        "district": (contact.get("district") or "").strip(),
        "landmark": (contact.get("landmark") or "").strip(),
        "latitude": contact.get("latitude"),
        "longitude": contact.get("longitude"),
    }


@transaction.atomic
def checkout_cart(cart, customer=None, address_text="", note="", contact=None, scheduled_for=None, arrival_at=None):
    items = list(cart.items.select_related("product"))
    if not items:
        raise ValidationError("Le panier est vide.")
    restaurant = cart.restaurant
    if restaurant.status != RestaurantStatus.ACTIVE or not restaurant.is_accepting_orders:
        raise ValidationError("Ce restaurant n'accepte plus de commandes.")

    resolved = _resolve_contact(customer, contact, cart.order_type)
    if cart.order_type == OrderType.DINE_IN and not cart.table_id:
        raise ValidationError("Une table est obligatoire pour une commande sur place.")
    if cart.order_type == OrderType.PREORDER and not arrival_at:
        raise ValidationError("Indiquez dans combien de temps vous arrivez.")
    if cart.order_type == OrderType.DELIVERY:
        if not address_text:
            raise ValidationError("Une adresse de livraison est obligatoire.")
        if not resolved["district"]:
            raise ValidationError("Indiquez le secteur de livraison.")

    subtotal = Decimal("0.00")
    prepared_items = []
    for item in items:
        product = Product.objects.select_for_update().get(pk=item.product_id)
        if product.restaurant_id != restaurant.id:
            raise ValidationError("Produit invalide pour ce restaurant.")
        if not product.can_be_ordered:
            raise ValidationError(f"{product.name} n'est plus disponible.")
        line_subtotal = product.price * item.quantity
        subtotal += line_subtotal
        prepared_items.append((product, item.quantity, product.price, line_subtotal, item.note))

    delivery_fee = restaurant.delivery_fee if cart.order_type == OrderType.DELIVERY else Decimal("0.00")
    if cart.order_type == OrderType.DELIVERY and subtotal < restaurant.min_delivery_amount:
        raise ValidationError("Le montant minimum de livraison n'est pas atteint.")

    order = Order.objects.create(
        restaurant=restaurant,
        customer=customer,
        table=cart.table if cart.order_type == OrderType.DINE_IN else None,
        order_type=cart.order_type,
        status=OrderStatus.PENDING,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        total=subtotal + delivery_fee,
        note=note or cart.note,
        scheduled_for=scheduled_for if cart.order_type == OrderType.DELIVERY else None,
        arrival_at=arrival_at if cart.order_type == OrderType.PREORDER else None,
        delivery_address_text=address_text,
        delivery_city=resolved["city"],
        delivery_district=resolved["district"],
        delivery_landmark=resolved["landmark"],
        latitude=resolved["latitude"],
        longitude=resolved["longitude"],
        customer_first_name=resolved["first_name"],
        customer_last_name=resolved["last_name"],
        customer_phone=resolved["phone"],
        customer_email=resolved["email"] or "",
    )
    OrderItem.objects.bulk_create(
        [
            OrderItem(
                order=order,
                product=product,
                product_name=product.name,
                quantity=quantity,
                unit_price=unit_price,
                subtotal=line_subtotal,
                note=item_note,
            )
            for product, quantity, unit_price, line_subtotal, item_note in prepared_items
        ]
    )
    cart.items.all().delete()
    return order


MAX_SALE_QUANTITY = 99


@transaction.atomic
def record_counter_sale(restaurant, lines, method, user=None, customer_name=""):
    """Vente au comptoir : la réception sert un client qui n'a pas commandé sur le site.

    `lines` : liste de (id du plat, quantité). La commande naît terminée et payée ; `method` vaut « cash » ou « mobile ».
    """
    from apps.inventory.services import consume_order
    from apps.payments.models import Payment, PaymentMethod, PaymentStatus

    if restaurant.status != RestaurantStatus.ACTIVE:
        raise ValidationError("Ce restaurant n'est pas actif.")
    if method not in ("cash", "mobile"):
        raise ValidationError("Choisissez comment le client a payé : espèces ou mobile.")
    wanted = {}
    for product_id, quantity in lines:
        if quantity > 0:
            wanted[product_id] = wanted.get(product_id, 0) + quantity
    if not wanted:
        raise ValidationError("Choisissez au moins un plat.")
    products = {p.pk: p for p in Product.objects.filter(pk__in=wanted, restaurant=restaurant)}
    subtotal = Decimal("0.00")
    prepared = []
    for product_id, quantity in wanted.items():
        product = products.get(product_id)
        if product is None:
            raise ValidationError("Plat introuvable pour ce restaurant.")
        if quantity > MAX_SALE_QUANTITY:
            raise ValidationError(f"{product.name} : {MAX_SALE_QUANTITY} au maximum par vente.")
        if not product.can_be_ordered:
            raise ValidationError(f"{product.name} n'est pas disponible.")
        line_total = product.price * quantity
        subtotal += line_total
        prepared.append((product, quantity, line_total))
    now = timezone.now()
    order = Order.objects.create(
        restaurant=restaurant,
        order_type=OrderType.COUNTER,
        status=OrderStatus.COMPLETED,
        subtotal=subtotal,
        total=subtotal,
        customer_first_name=(customer_name or "").strip()[:150],
        accepted_at=now,
        ready_at=now,
        completed_at=now,
    )
    OrderItem.objects.bulk_create(
        [
            OrderItem(
                order=order,
                product=product,
                product_name=product.name,
                quantity=quantity,
                unit_price=product.price,
                subtotal=line_total,
            )
            for product, quantity, line_total in prepared
        ]
    )
    Payment.objects.create(
        order=order,
        amount=order.total,
        method=PaymentMethod.MOBILE_MONEY if method == "mobile" else PaymentMethod.CASH_ON_SITE,
        status=PaymentStatus.PAID,
        reference=f"CASH-{uuid.uuid4().hex[:12].upper()}",
        provider="cash",
        paid_at=now,
    )
    consume_order(order, user)
    return order


# Statuts où l'argent liquide a forcément été remis : on solde alors le paiement.
CASH_COLLECTED_STATUSES = (OrderStatus.DELIVERED, OrderStatus.PICKED_UP, OrderStatus.COMPLETED)


@transaction.atomic
def transition_order(order, new_status, user=None, reason="", payment_method=None):
    """Fait avancer une commande. On peut sauter des étapes : le personnel n'a pas à valider chaque palier.

    `payment_method` (« cash » ou « mobile ») dit comment l'argent a été reçu quand la commande est soldée.
    """
    if new_status == OrderStatus.CANCELLED:
        if not order.can_cancel():
            raise ValidationError("Cette commande ne peut plus être annulée.")
        order.status = OrderStatus.CANCELLED
        order.cancelled_at = timezone.now()
        if reason:
            order.cancellation_reason = reason
        order.save(update_fields=["status", "cancelled_at", "cancellation_reason", "updated_at"])
        return order

    flow = STATUS_FLOW[order.order_type]
    if order.status not in flow:
        raise ValidationError("Statut actuel incompatible.")
    current_index = flow.index(order.status)
    if new_status not in flow:
        raise ValidationError("Statut incompatible avec ce type de commande.")
    next_index = flow.index(new_status)
    if next_index <= current_index:
        raise ValidationError("Transition de statut non autorisée.")
    if order.status == OrderStatus.PENDING and new_status != OrderStatus.ACCEPTED:
        # Accepter d'abord : on ne sert ni n'encaisse une commande que personne n'a prise en charge.
        raise ValidationError("Acceptez d'abord la commande.")

    order.status = new_status
    now = timezone.now()
    # Les étapes sautées sont datées au même instant : les statistiques gardent leurs repères.
    if not order.accepted_at:
        order.accepted_at = now
    if not order.ready_at and next_index >= flow.index(OrderStatus.READY):
        order.ready_at = now
    if new_status == OrderStatus.COMPLETED:
        order.completed_at = now
    order.save()
    if next_index >= flow.index(OrderStatus.PREPARING):
        from apps.inventory.services import consume_order

        consume_order(order, user)
    if new_status in CASH_COLLECTED_STATUSES:
        from apps.payments.services import mark_order_paid

        mark_order_paid(order, method=payment_method, only_cash=payment_method is None)
    return order
