"""Create synthetic reference data only when the configured database is absent."""

import sqlite3

import seed_data

REQUIRED_TABLES = {
    "CUSTOMERS",
    "INVOICES",
    "INVOICE_LINE_ITEMS",
    "PAYMENT_HISTORY",
    "COLLECTION_CASES",
    "DRAFT_COMMUNICATIONS",
}


def database_is_ready() -> bool:
    """Return whether the existing SQLite file has the required schema."""
    if not seed_data.DB_PATH.exists():
        return False
    conn = sqlite3.connect(seed_data.DB_PATH)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        conn.close()
    missing = REQUIRED_TABLES - tables
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise RuntimeError(
            f"Existing database is incomplete; missing tables: {missing_names}. "
            "Run scripts/seed_data.py explicitly to reset it."
        )
    return True


def main() -> None:
    """Seed once on first startup and preserve existing state thereafter."""
    if database_is_ready():
        print(f"Using existing synthetic database at {seed_data.DB_PATH}")
        return
    print("Synthetic database not found; generating it once.")
    seed_data.main()


if __name__ == "__main__":
    main()
