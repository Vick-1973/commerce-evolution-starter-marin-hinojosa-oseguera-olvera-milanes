"""Marketplace API, shared ordering, payment isolation and DB idempotency."""
from __future__ import annotations

import sqlite3
from copy import deepcopy

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from store import create_app
from store.db import get_session
from store.models import Order, Product
from store.payments import FakePaymentProcessor

KEY = "classroom-marketplace-key"


@pytest.fixture
def marketplace_client(app):
    app.config["MARKETPLACE_API_KEY"] = KEY
    return app.test_client()


@pytest.fixture
def payload():
    return {
        "external_order_id": "MKT-1001",
        "buyer": {"name": "Grace Hopper", "email": "grace@example.com"},
        "shipping": {"method": "standard_shipping", "address": "123 Market Road"},
        "items": [{"sku": "TEST-1", "quantity": 2}],
    }


def post(client, payload, key=KEY):
    return client.post(
        "/api/marketplace/orders", json=payload,
        headers={"X-Marketplace-Key": key},
    )


def counts_and_stock(app):
    with app.app_context():
        db = get_session()
        return (
            db.scalar(select(func.count()).select_from(Order)),
            db.scalar(select(Product.stock_quantity).where(Product.sku == "TEST-1")),
        )


@pytest.mark.parametrize("method,fee,address", [
    ("standard_shipping", 9900, "123 Market Road"),
    ("express_shipping", 19900, "123 Market Road"),
    ("store_pickup", 0, ""),
])
def test_marketplace_persists_source_items_fulfillment_and_inventory(
    marketplace_client, app, payload, monkeypatch, method, fee, address
):
    def forbidden_charge(*args, **kwargs):
        raise AssertionError("marketplace must never invoke payment processor")

    monkeypatch.setattr(FakePaymentProcessor, "charge", forbidden_charge)
    payload["shipping"] = {"method": method, "address": address}
    response = post(marketplace_client, payload)
    assert response.status_code == 201, response.json
    assert response.json["replayed"] is False
    assert response.json["shipping_cents"] == fee
    assert response.json["subtotal_cents"] == 20000
    assert response.json["total_cents"] == 20000 + fee
    with app.app_context():
        db = get_session()
        order = db.scalar(select(Order))
        assert order.source == "marketplace"
        assert order.external_order_id == "MKT-1001"
        assert len(order.external_payload_hash) == 64
        assert order.shipping_address == address
        assert order.fulfillment_method == method
        assert order.payment_reference.startswith("marketplace_paid_")
        assert len(order.items) == 1
        assert order.items[0].sku == "TEST-1"
        assert order.items[0].quantity == 2
        assert db.scalar(select(Product.stock_quantity).where(Product.sku == "TEST-1")) == 3


def test_exact_replay_returns_existing_order_without_second_stock_change(
    marketplace_client, app, payload
):
    first = post(marketplace_client, payload)
    second = post(marketplace_client, payload)
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json["replayed"] is True
    assert first.json["order_id"] == second.json["order_id"]
    assert counts_and_stock(app) == (1, 3)


def test_replay_works_even_after_first_order_sells_out(marketplace_client, app, payload):
    payload["items"][0]["quantity"] = 5
    assert post(marketplace_client, payload).status_code == 201
    assert post(marketplace_client, payload).status_code == 200
    assert counts_and_stock(app) == (1, 0)


def test_conflicting_payload_with_same_external_id_returns_409(
    marketplace_client, app, payload
):
    assert post(marketplace_client, payload).status_code == 201
    changed = deepcopy(payload)
    changed["items"][0]["quantity"] = 1
    response = post(marketplace_client, changed)
    assert response.status_code == 409
    assert "different order details" in response.json["error"]
    assert counts_and_stock(app) == (1, 3)


def test_duplicate_sku_lines_are_combined_and_reordered_replay_is_stable(
    marketplace_client, app, payload
):
    payload["items"] = [
        {"sku": "TEST-1", "quantity": 1},
        {"sku": "TEST-2", "quantity": 1},
        {"sku": "TEST-1", "quantity": 1},
    ]
    response = post(marketplace_client, payload)
    assert response.status_code == 201
    assert response.json["subtotal_cents"] == 45000
    changed = deepcopy(payload)
    changed["items"].reverse()
    assert post(marketplace_client, changed).status_code == 200
    with app.app_context():
        order = get_session().scalar(select(Order))
        assert len(order.items) == 2
        assert {i.sku: i.quantity for i in order.items} == {"TEST-1": 2, "TEST-2": 1}


def test_pickup_ignores_irrelevant_address_on_replay(marketplace_client, app, payload):
    payload["shipping"] = {"method": "store_pickup", "address": "Not needed"}
    assert post(marketplace_client, payload).status_code == 201
    payload["shipping"]["address"] = "Other ignored address"
    assert post(marketplace_client, payload).status_code == 200
    assert counts_and_stock(app) == (1, 3)


