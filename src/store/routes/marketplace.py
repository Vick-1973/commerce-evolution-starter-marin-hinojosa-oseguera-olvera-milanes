"""Authenticated marketplace HTTP adapter; no duplicate checkout/payment logic.

Request JSON:
  {"external_order_id":"EXT-1001",
   "buyer":{"name":"Ada","email":"ada@example.com"},
   "shipping":{"method":"express_shipping","address":"Street 1"},
   "items":[{"sku":"BNV-LAP-014","quantity":1}]}

X-Marketplace-Key is a teaching-project integration key. Payment was already
processed externally and FakePaymentProcessor must never be invoked here.
"""
from __future__ import annotations

import hashlib
import hmac
import json

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..db import get_session
from ..fulfillment import (
    DEFAULT_FULFILLMENT_CODE, FulfillmentAddressError, get_fulfillment_option,
)
from ..models import Order
from ..ordering import (
    InsufficientStock, InvalidFulfillment, OrderingError, RequestedItem,
    UnknownProduct, prepare_order, save_order,
)

bp = Blueprint("marketplace", __name__, url_prefix="/api/marketplace")


class BadMarketplaceRequest(ValueError):
    pass


def _text(value: object, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise BadMarketplaceRequest(f"{name} must be a nonempty string (max {maximum}).")
    return value.strip()


def _parse_payload(body: object):
    if not isinstance(body, dict):
        raise BadMarketplaceRequest("A JSON object is required.")
    external_id = _text(body.get("external_order_id"), "external_order_id", 120)
    buyer = body.get("buyer")
    shipping = body.get("shipping")
    if not isinstance(buyer, dict) or not isinstance(shipping, dict):
        raise BadMarketplaceRequest("buyer and shipping must be objects.")
    name = _text(buyer.get("name"), "buyer.name", 120)
    email = _text(buyer.get("email"), "buyer.email", 160)
    if "@" not in email:
        raise BadMarketplaceRequest("buyer.email must contain @.")
    method = shipping.get("method", DEFAULT_FULFILLMENT_CODE)
    if not isinstance(method, str):
        raise BadMarketplaceRequest("shipping.method must be a string.")
    option = get_fulfillment_option(method)
    if option is None:
        raise BadMarketplaceRequest("Unknown fulfillment method.")
    address = shipping.get("address", "")
    if not isinstance(address, str) or len(address) > 2000:
        raise BadMarketplaceRequest("shipping.address must be a string (max 2000).")
    try:
        address = option.normalize_address(address)
    except FulfillmentAddressError as exc:
        raise BadMarketplaceRequest(str(exc)) from exc
    raw_items = body.get("items")
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= 50:
        raise BadMarketplaceRequest("items must contain between 1 and 50 lines.")
    items: list[RequestedItem] = []
    combined: dict[str, int] = {}
    for i, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise BadMarketplaceRequest(f"items[{i}] must be an object.")
        sku = _text(item.get("sku"), f"items[{i}].sku", 40)
        quantity = item.get("quantity")
        if (not isinstance(quantity, int) or isinstance(quantity, bool)
                or not 1 <= quantity <= 10_000):
            raise BadMarketplaceRequest(f"items[{i}].quantity must be a positive integer.")
        combined[sku] = combined.get(sku, 0) + quantity
    if any(q > 10_000 for q in combined.values()):
        raise BadMarketplaceRequest("Total quantity per SKU cannot exceed 10000.")
    items = [RequestedItem(sku, quantity) for sku, quantity in sorted(combined.items())]

    # Store a fingerprint of the normalized business payload. Reordered SKU
    # lines and irrelevant pickup addresses do not cause false conflicts.
    canonical = {
        "external_order_id": external_id,
        "buyer": {"name": name, "email": email},
        "shipping": {"method": method, "address": address},
        "items": [{"sku": item.sku, "quantity": item.quantity} for item in items],
    }
    payload_hash = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return external_id, name, email, method, address, items, payload_hash


def _find_existing(external_id: str) -> Order | None:
    return get_session().scalar(
        select(Order).where(Order.source == "marketplace", Order.external_order_id == external_id)
    )


def _existing_response(existing: Order, fingerprint: str):
    if existing.external_payload_hash != fingerprint:
        return jsonify(error="External order ID already exists with different order details."), 409
    return jsonify(_as_json(existing, replayed=True)), 200


def _as_json(order: Order, *, replayed: bool) -> dict:
    return {
        "order_id": order.id,
        "source": order.source,
        "external_order_id": order.external_order_id,
        "status": order.status,
        "fulfillment_method": order.fulfillment_method,
        "shipping_cents": order.shipping_cents,
        "subtotal_cents": order.subtotal_cents,
        "total_cents": order.total_cents,
        "replayed": replayed,
    }


@bp.post("/orders")
def receive_order():
    api_key = current_app.config.get("MARKETPLACE_API_KEY", "")
    if not api_key:
        return jsonify(error="Marketplace API is not configured."), 503
    supplied = request.headers.get("X-Marketplace-Key", "")
    if not hmac.compare_digest(supplied, api_key):
        return jsonify(error="Invalid marketplace API key."), 401
    if not request.is_json:
        return jsonify(error="Content-Type must be application/json."), 415
    try:
        external_id, name, email, method, address, items, fingerprint = _parse_payload(
            request.get_json(silent=True)
        )
    except BadMarketplaceRequest as exc:
        return jsonify(error=str(exc)), 400

    db = get_session()
    existing = _find_existing(external_id)
    if existing is not None:
        return _existing_response(existing, fingerprint)

    try:
        quote = prepare_order(db, items, method, address)
    except (InvalidFulfillment, FulfillmentAddressError, OrderingError) as exc:
        # A competing request might have created the order after the first lookup.
        existing = _find_existing(external_id)
        if existing is not None:
            return _existing_response(existing, fingerprint)
        status = 404 if isinstance(exc, UnknownProduct) else (
            409 if isinstance(exc, InsufficientStock) else 400
        )
        return jsonify(error=str(exc)), status

    # Marketplace attests that payment is complete. Generate a local audit
    # reference; DO NOT call the storefront payment processor.
    paid_reference = f"marketplace_paid_{hashlib.sha256(external_id.encode()).hexdigest()[:24]}"
    try:
        order = save_order(
            db, quote, customer_name=name, customer_email=email,
            payment_reference=paid_reference, source="marketplace",
            external_order_id=external_id, external_payload_hash=fingerprint,
        )
    except IntegrityError:
        # The database unique index, not a pre-check, is the concurrency guard.
        db.rollback()
        existing = _find_existing(external_id)
        if existing is not None:
            return _existing_response(existing, fingerprint)
        raise
    except InsufficientStock as exc:
        existing = _find_existing(external_id)
        if existing is not None:
            return _existing_response(existing, fingerprint)
        return jsonify(error=str(exc)), 409
    return jsonify(_as_json(order, replayed=False)), 201
