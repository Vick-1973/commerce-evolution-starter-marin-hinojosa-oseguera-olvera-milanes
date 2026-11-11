from __future__ import annotations

from dataclasses import dataclass

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Product

bp = Blueprint("cart", __name__, url_prefix="/cart")


@dataclass
class CartLine:
    product: Product
    quantity: int

    @property
    def line_total_cents(self) -> int:
        return self.product.price_cents * self.quantity


def _raw_cart() -> dict[str, int]:
    return session.setdefault("cart", {})


def get_cart_lines(db: Session) -> list[CartLine]:
    lines: list[CartLine] = []
    for product_id, quantity in _raw_cart().items():
        product = db.get(Product, int(product_id))
        if product is not None and product.active and quantity > 0:
            lines.append(CartLine(product=product, quantity=int(quantity)))
    return lines


@bp.get("")
def view_cart():
    lines = get_cart_lines(get_session())
    subtotal = sum(line.line_total_cents for line in lines)
    return render_template("cart.html", lines=lines, subtotal_cents=subtotal)


@bp.post("/add/<int:product_id>")
def add(product_id: int):
    product = get_session().get(Product, product_id)
    if product is None or not product.active:
        flash("Product not found.", "error")
        return redirect(url_for("catalog.catalog"))

    cart = _raw_cart()
    key = str(product_id)
    cart[key] = int(cart.get(key, 0)) + 1
    session.modified = True
    flash(f"Added {product.name} to your cart.", "success")
    return redirect(request.referrer or url_for("catalog.catalog"))


@bp.post("/update/<int:product_id>")
def update(product_id: int):
    cart = _raw_cart()
    quantity = max(0, int(request.form.get("quantity", "1")))
    key = str(product_id)
    if quantity == 0:
        cart.pop(key, None)
    else:
        cart[key] = quantity
    session.modified = True
    return redirect(url_for("cart.view_cart"))


@bp.post("/remove/<int:product_id>")
def remove(product_id: int):
    _raw_cart().pop(str(product_id), None)
    session.modified = True
    return redirect(url_for("cart.view_cart"))
