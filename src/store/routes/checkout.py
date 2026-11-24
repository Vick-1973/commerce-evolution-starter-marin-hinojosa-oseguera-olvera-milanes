from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..db import get_session
from ..fulfillment import DEFAULT_FULFILLMENT_CODE, OPTIONS, get_fulfillment_option
from ..ordering import (
    InsufficientStock, InvalidFulfillment, OrderingError, RequestedItem, prepare_order,
    save_order,
)
from ..fulfillment import FulfillmentAddressError
from ..payments import FakePaymentProcessor, PaymentDeclined
from .cart import get_cart_lines

bp = Blueprint("checkout", __name__, url_prefix="/checkout")


@bp.get("")
def checkout_form():
    db = get_session()
    lines = get_cart_lines(db)
    if not lines:
        flash("Your cart is empty.", "error")
        return redirect(url_for("cart.view_cart"))

    requested_method = request.args.get("fulfillment_method", DEFAULT_FULFILLMENT_CODE)
    selected = get_fulfillment_option(requested_method) or get_fulfillment_option(
        DEFAULT_FULFILLMENT_CODE
    )
    subtotal = sum(line.line_total_cents for line in lines)
    fee = selected.calculate_fee(subtotal)
    return render_template(
        "checkout.html",
        lines=lines,
        subtotal_cents=subtotal,
        fulfillment_options=OPTIONS,
        selected_fulfillment=selected,
        shipping_cents=fee,
        total_cents=subtotal + fee,
    )


@bp.post("")
def place_order():
    db = get_session()
    lines = get_cart_lines(db)
    if not lines:
        flash("Your cart is empty.", "error")
        return redirect(url_for("cart.view_cart"))

    fulfillment_code = request.form.get("fulfillment_method", DEFAULT_FULFILLMENT_CODE)
    customer_name = request.form.get("customer_name", "").strip()
    customer_email = request.form.get("customer_email", "").strip()
    shipping_address = request.form.get("shipping_address", "").strip()
    payment_token = request.form.get("payment_token", "").strip()

    if not all([customer_name, customer_email, payment_token]):
        flash("Please complete all checkout fields.", "error")
        return redirect(url_for("checkout.checkout_form", fulfillment_method=fulfillment_code))

    try:
        quote = prepare_order(
            db,
            [RequestedItem(line.product.sku, line.quantity) for line in lines],
            fulfillment_code,
            shipping_address,
        )
    except InsufficientStock as exc:
        flash(str(exc), "error")
        return redirect(url_for("cart.view_cart"))
    except (InvalidFulfillment, OrderingError, FulfillmentAddressError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("checkout.checkout_form", fulfillment_method=fulfillment_code))

    try:
        payment_reference = FakePaymentProcessor().charge(quote.total_cents, payment_token)
    except PaymentDeclined:
        flash("Payment was declined. Try a different test token.", "error")
        return redirect(url_for("checkout.checkout_form", fulfillment_method=fulfillment_code))

    try:
        order = save_order(
            db, quote, customer_name=customer_name, customer_email=customer_email,
            payment_reference=payment_reference,
        )
    except InsufficientStock as exc:
        flash(str(exc), "error")
        return redirect(url_for("cart.view_cart"))

    session["cart"] = {}
    flash("Order placed successfully.", "success")
    return redirect(url_for("orders.order_detail", order_id=order.id))
