"""
MCP server for the Collections Intelligence Agent.

Provides tools for querying AR data (customers, invoices, aging) and
managing draft collection communications. All PII fields (tax_id,
bank_account_number) are masked server-side before results are returned
to any agent — this is enforced in code, not via prompt instructions.

Run standalone:
    python mcp_server/server.py

Or let the ADK agent launch it via StdioConnectionParams.
"""

import functools
import hmac
import json
import logging
import os
import sqlite3
import sys
import time
import uuid
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

from mcp.server.fastmcp import FastMCP
from opentelemetry import trace

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = Path(
    os.getenv(
        "AR_DATABASE_PATH",
        Path(__file__).resolve().parent.parent / "data" / "ar_finance.db",
    )
)
AS_OF_DATE = date(2026, 6, 20)  # must match seed_data.py
_TOOL_CALLS: Counter[str] = Counter()
_TOOL_ERRORS: Counter[str] = Counter()
_TRACER = trace.get_tracer("collections_intelligence.mcp")
_F = TypeVar("_F", bound=Callable[..., dict])


class _JsonFormatter(logging.Formatter):
    """Format MCP operational events as single-line JSON on stderr."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in (
            "event",
            "tool",
            "outcome",
            "duration_ms",
            "invocation_id",
            "tool_call_count",
            "tool_error_count",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, separators=(",", ":"))


_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(_JsonFormatter())
logger = logging.getLogger("collections_intelligence.mcp")
logger.handlers.clear()
logger.addHandler(_handler)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
logger.propagate = False

mcp = FastMCP(
    "collections-intelligence",
    instructions=(
        "MCP server for AR collections data. Provides tools to query "
        "customers, invoices, aging reports, and manage draft communications. "
        "PII fields are masked automatically."
    ),
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_conn() -> sqlite3.Connection:
    """Return a new connection with row_factory set to sqlite3.Row."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _mask_customer_row(row: dict) -> dict:
    """Strip PII fields from a customer row before returning to the agent.

    This is the single enforcement point for PII masking — it runs
    server-side inside the tool function, so PII never enters the
    agent's context window.
    """
    masked = dict(row)
    if "tax_id" in masked:
        masked["tax_id"] = "***MASKED***"
    if "bank_account_number" in masked:
        masked["bank_account_number"] = "***MASKED***"
    return masked


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    """Convert a list of sqlite3.Row objects to plain dicts."""
    return [dict(row) for row in rows]