def test_different_external_ids_create_separate_orders(marketplace_client, app, payload):
    assert post(marketplace_client, payload).status_code == 201
    payload["external_order_id"] = "MKT-1002"
    assert post(marketplace_client, payload).status_code == 201
    assert counts_and_stock(app) == (2, 1)


def test_missing_secret_config_disables_api(client, payload):
    assert post(client, payload).status_code == 503


@pytest.mark.parametrize("key", ["", "wrong", "classroom-marketplace-key-nope"])
def test_rejects_requests_without_valid_integration_key(marketplace_client, payload, key):
    assert post(marketplace_client, payload, key=key).status_code == 401


def test_requires_json_media_type(marketplace_client):
    response = marketplace_client.post(
        "/api/marketplace/orders", data="not-json", headers={"X-Marketplace-Key": KEY}
    )
    assert response.status_code == 415


@pytest.mark.parametrize("change", [
    lambda x: x.update(external_order_id=""),
    lambda x: x.update(buyer={"name": "", "email": "a@b.com"}),
    lambda x: x.update(buyer={"name": "Ada", "email": "invalid"}),
    lambda x: x.update(shipping={"method": "unsupported", "address": "A"}),
    lambda x: x.update(shipping={"method": "express_shipping", "address": ""}),
    lambda x: x.update(items=[]),
    lambda x: x.update(items=[{"sku": "TEST-1", "quantity": -1}]),
    lambda x: x.update(items=[{"sku": "TEST-1", "quantity": True}]),
    lambda x: x.update(items=[{"sku": "TEST-1", "quantity": "1"}]),
])
def test_malformed_payload_rejected_without_order_or_stock_change(
    marketplace_client, app, payload, change
):
    change(payload)
    response = post(marketplace_client, payload)
    assert response.status_code == 400, response.json
    assert counts_and_stock(app) == (0, 5)


def test_unknown_sku_rejected_without_order(marketplace_client, app, payload):
    payload["items"] = [{"sku": "NOT-HERE", "quantity": 1}]
    assert post(marketplace_client, payload).status_code == 404
    assert counts_and_stock(app) == (0, 5)


def test_out_of_stock_is_conflict_and_preserves_inventory(marketplace_client, app, payload):
    payload["items"][0]["quantity"] = 6
    assert post(marketplace_client, payload).status_code == 409
    assert counts_and_stock(app) == (0, 5)


def test_client_supplied_price_and_payment_token_are_ignored(
    marketplace_client, app, payload, monkeypatch
):
    def forbidden_charge(*args, **kwargs):
        raise AssertionError("not allowed")
    monkeypatch.setattr(FakePaymentProcessor, "charge", forbidden_charge)
    payload["items"][0]["price_cents"] = 1
    payload["payment_token"] = "tok_fail"
    response = post(marketplace_client, payload)
    assert response.status_code == 201
    assert response.json["subtotal_cents"] == 20000


def test_storefront_still_charges_and_marks_origin(client, app, first_product_id, monkeypatch):
    calls = []
    def fake_charge(self, amount, token):
        calls.append((amount, token))
        return "pay_storefront"
    monkeypatch.setattr(FakePaymentProcessor, "charge", fake_charge)
    client.post(f"/cart/add/{first_product_id}")
    result = client.post("/checkout", data={
        "customer_name": "Web Customer", "customer_email": "web@example.com",
        "shipping_address": "Web Street", "payment_token": "tok_success",
        "fulfillment_method": "express_shipping",
    }, follow_redirects=True)
    assert result.status_code == 200
    assert b"Order #1" in result.data
    assert calls == [(29900, "tok_success")]
    with app.app_context():
        order = get_session().scalar(select(Order))
        assert order.source == "storefront"
        assert order.external_order_id is None
        assert order.total_cents == 29900


def test_marketplace_order_visible_in_order_history_and_detail(marketplace_client, payload):
    response = post(marketplace_client, payload)
    order_id = response.json["order_id"]
    page = marketplace_client.get(f"/orders/{order_id}")
    assert page.status_code == 200
    assert b"Marketplace order ID" in page.data
    assert b"MKT-1001" in page.data


def test_database_unique_index_prevents_external_duplicate(app):
    with app.app_context():
        db = get_session()
        common = dict(
            source="marketplace", external_order_id="EXTERNAL-1",
            customer_name="A", customer_email="a@example.com", shipping_address="",
            fulfillment_method="store_pickup", subtotal_cents=10000,
            shipping_cents=0, total_cents=10000, payment_reference="external-paid",
            status="confirmed",
        )
        db.add(Order(**common)); db.commit()
        db.add(Order(**common))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.scalar(select(func.count()).select_from(Order)) == 1


