from pathlib import Path

from flask import current_app

from store import create_app


def reset() -> None:
    app = create_app()
    with app.app_context():
        db_path = Path(current_app.config["DATABASE"])
    if db_path.exists():
        db_path.unlink()
        print(f"Removed {db_path}")
    else:
        print(f"No database found at {db_path}")
    print("Run `python seed.py` to recreate and seed the database.")


if __name__ == "__main__":
    reset()
