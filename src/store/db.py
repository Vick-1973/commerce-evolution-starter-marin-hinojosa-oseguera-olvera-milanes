from __future__ import annotations

from flask import Flask, current_app, g
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def _database_url(database: str) -> str:
    if database == ":memory:":
        return "sqlite+pysqlite:///:memory:"
    return f"sqlite+pysqlite:///{database}"


def init_app(app: Flask) -> None:
    from . import models  # noqa: F401 - registers mapped classes

    database = app.config["DATABASE"]
    engine = create_engine(
        _database_url(database),
        connect_args={"check_same_thread": False},
    )
    app.extensions["store_engine"] = engine
    app.extensions["store_session_factory"] = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )
    Base.metadata.create_all(engine)
    # SQLAlchemy create_all does not add new columns to an existing SQLite table.
    # Preserve historical BANVO orders when upgrading from M1 rather than reset DB.
    if "fulfillment_method" not in {
        column["name"] for column in inspect(engine).get_columns("orders")
    }:
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE orders ADD COLUMN fulfillment_method "
                "VARCHAR(40) NOT NULL DEFAULT 'standard_shipping'"
            ))
    # M3: additive migration of existing M1/M2 SQLite databases.
    # Do not reset or re-seed: historical payments, orders and inventory survive.
    current_columns = {col["name"] for col in inspect(engine).get_columns("orders")}
    with engine.begin() as connection:
        if "source" not in current_columns:
            connection.execute(text(
                "ALTER TABLE orders ADD COLUMN source VARCHAR(20) "
                "NOT NULL DEFAULT 'storefront'"
            ))
        if "external_order_id" not in current_columns:
            connection.execute(text(
                "ALTER TABLE orders ADD COLUMN external_order_id VARCHAR(120)"
            ))
        if "external_payload_hash" not in current_columns:
            connection.execute(text(
                "ALTER TABLE orders ADD COLUMN external_payload_hash VARCHAR(64)"
            ))
        # SQLAlchemy create_all cannot backfill indexes on existing tables.
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_source_external "
            "ON orders(source, external_order_id)"
        ))
    app.teardown_appcontext(close_session)


def get_session() -> Session:
    if "db_session" not in g:
        factory = current_app.extensions["store_session_factory"]
        g.db_session = factory()
    return g.db_session


def close_session(_error: BaseException | None = None) -> None:
    session = g.pop("db_session", None)
    if session is not None:
        session.close()
