from flask import Blueprint, abort, render_template
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..db import get_session
from ..models import Order

bp = Blueprint("orders", __name__, url_prefix="/orders")


@bp.get("")
def order_history():
    db = get_session()
    orders = db.scalars(select(Order).order_by(Order.created_at.desc())).all()
    return render_template("orders.html", orders=orders)


@bp.get("/<int:order_id>")
def order_detail(order_id: int):
    db = get_session()
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items))
    )
    if order is None:
        abort(404)
    return render_template("order_confirmation.html", order=order)
