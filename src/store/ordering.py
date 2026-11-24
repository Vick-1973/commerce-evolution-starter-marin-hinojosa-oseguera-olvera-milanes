"""Shared ordering core for storefront and paid marketplace requests.

The entry points handle transport and their own payment contract. This module
owns authoritative product pricing, fulfillment rules, inventory reservation and
persistence. It must not import Flask, web sessions, or the payment provider.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .fulfillment import FulfillmentAddressError, FulfillmentOption, get_fulfillment_option
from .models import Order, OrderItem, Product


class OrderingError(ValueError):
    """Invalid order request; no data should be committed."""


class InvalidFulfillment(OrderingError):
    pass


class UnknownProduct(OrderingError):
    pass


class InsufficientStock(OrderingError):
    pass


@dataclass(frozen=True)
class RequestedItem:
    sku: str
    quantity: int


@dataclass(frozen=True)
class PricedLine:
    product: Product
    quantity: int

    @property
    def line_total_cents(self) -> int:
        return self.product.price_cents * self.quantity


@dataclass(frozen=True)
class OrderQuote:
    lines: tuple[PricedLine, ...]
    fulfillment: FulfillmentOption
    shipping_address: str
    subtotal_cents: int
    shipping_cents: int
    total_cents: int


def prepare_order(
    db: Session, items: list[RequestedItem], fulfillment_code: str, shipping_address: str,
) -> OrderQuote:
    """Validate items once and price using authoritative database and Strategy."""
    fulfillment = get_fulfillment_option(fulfillment_code)
    if fulfillment is None:
        raise InvalidFulfillment("Please choose a valid fulfillment option.")
    address = fulfillment.normalize_address(shipping_address)
    if not items:
        raise OrderingError("At least one order item is required.")

    normalized: dict[str, int] = {}
    for item in items:
        if (not isinstance(item.sku, str) or not item.sku.strip()
                or not isinstance(item.quantity, int) or isinstance(item.quantity, bool)
                or item.quantity <= 0):
            raise OrderingError("Each item needs a SKU and a positive integer quantity.")
        sku = item.sku.strip()
        normalized[sku] = normalized.get(sku, 0) + item.quantity

    products = {
        product.sku: product
        for product in db.scalars(select(Product).where(Product.sku.in_(normalized))).all()
    }
    lines = []
    for sku, quantity in normalized.items():
        product = products.get(sku)
        if product is None or not product.active:
            raise UnknownProduct(f"Product with SKU {sku} is unavailable.")
        if quantity > product.stock_quantity:
            raise InsufficientStock(f"Not enough stock for {product.name}.")
        lines.append(PricedLine(product=product, quantity=quantity))
    subtotal = sum(line.line_total_cents for line in lines)
    fee = fulfillment.calculate_fee(subtotal)
    return OrderQuote(tuple(lines), fulfillment, address, subtotal, fee, subtotal + fee)


def save_order(
    db: Session, quote: OrderQuote, *, customer_name: str, customer_email: str,
    payment_reference: str, source: str = "storefront",
    external_order_id: str | None = None, external_payload_hash: str | None = None,
) -> Order:
    """Save a complete order and adjust inventory in one DB transaction.

    A conditional UPDATE guards against stock changes after the initial quote.
    The caller owns payment: marketplace must never invoke a payment processor.
    """
    order = Order(
        source=source,
        external_order_id=external_order_id,
        external_payload_hash=external_payload_hash,
        customer_name=customer_name,
        customer_email=customer_email,
        shipping_address=quote.shipping_address,
        fulfillment_method=quote.fulfillment.code,
        subtotal_cents=quote.subtotal_cents,
        shipping_cents=quote.shipping_cents,
        total_cents=quote.total_cents,
        payment_reference=payment_reference,
        status="confirmed",
    )
    try:
        db.add(order)
        db.flush()
        for line in quote.lines:
            result = db.execute(
                update(Product)
                .where(Product.id == line.product.id, Product.active == 1,
                       Product.stock_quantity >= line.quantity)
                .values(stock_quantity=Product.stock_quantity - line.quantity)
            )
            if result.rowcount != 1:
                raise InsufficientStock(f"Not enough stock for {line.product.name}.")
            order.items.append(OrderItem(
                product_id=line.product.id,
                sku=line.product.sku,
                product_name=line.product.name,
                unit_price_cents=line.product.price_cents,
                quantity=line.quantity,
            ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return order
