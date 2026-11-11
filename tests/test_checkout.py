from sqlalchemy import func, select

from store.db import get_session
from store.models import Order, Product


def _checkout(client, product_id, token="tok_success", quantity=1):
    client.post(f"/cart/add/{product_id}")
    if quantity != 1:
        client.post(f"/cart/update/{product_id}", data={"quantity": str(quantity)})
    return client.post(
        "/checkout",
        data={
            "customer_name": "Ada Lovelace",
            "customer_email": "ada@example.com",
            "shipping_address": "123 Analytical Engine Way",
            "payment_token": token,
        },
        follow_redirects=True,
    )


def test_checkout_happy_path_creates_order(client, app, first_product_id):
    response = _checkout(client, first_product_id)
    assert response.status_code == 200
    assert b"Order #1" in response.data
    with app.app_context():
        assert get_session().scalar(select(func.count()).select_from(Order)) == 1


def test_checkout_persists_order_items(client, app, first_product_id):
    _checkout(client, first_product_id, quantity=2)
    with app.app_context():
        order = get_session().scalar(select(Order))
        assert len(order.items) == 1
        assert order.items[0].quantity == 2
        assert order.items[0].unit_price_cents == 10000


def test_checkout_decreases_inventory(client, app, first_product_id):
    _checkout(client, first_product_id, quantity=2)
    with app.app_context():
        product = get_session().get(Product, first_product_id)
        assert product.stock_quantity == 3


def test_insufficient_inventory_is_rejected(client, app, first_product_id):
    response = _checkout(client, first_product_id, quantity=8)
    assert b"Not enough stock" in response.data
    with app.app_context():
        assert get_session().scalar(select(func.count()).select_from(Order)) == 0
        assert get_session().get(Product, first_product_id).stock_quantity == 5


def test_payment_failure_does_not_create_order(client, app, first_product_id):
    response = _checkout(client, first_product_id, token="tok_fail")
    assert b"Payment was declined" in response.data
    with app.app_context():
        assert get_session().scalar(select(func.count()).select_from(Order)) == 0
        assert get_session().get(Product, first_product_id).stock_quantity == 5


def test_order_history_displays_persisted_order(client, first_product_id):
    _checkout(client, first_product_id)
    response = client.get("/orders")
    assert response.status_code == 200
    assert b"Order #1" in response.data
    assert b"Ada Lovelace" in response.data