def test_m2_database_migrates_to_m3_without_losing_old_order(tmp_path):
    path = tmp_path / "m2-schema.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE orders (
          id INTEGER PRIMARY KEY, customer_name VARCHAR(120) NOT NULL,
          customer_email VARCHAR(160) NOT NULL, shipping_address TEXT NOT NULL,
          fulfillment_method VARCHAR(40) NOT NULL DEFAULT 'standard_shipping',
          subtotal_cents INTEGER NOT NULL, shipping_cents INTEGER NOT NULL,
          total_cents INTEGER NOT NULL, payment_reference VARCHAR(80) NOT NULL,
          status VARCHAR(30) NOT NULL, created_at DATETIME NOT NULL)""")
        connection.execute("""INSERT INTO orders (
            id,customer_name,customer_email,shipping_address,fulfillment_method,
            subtotal_cents,shipping_cents,total_cents,payment_reference,status,created_at
            ) VALUES (17,'Past Buyer','past@example.com','Old Street','express_shipping',
            10000,19900,29900,'pay_legacy','confirmed','2026-11-10 12:00:00')""")
    app = create_app({"TESTING": True, "DATABASE": str(path), "SECRET_KEY": "test"})
    with app.app_context():
        db = get_session()
        old = db.get(Order, 17)
        assert old.customer_name == "Past Buyer"
        assert old.fulfillment_method == "express_shipping"
        assert old.source == "storefront"
        assert old.external_order_id is None
        assert old.payment_reference == "pay_legacy"
        assert old.total_cents == 29900
        db.close()
        app.extensions["store_engine"].dispose()
    with sqlite3.connect(path) as connection:
        indexes = connection.execute("PRAGMA index_list('orders')").fetchall()
        assert any("uq_orders_source_external" in row[1] for row in indexes)


def test_retry_survives_application_restart(app, marketplace_client, payload):
    assert post(marketplace_client, payload).status_code == 201
    database = app.config["DATABASE"]
    # A separate app instance acts like a process restart with the same SQLite DB.
    restarted = create_app({
        "TESTING": True, "DATABASE": database, "SECRET_KEY": "another-secret",
        "MARKETPLACE_API_KEY": KEY,
    })
    repeat = post(restarted.test_client(), payload)
    assert repeat.status_code == 200
    assert repeat.json["order_id"] == 1
    with restarted.app_context():
        assert get_session().scalar(select(func.count()).select_from(Order)) == 1
        assert get_session().scalar(select(Product.stock_quantity).where(Product.sku == "TEST-1")) == 3
        restarted.extensions["store_engine"].dispose()


def test_shared_core_rolls_back_all_items_when_stock_changes_after_quote(app):
    from sqlalchemy import update
    from store.ordering import InsufficientStock, RequestedItem, prepare_order, save_order

    with app.app_context():
        db = get_session()
        quote = prepare_order(
            db, [RequestedItem("TEST-1", 1), RequestedItem("TEST-2", 2)],
            "standard_shipping", "Street 1",
        )
        # Another sale consumes TEST-2 after the quote but before final save.
        db.execute(update(Product).where(Product.sku == "TEST-2").values(stock_quantity=0))
        db.commit()
        with pytest.raises(InsufficientStock):
            save_order(db, quote, customer_name="Buyer", customer_email="buyer@example.com",
                       payment_reference="pay_externalized")
        assert db.scalar(select(func.count()).select_from(Order)) == 0
        assert db.scalar(select(Product.stock_quantity).where(Product.sku == "TEST-1")) == 5
        assert db.scalar(select(Product.stock_quantity).where(Product.sku == "TEST-2")) == 0


def test_legacy_m2_migration_is_repeatable_with_history_preserved(tmp_path):
    db_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("""CREATE TABLE orders (
          id INTEGER PRIMARY KEY, customer_name VARCHAR(120) NOT NULL,
          customer_email VARCHAR(160) NOT NULL, shipping_address TEXT NOT NULL,
          fulfillment_method VARCHAR(40) NOT NULL DEFAULT 'standard_shipping',
          subtotal_cents INTEGER NOT NULL, shipping_cents INTEGER NOT NULL,
          total_cents INTEGER NOT NULL, payment_reference VARCHAR(80) NOT NULL,
          status VARCHAR(30) NOT NULL, created_at DATETIME NOT NULL)""")
        connection.execute("""INSERT INTO orders (
          id,customer_name,customer_email,shipping_address,fulfillment_method,
          subtotal_cents,shipping_cents,total_cents,payment_reference,status,created_at)
          VALUES (77,'Original','old@example.com','Street','standard_shipping',
                  10000,9900,19900,'pay_legacy','confirmed','2026-11-01 10:00:00')""")
    for _ in range(2):
        migrated = create_app({"TESTING": True, "DATABASE": str(db_path), "SECRET_KEY": "test"})
        with migrated.app_context():
            assert get_session().get(Order, 77).payment_reference == "pay_legacy"
            assert get_session().get(Order, 77).source == "storefront"
            get_session().close()
            migrated.extensions["store_engine"].dispose()
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
