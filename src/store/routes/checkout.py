from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..db import get_session
from ..fulfillment import (
    DEFAULT_FULFILLMENT_CODE,
    OPTIONS,
    FulfillmentAddressError,
    get_fulfillment_option,
)
from ..models import Order, OrderItem
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

    requested_method = request.args.get(
        "fulfillment_method",
        DEFAULT_FULFILLMENT_CODE,
    )

    selected = get_fulfillment_option(
        requested_method
    ) or get_fulfillment_option(DEFAULT_FULFILLMENT_CODE)

    subtotal = sum(line.line_total_cents for line in lines)

    return render_template(
        "checkout.html",
        lines=lines,
        subtotal_cents=subtotal,
        fulfillment_options=OPTIONS,
        selected_fulfillment=selected,
        shipping_cents=selected.calculate_fee(subtotal),
        total_cents=subtotal + selected.calculate_fee(subtotal),
    )


@bp.post("")
def place_order():
    db = get_session()
    lines = get_cart_lines(db)

    if not lines:
        flash("Your cart is empty.", "error")
        return redirect(url_for("cart.view_cart"))

    fulfillment_code = request.form.get(
        "fulfillment_method",
        DEFAULT_FULFILLMENT_CODE,
    )

    selected = get_fulfillment_option(fulfillment_code)

    if selected is None:
        flash("Please choose a valid fulfillment option.", "error")
        return redirect(url_for("checkout.checkout_form"))

    customer_name = request.form.get(
        "customer_name", ""
    ).strip()

    customer_email = request.form.get(
        "customer_email", ""
    ).strip()

    shipping_address = request.form.get(
        "shipping_address", ""
    ).strip()

    payment_token = request.form.get(
        "payment_token", ""
    ).strip()

    if not all([customer_name, customer_email, payment_token]):
        flash("Please complete all checkout fields.", "error")
        return redirect(
            url_for(
                "checkout.checkout_form",
                fulfillment_method=selected.code,
            )
        )

    try:
        shipping_address = selected.normalize_address(shipping_address)
    except FulfillmentAddressError as exc:
        flash(str(exc), "error")
        return redirect(
            url_for(
                "checkout.checkout_form",
                fulfillment_method=selected.code,
            )
        )

    for line in lines:
        if line.quantity > line.product.stock_quantity:
            flash(
                f"Not enough stock for {line.product.name}.",
                "error",
            )
            return redirect(url_for("cart.view_cart"))

    subtotal = sum(line.line_total_cents for line in lines)
    total = subtotal + selected.calculate_fee(subtotal)

    try:
        payment_reference = FakePaymentProcessor().charge(
            total,
            payment_token,
        )
    except PaymentDeclined:
        flash(
            "Payment was declined. Try a different test token.",
            "error",
        )
        return redirect(
            url_for(
                "checkout.checkout_form",
                fulfillment_method=selected.code,
            )
        )

    order = Order(
        customer_name=customer_name,
        customer_email=customer_email,
        shipping_address=shipping_address,
        fulfillment_method=selected.code,
        subtotal_cents=subtotal,
        shipping_cents=selected.calculate_fee(subtotal),
        total_cents=total,
        payment_reference=payment_reference,
        status="confirmed",
    )

    db.add(order)
    db.flush()

    for line in lines:
        order.items.append(
            OrderItem(
                product_id=line.product.id,
                sku=line.product.sku,
                product_name=line.product.name,
                unit_price_cents=line.product.price_cents,
                quantity=line.quantity,
            )
        )

        line.product.stock_quantity -= line.quantity

    db.commit()

    session["cart"] = {}

    flash("Order placed successfully.", "success")

    return redirect(
        url_for(
            "orders.order_detail",
            order_id=order.id,
        )
    )
