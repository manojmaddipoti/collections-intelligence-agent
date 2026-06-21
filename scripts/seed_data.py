"""
Synthetic data generator for the AR Collections Agent demo.

Generates a small, fully fictitious SQLite database modeling core AR
tables (CUSTOMERS, INVOICES, INVOICE_LINE_ITEMS, PAYMENT_HISTORY).

No real company, customer, or financial data is used anywhere in this
project. All names, amounts, tax IDs, and bank details are fake.

Dates are anchored to a fixed AS_OF_DATE rather than the real current
date, so aging buckets (30/60/90+) look the same every time this script
runs, regardless of when someone clones and runs the repo.
"""

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

SEED = 42
AS_OF_DATE = date(2026, 6, 20)  # fixed reference date for reproducible aging
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "ar_finance.db"

NUM_CUSTOMERS = 25
ACCOUNT_TIERS = ["Standard", "Premium", "Enterprise"]
PAYMENT_METHODS = ["ACH", "Wire", "Check", "Credit Card"]
LINE_ITEM_CATALOG = [
    ("Annual platform license", 1, 12000.00),
    ("Professional services - implementation", 40, 185.00),
    ("Premium support add-on", 1, 2400.00),
    ("Additional user seats", 10, 49.00),
    ("Data migration services", 1, 3500.00),
    ("Training workshop", 2, 750.00),
]

random.seed(SEED)
fake = Faker()
Faker.seed(SEED)


def fake_tax_id():
    # Fake EIN-style string for demo purposes only - not a real/valid tax ID
    return f"{random.randint(10, 99)}-{random.randint(1000000, 9999999)}"


def fake_bank_account():
    # Fake account-number-style string for demo purposes only
    return f"FAKE-{random.randint(10**9, 10**10 - 1)}"


def build_schema(conn):
    conn.executescript("""
    DROP TABLE IF EXISTS PAYMENT_HISTORY;
    DROP TABLE IF EXISTS INVOICE_LINE_ITEMS;
    DROP TABLE IF EXISTS INVOICES;
    DROP TABLE IF EXISTS CUSTOMERS;

    CREATE TABLE CUSTOMERS (
        customer_id          TEXT PRIMARY KEY,
        company_name         TEXT NOT NULL,
        account_tier         TEXT NOT NULL,
        contact_name          TEXT NOT NULL,
        contact_email         TEXT NOT NULL,
        tax_id                TEXT NOT NULL,
        bank_account_number   TEXT NOT NULL,
        credit_limit           REAL NOT NULL
    );

    CREATE TABLE INVOICES (
        invoice_id     TEXT PRIMARY KEY,
        customer_id    TEXT NOT NULL REFERENCES CUSTOMERS(customer_id),
        invoice_date   TEXT NOT NULL,
        due_date       TEXT NOT NULL,
        amount         REAL NOT NULL,
        amount_paid    REAL NOT NULL DEFAULT 0,
        status         TEXT NOT NULL
    );

    CREATE TABLE INVOICE_LINE_ITEMS (
        line_item_id  TEXT PRIMARY KEY,
        invoice_id    TEXT NOT NULL REFERENCES INVOICES(invoice_id),
        description   TEXT NOT NULL,
        quantity      INTEGER NOT NULL,
        unit_price    REAL NOT NULL,
        line_total    REAL NOT NULL
    );

    CREATE TABLE PAYMENT_HISTORY (
        payment_id      TEXT PRIMARY KEY,
        invoice_id      TEXT NOT NULL REFERENCES INVOICES(invoice_id),
        customer_id     TEXT NOT NULL REFERENCES CUSTOMERS(customer_id),
        payment_date    TEXT NOT NULL,
        amount_paid     REAL NOT NULL,
        payment_method  TEXT NOT NULL
    );
    """)


def aging_bucket_days():
    """Pick an overdue-day count weighted across realistic buckets."""
    bucket = random.choices(
        ["current", "30", "60", "90plus"],
        weights=[35, 25, 20, 20],
        k=1,
    )[0]
    if bucket == "current":
        return random.randint(-15, 15)
    if bucket == "30":
        return random.randint(1, 30)
    if bucket == "60":
        return random.randint(31, 60)
    return random.randint(61, 130)


