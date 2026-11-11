from pathlib import Path

from sqlalchemy import func, select

from store import create_app
from store.db import get_session
from store.models import Product

PRODUCTS = [
    ("START-100", "Everyday Backpack", "A clean, durable backpack for work, class, or travel.", 79900, 12, "/static/images/backpack.svg"),
    ("START-110", "Wireless Keyboard", "Compact wireless keyboard with a comfortable low-profile layout.", 119900, 10, "/static/images/keyboard.svg"),
    ("START-120", "Ceramic Mug", "A simple ceramic mug for coffee, tea, and long debugging sessions.", 24900, 20, "/static/images/mug.svg"),
    ("START-130", "Desk Lamp", "Adjustable desk lamp with warm and cool light settings.", 64900, 9, "/static/images/lamp.svg"),
    ("START-140", "Notebook Set", "Three hardcover notebooks for sketches, notes, and architecture diagrams.", 32900, 18, "/static/images/notebooks.svg"),
    ("START-150", "Travel Bottle", "Insulated stainless-steel bottle for everyday use.", 45900, 15, "/static/images/bottle.svg"),
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
        print(f"Seeded {len(PRODUCTS)} products.")


if __name__ == "__main__":
    seed()
