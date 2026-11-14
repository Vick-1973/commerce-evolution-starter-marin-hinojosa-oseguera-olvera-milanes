
from pathlib import Path

from flask import current_app
from store import create_app


def reset() -> None:
    app = create_app()

    with app.app_context():
        db_path = Path(current_app.config["DATABASE"])

        # Close SQLAlchemy's pooled connections
        engine = app.extensions["store_engine"]
        engine.dispose()

    if db_path.exists():
        try:
            db_path.unlink()
            print(f"Removed {db_path}")
        except PermissionError:
            print("ERROR: The database is still being used.")
            print("Close Flask or any SQLite database viewers.")
            raise SystemExit(1)
    else:
        print(f"No database found at {db_path}")

    print("Run 'python seed.py' to recreate and seed the database.")


if __name__ == "__main__":
    reset()