def _instrument_tool(func: _F) -> _F:
    """Emit a span, structured latency event, and process-local tool counters."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> dict:
        tool_name = func.__name__
        invocation_id = uuid.uuid4().hex
        started = time.perf_counter()
        outcome = "ok"
        _TOOL_CALLS[tool_name] += 1
        with _TRACER.start_as_current_span(f"mcp.tool.{tool_name}") as span:
            span.set_attribute("mcp.tool.name", tool_name)
            span.set_attribute("mcp.invocation_id", invocation_id)
            try:
                result = func(*args, **kwargs)
                if "error" in result:
                    outcome = "rejected"
                    _TOOL_ERRORS[tool_name] += 1
                return result
            except Exception:
                outcome = "error"
                _TOOL_ERRORS[tool_name] += 1
                span.record_exception(sys.exc_info()[1])
                logger.exception(
                    "MCP tool failed",
                    extra={
                        "event": "mcp_tool_call",
                        "tool": tool_name,
                        "outcome": outcome,
                        "invocation_id": invocation_id,
                    },
                )
                raise
            finally:
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                span.set_attribute("mcp.outcome", outcome)
                span.set_attribute("mcp.duration_ms", duration_ms)
                logger.info(
                    "MCP tool completed",
                    extra={
                        "event": "mcp_tool_call",
                        "tool": tool_name,
                        "outcome": outcome,
                        "duration_ms": duration_ms,
                        "invocation_id": invocation_id,
                        "tool_call_count": _TOOL_CALLS[tool_name],
                        "tool_error_count": _TOOL_ERRORS[tool_name],
                    },
                )

    return wrapper  # type: ignore[return-value]


def _ensure_drafts_table(conn: sqlite3.Connection) -> None:
    """Create the DRAFT_COMMUNICATIONS table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS DRAFT_COMMUNICATIONS (
            draft_id       TEXT PRIMARY KEY,
            customer_id    TEXT NOT NULL REFERENCES CUSTOMERS(customer_id),
            subject        TEXT NOT NULL,
            body           TEXT NOT NULL,
            tone           TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'pending_review'
                           CHECK (status IN ('pending_review', 'approved')),
            created_at     TEXT NOT NULL,
            reviewed_at    TEXT,
            approved_by    TEXT
        )
    """)
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(DRAFT_COMMUNICATIONS)").fetchall()
    }
    if "approved_by" not in columns:
        conn.execute("ALTER TABLE DRAFT_COMMUNICATIONS ADD COLUMN approved_by TEXT")
    conn.commit()


def _draft_database_url() -> str | None:
    """Return the optional Postgres URL used for mutable draft state."""
    return os.getenv("DRAFT_DATABASE_URL")


def _get_postgres_conn() -> Any:
    """Connect to the configured Postgres draft store."""
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "DRAFT_DATABASE_URL requires psycopg; install project requirements."
        ) from exc
    return psycopg.connect(_draft_database_url(), row_factory=dict_row)


def _ensure_postgres_drafts_table(conn: Any) -> None:
    """Create the durable Postgres table used for mutable draft state."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS draft_communications (
            draft_id       TEXT PRIMARY KEY,
            customer_id    TEXT NOT NULL,
            subject        TEXT NOT NULL,
            body           TEXT NOT NULL,
            tone           TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'pending_review'
                           CHECK (status IN ('pending_review', 'approved')),
            created_at     TIMESTAMPTZ NOT NULL,
            reviewed_at    TIMESTAMPTZ,
            approved_by    TEXT
        )
        """
    )
    conn.commit()


def _approval_authorized(approver_id: str, approval_token: str) -> bool:
    """Validate a human approver against their server-side credential."""
    try:
        credentials = json.loads(os.getenv("APPROVER_CREDENTIALS_JSON", "{}"))
    except json.JSONDecodeError:
        return False
    if not isinstance(credentials, dict):
        return False
    expected_token = credentials.get(approver_id)
    return bool(
        isinstance(expected_token, str)
        and expected_token
        and hmac.compare_digest(approval_token, expected_token)
    )


# ---------------------------------------------------------------------------
# Tools — Customer data (PII-masked)
# ---------------------------------------------------------------------------


@mcp.tool()
@_instrument_tool
def get_customer_summary(customer_id: str) -> dict:
    """Get summary information for a specific customer.

    Returns customer name, account tier, contact info, and credit limit.
    PII fields (tax_id, bank_account_number) are masked.

    Args:
        customer_id: The customer ID (e.g. 'CUST-0001').
    """
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM CUSTOMERS WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()
        if row is None:
            return {"error": f"Customer {customer_id} not found."}
        return {"customer": _mask_customer_row(dict(row))}
    finally:
        conn.close()


@mcp.tool()
@_instrument_tool
def list_customers() -> dict:
    """List all customers with basic info.

    Returns each customer's ID, company name, account tier, contact name,
    and credit limit. PII fields are masked.
    """
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT * FROM CUSTOMERS ORDER BY customer_id").fetchall()
        customers = [_mask_customer_row(dict(r)) for r in rows]
        return {"customers": customers, "count": len(customers)}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tools — Invoice and payment data
# ---------------------------------------------------------------------------


@mcp.tool()
@_instrument_tool
def get_customer_invoices(customer_id: str) -> dict:
    """Get all invoices for a customer with status and aging information.

    Each invoice includes: invoice_id, invoice_date, due_date, amount,
    amount_paid, status, and days_overdue (relative to the reference date).

    Args:
        customer_id: The customer ID (e.g. 'CUST-0001').
    """
    as_of = AS_OF_DATE.isoformat()
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT *,
                   CAST(julianday(?) - julianday(due_date) AS INTEGER) AS days_overdue
            FROM INVOICES
            WHERE customer_id = ?
            ORDER BY due_date
            """,
            (as_of, customer_id),
        ).fetchall()
        invoices = _rows_to_dicts(rows)
        return {
            "customer_id": customer_id,
            "invoices": invoices,
            "count": len(invoices),
        }
    finally:
        conn.close()


