import sqlite3
from pathlib import Path


def main() -> None:
    db = Path("events.db")
    if not db.exists():
        raise FileNotFoundError("No existe events.db. Ejecuta primero activity_logger.py")

    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        """
        SELECT timestamp, app_name, event_type, value, file_path, duration
        FROM events
        ORDER BY id DESC
        LIMIT 50
        """
    ).fetchall()
    conn.close()

    for row in rows:
        print(row)


if __name__ == "__main__":
    main()

