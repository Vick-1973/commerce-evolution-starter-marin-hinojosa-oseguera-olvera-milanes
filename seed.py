"""BANVO demo catalog. Prices are fictional MXN values represented in cents.

IMPORTANT: seed() intentionally does not overwrite existing data. Perform
baseline validation first; then use `python reset_db.py` and `python seed.py`
to replace the development seed. Never reset a database with real orders.
"""
from sqlalchemy import func, select

from store import create_app
from store.db import get_session
from store.models import Product

PRODUCTS = [
    ("BNV-LAP-014", "BANVO CoreBook 14", "14-inch laptop with a lightweight metal design, built for study, work and everyday productivity.", 1_899_900, 8, "/static/images/banvo-laptop.svg"),
    ("BNV-AUD-020", "BANVO Pulse ANC", "Over-ear wireless headphones with noise cancellation, comfortable cushions and all-day battery.", 179_900, 16, "/static/images/banvo-headphones.svg"),
    ("BNV-KEY-075", "BANVO KeyPro 75", "Compact 75% mechanical keyboard with tactile switches and customizable lighting.", 139_900, 12, "/static/images/banvo-keyboard.svg"),
    ("BNV-MON-027", "BANVO Vision 27 QHD", "27-inch QHD monitor designed for crisp productivity and immersive entertainment.", 379_900, 9, "/static/images/banvo-monitor.svg"),
    ("BNV-WAT-101", "BANVO FitWatch S", "Smartwatch with activity tracking, customizable faces and notifications at a glance.", 249_900, 14, "/static/images/banvo-watch.svg"),
    ("BNV-MOU-002", "BANVO Glide Wireless", "Ergonomic rechargeable wireless mouse with adjustable sensitivity and quiet clicks.", 69_900, 21, "/static/images/banvo-mouse.svg"),
]


def seed() -> None:
    app = create_app()
    with app.app_context():
        db = get_session()
        count = db.scalar(select(func.count()).select_from(Product))
        if count:
            print(f"Database already contains {count} products; nothing changed.")
            return

        for sku, name, description, price, stock, image_url in PRODUCTS:
            db.add(Product(
                sku=sku,
                name=name,
                description=description,
                price_cents=price,
                stock_quantity=stock,
                image_url=image_url,
                active=1,
            ))
        db.commit()
        print(f"Seeded {len(PRODUCTS)} BANVO products.")


if __name__ == "__main__":
    seed()