def seed(conn):
    cur = conn.cursor()

    for i in range(1, NUM_CUSTOMERS + 1):
        customer_id = f"CUST-{i:04d}"
        cur.execute(
            """INSERT INTO CUSTOMERS
               (customer_id, company_name, account_tier, contact_name,
                contact_email, tax_id, bank_account_number, credit_limit)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                customer_id,
                fake.company(),
                random.choice(ACCOUNT_TIERS),
                fake.name(),
                fake.company_email(),
                fake_tax_id(),
                fake_bank_account(),
                round(random.uniform(10000, 250000), 2),
            ),
        )

        num_invoices = random.randint(3, 8)
        for j in range(1, num_invoices + 1):
            invoice_id = f"INV-{i:04d}-{j:02d}"
            overdue_days = aging_bucket_days()
            due_date = AS_OF_DATE - timedelta(days=overdue_days)
            invoice_date = due_date - timedelta(days=30)

            num_lines = random.randint(1, 3)
            line_items = random.sample(LINE_ITEM_CATALOG, k=num_lines)
            amount = 0.0
            for k, (desc, qty, price) in enumerate(line_items, start=1):
                line_total = round(qty * price, 2)
                amount += line_total
                cur.execute(
                    """INSERT INTO INVOICE_LINE_ITEMS
                       (line_item_id, invoice_id, description, quantity,
                        unit_price, line_total)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (f"{invoice_id}-L{k}", invoice_id, desc, qty, price, line_total),
                )
            amount = round(amount, 2)

            pay_roll = random.random()
            if overdue_days < 0:
                amount_paid, status = 0.0, "Open"
            elif pay_roll < 0.4:
                amount_paid, status = amount, "Paid"
            elif pay_roll < 0.6:
                amount_paid = round(amount * random.uniform(0.2, 0.8), 2)
                status = "Partially Paid"
            else:
                amount_paid, status = 0.0, "Overdue"

            cur.execute(
                """INSERT INTO INVOICES
                   (invoice_id, customer_id, invoice_date, due_date,
                    amount, amount_paid, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    invoice_id, customer_id,
                    invoice_date.isoformat(), due_date.isoformat(),
                    amount, amount_paid, status,
                ),
            )

            if amount_paid > 0:
                payment_date = due_date - timedelta(days=random.randint(0, 10))
                cur.execute(
                    """INSERT INTO PAYMENT_HISTORY
                       (payment_id, invoice_id, customer_id, payment_date,
                        amount_paid, payment_method)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        f"{invoice_id}-PMT", invoice_id, customer_id,
                        payment_date.isoformat(), amount_paid,
                        random.choice(PAYMENT_METHODS),
                    ),
                )

    conn.commit()


def print_summary(conn):
    cur = conn.cursor()
    counts = {}
    for table in ["CUSTOMERS", "INVOICES", "INVOICE_LINE_ITEMS", "PAYMENT_HISTORY"]:
        counts[table] = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    print("Seed complete:")
    for table, n in counts.items():
        print(f"  {table:<22} {n} rows")

    as_of = AS_OF_DATE.isoformat()
    print(f"\nAging snapshot (as of {as_of}):")
    cur.execute(f"""
        SELECT
          CASE
            WHEN julianday('{as_of}') - julianday(due_date) <= 0 THEN 'Current'
            WHEN julianday('{as_of}') - julianday(due_date) <= 30 THEN '1-30 days'
            WHEN julianday('{as_of}') - julianday(due_date) <= 60 THEN '31-60 days'
            WHEN julianday('{as_of}') - julianday(due_date) <= 90 THEN '61-90 days'
            ELSE '90+ days'
          END AS bucket,
          COUNT(*) AS invoice_count,
          ROUND(SUM(amount - amount_paid), 2) AS open_balance
        FROM INVOICES
        WHERE status != 'Paid'
        GROUP BY bucket
        ORDER BY MIN(julianday('{as_of}') - julianday(due_date))
    """)
    for bucket, count, balance in cur.fetchall():
        print(f"  {bucket:<12} {count:>3} invoices   ${balance:>12,.2f} open")


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        build_schema(conn)
        seed(conn)
        print_summary(conn)
    finally:
        conn.close()
    print(f"\nDatabase written to {DB_PATH}")


if __name__ == "__main__":
    main()
