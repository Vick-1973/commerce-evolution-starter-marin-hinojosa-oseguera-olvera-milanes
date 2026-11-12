"""Read-only CLI evidence of actual BANVO database state; does not modify it.

Run from repo root: `python scripts/inspect_persistence.py`
Use before and after a purchase and after restarting Flask.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from store import create_app


def main() -> None:
    app = create_app()
    with app.app_context():
        path = Path(app.config["DATABASE"])
    print(f"DATABASE = {path}")
    if not path.exists():
        print("No database found; run `python seed.py` first.")
        return
    with sqlite3.connect(path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, sql in [
            ("products", "SELECT id, sku, name, stock_quantity FROM products ORDER BY id"),
            ("orders", "SELECT id, customer_name, total_cents, payment_reference, status FROM orders ORDER BY id DESC"),
            ("order_items", "SELECT order_id, sku, product_name, quantity, unit_price_cents FROM order_items ORDER BY id DESC"),
        ]:
            print(f"\n===== {table.upper()} =====")
            if table not in tables:
                print("table not found")
                continue
            rows = conn.execute(sql).fetchall()
            print(f"rows: {len(rows)}")
            for row in rows:
                print(row)


if __name__ == "__main__":
    main()