@mcp.tool()
@_instrument_tool
def get_invoice_details(invoice_id: str) -> dict:
    """Get detailed information for a specific invoice.

    Returns the invoice header, its line items, and payment history.

    Args:
        invoice_id: The invoice ID (e.g. 'INV-0001-01').
    """
    conn = _get_conn()
    try:
        invoice = conn.execute(
            "SELECT * FROM INVOICES WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchone()
        if invoice is None:
            return {"error": f"Invoice {invoice_id} not found."}

        line_items = conn.execute(
            "SELECT * FROM INVOICE_LINE_ITEMS WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchall()

        payments = conn.execute(
            "SELECT * FROM PAYMENT_HISTORY WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchall()

        return {
            "invoice": dict(invoice),
            "line_items": _rows_to_dicts(line_items),
            "payments": _rows_to_dicts(payments),
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tools — AR aging and risk analysis
# ---------------------------------------------------------------------------


@mcp.tool()
@_instrument_tool
def get_ar_aging_report() -> dict:
    """Get the accounts receivable aging report.

    Returns aggregated aging buckets (Current, 1-30 days, 31-60 days,
    61-90 days, 90+ days) with invoice counts and total open balances.
    """
    as_of = AS_OF_DATE.isoformat()
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT
                CASE
                    WHEN julianday(?) - julianday(due_date) <= 0 THEN 'Current'
                    WHEN julianday(?) - julianday(due_date) <= 30 THEN '1-30 days'
                    WHEN julianday(?) - julianday(due_date) <= 60 THEN '31-60 days'
                    WHEN julianday(?) - julianday(due_date) <= 90 THEN '61-90 days'
                    ELSE '90+ days'
                END AS bucket,
                COUNT(*) AS invoice_count,
                ROUND(SUM(amount - amount_paid), 2) AS open_balance
            FROM INVOICES
            WHERE status != 'Paid'
            GROUP BY bucket
            ORDER BY MIN(julianday(?) - julianday(due_date))
            """,
            (as_of, as_of, as_of, as_of, as_of),
        ).fetchall()

        buckets = _rows_to_dicts(rows)
        total_open = round(sum(b["open_balance"] for b in buckets), 2)
        return {
            "as_of_date": as_of,
            "buckets": buckets,
            "total_open_balance": total_open,
        }
    finally:
        conn.close()


@mcp.tool()
@_instrument_tool
def get_overdue_accounts() -> dict:
    """Get all customers with overdue invoices, sorted by total exposure.

    Returns each customer's ID, company name, account tier, number of
    overdue invoices, total overdue amount, and oldest overdue days.
    PII fields are masked.
    """
    as_of = AS_OF_DATE.isoformat()
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT
                c.customer_id,
                c.company_name,
                c.account_tier,
                c.contact_name,
                c.contact_email,
                COUNT(i.invoice_id) AS overdue_invoice_count,
                ROUND(SUM(i.amount - i.amount_paid), 2) AS total_overdue_amount,
                MAX(CAST(julianday(?) - julianday(i.due_date) AS INTEGER)) AS oldest_overdue_days
            FROM CUSTOMERS c
            JOIN INVOICES i ON c.customer_id = i.customer_id
            WHERE i.status IN ('Overdue', 'Partially Paid')
              AND julianday(?) - julianday(i.due_date) > 0
            GROUP BY c.customer_id
            ORDER BY total_overdue_amount DESC
            """,
            (as_of, as_of),
        ).fetchall()

        accounts = _rows_to_dicts(rows)
        return {"overdue_accounts": accounts, "count": len(accounts)}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tools — Collection workflow context
# ---------------------------------------------------------------------------


@mcp.tool()
@_instrument_tool
def get_collection_context(customer_id: str) -> dict:
    """Get disputes and promises-to-pay associated with a customer.

    Returns collection cases ordered newest first so agents can avoid
    inappropriate follow-up on disputed invoices or active payment promises.

    Args:
        customer_id: The customer ID (e.g. 'CUST-0001').
    """
    conn = _get_conn()
    try:
        customer = conn.execute(
            "SELECT customer_id FROM CUSTOMERS WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()
        if customer is None:
            return {"error": f"Customer {customer_id} not found."}
        rows = conn.execute(
            """
            SELECT case_id, invoice_id, customer_id, case_type, status,
                   details, promise_date, created_at
            FROM COLLECTION_CASES
            WHERE customer_id = ?
            ORDER BY created_at DESC, case_id
            """,
            (customer_id,),
        ).fetchall()
        cases = _rows_to_dicts(rows)
        return {"customer_id": customer_id, "cases": cases, "count": len(cases)}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tools — Draft communications (human-in-the-loop)
# ---------------------------------------------------------------------------


@mcp.tool()
@_instrument_tool
def save_draft_communication(
    customer_id: str,
    subject: str,
    body: str,
    tone: str,
) -> dict:
    """Save a draft collection communication for human review.

    The draft is saved with status 'pending_review'. It cannot be sent
    until a human explicitly approves it via approve_communication.

    Args:
        customer_id: The customer ID this communication is for.
        subject: The subject line of the communication.
        body: The full body text of the communication.
        tone: The tone used (e.g. 'direct', 'diplomatic', 'executive').
    """
    source_conn = _get_conn()
    try:
        customer = source_conn.execute(
            "SELECT customer_id FROM CUSTOMERS WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()
        if customer is None:
            return {"error": f"Customer {customer_id} not found."}
    finally:
        source_conn.close()

    draft_id = f"DRAFT-{uuid.uuid4().hex[:8].upper()}"
    created_at = datetime.now().astimezone().isoformat()
    if _draft_database_url():
        conn = _get_postgres_conn()
        try:
            _ensure_postgres_drafts_table(conn)
            conn.execute(
                """
                INSERT INTO draft_communications
                    (draft_id, customer_id, subject, body, tone, status, created_at)
                VALUES (%s, %s, %s, %s, %s, 'pending_review', %s)
                """,
                (draft_id, customer_id, subject, body, tone, created_at),
            )
            conn.commit()
        finally:
            conn.close()
    else:
        conn = _get_conn()
        try:
            _ensure_drafts_table(conn)
            conn.execute(
                """
                INSERT INTO DRAFT_COMMUNICATIONS
                    (draft_id, customer_id, subject, body, tone, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending_review', ?)
                """,
                (draft_id, customer_id, subject, body, tone, created_at),
            )
            conn.commit()
        finally:
            conn.close()
    return {
        "draft_id": draft_id,
        "status": "pending_review",
        "message": (
            f"Draft {draft_id} saved for customer {customer_id}. "
            "An authenticated human must review it before any external "
            "communication occurs."
        ),
    }


@mcp.tool()
@_instrument_tool
def list_draft_communications() -> dict:
    """List all draft communications and their current statuses.

    Returns each draft's ID, customer_id, subject, tone, status, creation
    timestamp, review timestamp, and authenticated approver identity.
    """
    if _draft_database_url():
        conn = _get_postgres_conn()
        try:
            _ensure_postgres_drafts_table(conn)
            rows = conn.execute(
                """
                SELECT draft_id, customer_id, subject, tone, status,
                       created_at, reviewed_at, approved_by
                FROM draft_communications
                ORDER BY created_at DESC
                """
            ).fetchall()
            drafts = [dict(row) for row in rows]
        finally:
            conn.close()
    else:
        conn = _get_conn()
        try:
            _ensure_drafts_table(conn)
            rows = conn.execute(
                """
                SELECT draft_id, customer_id, subject, tone, status,
                       created_at, reviewed_at, approved_by
                FROM DRAFT_COMMUNICATIONS
                ORDER BY created_at DESC
                """
            ).fetchall()
            drafts = _rows_to_dicts(rows)
        finally:
            conn.close()
    for draft in drafts:
        for field in ("created_at", "reviewed_at"):
            if isinstance(draft.get(field), datetime):
                draft[field] = draft[field].isoformat()
    return {"drafts": drafts, "count": len(drafts)}


@mcp.tool()
@_instrument_tool
def approve_communication(
    draft_id: str,
    approver_id: str,
    approval_token: str,
) -> dict:
    """Approve a draft after validating an authenticated human identity.

    Approval changes internal status only. The approver must provide the
    credential bound to their identity in APPROVER_CREDENTIALS_JSON.

    Args:
        draft_id: The draft ID to approve (e.g. 'DRAFT-A1B2C3D4').
        approver_id: Authenticated human identity recorded in the audit trail.
        approval_token: Secret approval credential; never returned or logged.
    """
    if not _approval_authorized(approver_id, approval_token):
        return {
            "error": (
                "Approval denied. A valid approver identity and its bound "
                "approval credential are required."
            )
        }

    reviewed_at = datetime.now().astimezone().isoformat()
    if _draft_database_url():
        conn = _get_postgres_conn()
        try:
            _ensure_postgres_drafts_table(conn)
            row = conn.execute(
                "SELECT status FROM draft_communications WHERE draft_id = %s",
                (draft_id,),
            ).fetchone()
            if row is None:
                return {"error": f"Draft {draft_id} not found."}
            status = row["status"]
            if status == "approved":
                return {"error": f"Draft {draft_id} is already approved."}
            if status != "pending_review":
                return {"error": f"Draft {draft_id} is not pending review."}
            conn.execute(
                """
                UPDATE draft_communications
                SET status = 'approved', reviewed_at = %s, approved_by = %s
                WHERE draft_id = %s AND status = 'pending_review'
                """,
                (reviewed_at, approver_id, draft_id),
            )
            conn.commit()
        finally:
            conn.close()
    else:
        conn = _get_conn()
        try:
            _ensure_drafts_table(conn)
            row = conn.execute(
                "SELECT status FROM DRAFT_COMMUNICATIONS WHERE draft_id = ?",
                (draft_id,),
            ).fetchone()
            if row is None:
                return {"error": f"Draft {draft_id} not found."}
            status = row["status"]
            if status == "approved":
                return {"error": f"Draft {draft_id} is already approved."}
            if status != "pending_review":
                return {"error": f"Draft {draft_id} is not pending review."}
            conn.execute(
                """
                UPDATE DRAFT_COMMUNICATIONS
                SET status = 'approved', reviewed_at = ?, approved_by = ?
                WHERE draft_id = ? AND status = 'pending_review'
                """,
                (reviewed_at, approver_id, draft_id),
            )
            conn.commit()
        finally:
            conn.close()
    return {
        "draft_id": draft_id,
        "status": "approved",
        "reviewed_at": reviewed_at,
        "approved_by": approver_id,
        "message": (
            f"Draft {draft_id} was approved by {approver_id} for human "
            "follow-up. No email or notice was sent by this system."
        ),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
