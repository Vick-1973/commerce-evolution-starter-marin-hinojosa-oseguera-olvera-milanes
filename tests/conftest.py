from pathlib import Path

import pytest
from sqlalchemy import select

from store import create_app
from store.db import get_session
from store.models import Product


@pytest.fixture()
def app(tmp_path: Path):
    db_path = tmp_path / "test.db"
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE": str(db_path),
        "STORE_NAME": "Test Store",
    })
    with app.app_context():
        db = get_session()
        db.add_all([
            Product(sku="TEST-1", name="First Product", description="One", price_cents=10000, stock_quantity=5, image_url="/static/images/mug.svg", active=1),
            Product(sku="TEST-2", name="Second Product", description="Two", price_cents=25000, stock_quantity=2, image_url="/static/images/lamp.svg", active=1),
        ])
        db.commit()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def first_product_id(app):
    with app.app_context():
        return get_session().scalar(select(Product.id).where(Product.sku == "TEST-1"))
