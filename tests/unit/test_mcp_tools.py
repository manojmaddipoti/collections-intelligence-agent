"""Unit tests for every Collections Intelligence MCP tool."""

import pytest

from mcp_server import server


def test_get_customer_summary_masks_pii(seeded_db: object) -> None:
    """Customer summaries must redact sensitive source fields."""
    result = server.get_customer_summary("CUST-0001")
    customer = result["customer"]
    assert customer["tax_id"] == "***MASKED***"
    assert customer["bank_account_number"] == "***MASKED***"
    assert server.get_customer_summary("NOPE") == {
        "error": "Customer NOPE not found."
    }


def test_list_customers_masks_every_row(seeded_db: object) -> None:
    """Customer lists must be complete and PII-safe."""
    result = server.list_customers()
    assert result["count"] == 25
    assert all(c["tax_id"] == "***MASKED***" for c in result["customers"])
    assert all(
        c["bank_account_number"] == "***MASKED***" for c in result["customers"]
    )


def test_get_customer_invoices_returns_aging(seeded_db: object) -> None:
    """Invoice lists must include deterministic overdue-day calculations."""
    result = server.get_customer_invoices("CUST-0001")
    assert result["count"] > 0
    assert all("days_overdue" in invoice for invoice in result["invoices"])
    assert server.get_customer_invoices("NOPE")["count"] == 0


def test_get_invoice_details_returns_related_rows(seeded_db: object) -> None:
    """Invoice detail must include line items and payment history."""
    result = server.get_invoice_details("INV-0001-01")
    assert result["invoice"]["invoice_id"] == "INV-0001-01"
    assert result["line_items"]
    assert isinstance(result["payments"], list)
    assert server.get_invoice_details("NOPE") == {
        "error": "Invoice NOPE not found."
    }


def test_get_ar_aging_report_reconciles_total(seeded_db: object) -> None:
    """The aging total must equal the sum of its buckets."""
    result = server.get_ar_aging_report()
    assert result["as_of_date"] == "2026-06-20"
    assert result["total_open_balance"] == round(
        sum(bucket["open_balance"] for bucket in result["buckets"]),
        2,
    )
    assert {bucket["bucket"] for bucket in result["buckets"]} == {
        "Current",
        "1-30 days",
        "31-60 days",
        "61-90 days",
        "90+ days",
    }


def test_get_overdue_accounts_is_ranked(seeded_db: object) -> None:
    """Overdue accounts must be returned in descending exposure order."""
    result = server.get_overdue_accounts()
    amounts = [
        account["total_overdue_amount"] for account in result["overdue_accounts"]
    ]
    assert result["count"] > 0
    assert amounts == sorted(amounts, reverse=True)
    assert all(account["oldest_overdue_days"] > 0 for account in result["overdue_accounts"])


@pytest.mark.parametrize(
    ("customer_id", "case_type", "status"),
    [
        ("CUST-0001", "dispute", "open"),
        ("CUST-0002", "promise_to_pay", "active"),
        ("CUST-0003", "promise_to_pay", "broken"),
    ],
)
def test_get_collection_context_returns_workflow_cases(
    seeded_db: object,
    customer_id: str,
    case_type: str,
    status: str,
) -> None:
    """Collection context must expose deterministic dispute/promise states."""
    result = server.get_collection_context(customer_id)
    assert any(
        case["case_type"] == case_type and case["status"] == status
        for case in result["cases"]
    )
    assert server.get_collection_context("NOPE") == {
        "error": "Customer NOPE not found."
    }


def test_save_draft_communication_is_pending(seeded_db: object) -> None:
    """Draft creation must validate customers and start pending review."""
    assert server.save_draft_communication(
        "NOPE", "Subject", "Body", "direct"
    ) == {"error": "Customer NOPE not found."}
    result = server.save_draft_communication(
        "CUST-0001", "Subject", "Body", "direct"
    )
    assert result["status"] == "pending_review"
    assert result["draft_id"].startswith("DRAFT-")


def test_list_draft_communications_hides_body(seeded_db: object) -> None:
    """Draft lists must expose audit metadata without message bodies."""
    created = server.save_draft_communication(
        "CUST-0001", "Subject", "Sensitive body", "direct"
    )
    result = server.list_draft_communications()
    assert result["count"] == 1
    assert result["drafts"][0]["draft_id"] == created["draft_id"]
    assert "body" not in result["drafts"][0]
    assert result["drafts"][0]["approved_by"] is None


def test_approve_communication_requires_authenticated_human(
    seeded_db: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approval must reject missing credentials and audit a valid reviewer."""
    draft = server.save_draft_communication(
        "CUST-0001", "Subject", "Body", "direct"
    )
    denied = server.approve_communication(draft["draft_id"], "reviewer", "wrong")
    assert "error" in denied

    monkeypatch.setenv(
        "APPROVER_CREDENTIALS_JSON",
        '{"reviewer@example.com":"test-approval-token"}',
    )
    result = server.approve_communication(
        draft["draft_id"],
        "reviewer@example.com",
        "test-approval-token",
    )
    assert result["status"] == "approved"
    assert result["approved_by"] == "reviewer@example.com"
    assert "No email or notice was sent" in result["message"]
    assert "already approved" in server.approve_communication(
        draft["draft_id"],
        "reviewer@example.com",
        "test-approval-token",
    )["error"]
