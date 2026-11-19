"""Focused M2 tests: fulfillment rules, checkout integration, and migration."""
from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import select

from store import create_app
from store.db import get_session
from store.fulfillment import DEFAULT_FULFILLMENT_CODE, OPTIONS, get_fulfillment_option
from store.models import Order, Product


def buy(client, product_id, *, method="standard_shipping", address="123 Test St", token="tok_success", extra=None):
    client.post(f"/cart/add/{product_id}")
    data = {
        "customer_name": "Ada Lovelace",
        "customer_email": "ada@example.com",
        "shipping_address": address,
        "payment_token": token,
        "fulfillment_method": method,
    }
    if extra:
        data.update(extra)
    return client.post("/checkout", data=data, follow_redirects=True)


def test_available_fulfillment_options_are_data_driven():
    assert [(o.code, o.fee_cents, o.requires_address) for o in OPTIONS] == [
        ("standard_shipping", 9900, True),
        ("express_shipping", 19900, True),
        ("store_pickup", 0, False),
    ]
    assert DEFAULT_FULFILLMENT_CODE == "standard_shipping"
    assert get_fulfillment_option("forged") is None


def test_checkout_form_shows_all_options_and_initial_total(client, first_product_id):
    client.post(f"/cart/add/{first_product_id}")
    response = client.get("/checkout")
    assert response.status_code == 200
    for label in [b"Standard Shipping", b"Express Shipping", b"Store Pickup"]:
        assert label in response.data
    assert b'data-subtotal-cents="10000"' in response.data
    assert b"$199.00" in response.data  # subtotal 100 + standard 99


@pytest.mark.parametrize(
    ("method", "fee", "total", "address"),
    [
        ("standard_shipping", 9900, 19900, "123 Test St"),
        ("express_shipping", 19900, 29900, "123 Test St"),
        ("store_pickup", 0, 10000, ""),
    ],
)
def test_all_fulfillment_methods_create_correct_persisted_orders(
    client, app, first_product_id, method, fee, total, address
):
    response = buy(client, first_product_id, method=method, address=address)
    assert response.status_code == 200
    assert b"Order #1" in response.data
    assert get_fulfillment_option(method).label.encode() in response.data
    with app.app_context():
        order = get_session().scalar(select(Order))
        product = get_session().get(Product, first_product_id)
        assert order.fulfillment_method == method
        assert order.shipping_cents == fee
        assert order.subtotal_cents == 10000
        assert order.total_cents == total
        assert order.shipping_address == address
        assert len(order.items) == 1
        assert order.items[0].quantity == 1
        assert product.stock_quantity == 4


@pytest.mark.parametrize("method", ["standard_shipping", "express_shipping"])
def test_shipping_requires_address_and_does_not_change_data(client, app, first_product_id, method):
    response = buy(client, first_product_id, method=method, address="   ")
    assert b"A shipping address is required for delivery" in response.data
    with app.app_context():
        assert get_session().scalar(select(Order)) is None
        assert get_session().get(Product, first_product_id).stock_quantity == 5
    with client.session_transaction() as web_session:
        assert web_session["cart"][str(first_product_id)] == 1


def test_pickup_ignores_supplied_shipping_address(client, app, first_product_id):
    buy(client, first_product_id, method="store_pickup", address="Should not be stored")
    with app.app_context():
        order = get_session().scalar(select(Order))
        assert order.shipping_address == ""


def test_unknown_method_is_rejected_without_order_or_inventory_change(client, app, first_product_id):
    response = buy(client, first_product_id, method="free_express_fake")
    assert b"Please choose a valid fulfillment option" in response.data
    with app.app_context():
        assert get_session().scalar(select(Order)) is None
        assert get_session().get(Product, first_product_id).stock_quantity == 5


def test_client_cannot_override_shipping_fee(client, app, first_product_id, monkeypatch):
    from store.payments import FakePaymentProcessor

    amounts = []

    def capture_charge(_self, amount_cents, _token):
        amounts.append(amount_cents)
        return "pay_verified"

    monkeypatch.setattr(FakePaymentProcessor, "charge", capture_charge)
    buy(client, first_product_id, method="express_shipping", extra={"shipping_cents": "-900000"})
    assert amounts == [29900]
    with app.app_context():
        order = get_session().scalar(select(Order))
        assert order.shipping_cents == 19900
        assert order.payment_reference == "pay_verified"


@pytest.mark.parametrize("method,address", [
    ("express_shipping", "123 Test St"),
    ("store_pickup", ""),
])
def test_declined_payment_keeps_inventory_and_cart(client, app, first_product_id, method, address):
    response = buy(client, first_product_id, method=method, address=address, token="tok_fail")
    assert b"Payment was declined" in response.data
    with app.app_context():
        assert get_session().scalar(select(Order)) is None
        assert get_session().get(Product, first_product_id).stock_quantity == 5
    with client.session_transaction() as web_session:
        assert web_session["cart"][str(first_product_id)] == 1


def test_existing_checkout_without_option_defaults_to_standard(client, app, first_product_id):
    client.post(f"/cart/add/{first_product_id}")
    response = client.post("/checkout", data={
        "customer_name": "Grace", "customer_email": "grace@example.com",
        "shipping_address": "1 Legacy Lane", "payment_token": "tok_success",
    }, follow_redirects=True)
    assert b"Order #1" in response.data
    with app.app_context():
        order = get_session().scalar(select(Order))
        assert order.fulfillment_method == "standard_shipping"
        assert order.shipping_cents == 9900


def test_order_history_displays_fulfillment_choice(client, first_product_id):
    buy(client, first_product_id, method="express_shipping")
    response = client.get("/orders")
    assert b"Express Shipping" in response.data


def test_legacy_database_adds_column_without_losing_orders(tmp_path):
    """Old M1 databases are upgraded in place, not deleted and reseeded."""
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                customer_name VARCHAR(120) NOT NULL,
                customer_email VARCHAR(160) NOT NULL,
                shipping_address TEXT NOT NULL,
                subtotal_cents INTEGER NOT NULL,
                shipping_cents INTEGER NOT NULL,
                total_cents INTEGER NOT NULL,
                payment_reference VARCHAR(80) NOT NULL,
                status VARCHAR(30) NOT NULL,
                created_at DATETIME NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO orders (
                id, customer_name, customer_email, shipping_address,
                subtotal_cents, shipping_cents, total_cents,
                payment_reference, status, created_at
            ) VALUES (7, 'Legacy Buyer', 'legacy@example.com', 'Old Address',
                      10000, 9900, 19900, 'pay_old', 'confirmed', '2026-11-01 12:00:00')
        """)
    app = create_app({"TESTING": True, "DATABASE": str(path), "SECRET_KEY": "test"})
    with app.app_context():
        old = get_session().get(Order, 7)
        assert old.customer_name == "Legacy Buyer"
        assert old.fulfillment_method == "standard_shipping"
        assert old.shipping_cents == 9900
        assert old.total_cents == 19900
        assert old.payment_reference == "pay_old"
        app.extensions["store_engine"].dispose()

    # Startup is idempotent: an already migrated database must still open.
    again = create_app({"TESTING": True, "DATABASE": str(path), "SECRET_KEY": "test"})
    with again.app_context():
        assert get_session().get(Order, 7).fulfillment_method == "standard_shipping"
        again.extensions["store_engine"].dispose()
