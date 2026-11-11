from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from .db import init_app as init_database


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    database_path = Path(app.instance_path) / "store.db"

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("STORE_SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.environ.get("STORE_DATABASE", str(database_path)),
        STORE_NAME=os.environ.get("STORE_NAME", "Starter Store"),
    )

    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    init_database(app)

    from .routes.catalog import bp as catalog_bp
    from .routes.cart import bp as cart_bp
    from .routes.checkout import bp as checkout_bp
    from .routes.orders import bp as orders_bp

    app.register_blueprint(catalog_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(orders_bp)

    @app.template_filter("money")
    def money(cents: int) -> str:
        return f"${cents / 100:,.2f}"

    return app
