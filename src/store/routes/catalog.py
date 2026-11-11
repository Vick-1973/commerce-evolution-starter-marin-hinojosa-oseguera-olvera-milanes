from flask import Blueprint, abort, current_app, render_template
from sqlalchemy import select

from ..db import get_session
from ..models import Product

bp = Blueprint("catalog", __name__)


@bp.get("/")
def catalog():
    db = get_session()
    products = db.scalars(
        select(Product).where(Product.active == 1).order_by(Product.name)
    ).all()
    return render_template(
        "catalog.html",
        products=products,
        store_name=current_app.config["STORE_NAME"],
    )


@bp.get("/products/<int:product_id>")
def product_detail(product_id: int):
    product = get_session().get(Product, product_id)
    if product is None or not product.active:
        abort(404)
    return render_template("product.html", product=product)
