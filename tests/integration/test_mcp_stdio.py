"""End-to-end tests for every tool over the real MCP stdio transport."""

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PATH = Path(__file__).resolve().parents[2] / "mcp_server" / "server.py"


def _payload(result: Any) -> dict:
    """Decode a FastMCP dictionary result from its text content."""
    assert result.isError is False
    return json.loads(result.content[0].text)


@pytest.mark.asyncio
async def test_all_tools_over_stdio(seeded_db: Path) -> None:
    """Call every registered MCP tool through a subprocess-backed session."""
    env = dict(os.environ)
    env.update(
        {
            "AR_DATABASE_PATH": str(seeded_db),
            "APPROVER_CREDENTIALS_JSON": (
                '{"reviewer@example.com":"integration-approval-token"}'
            ),
        }
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_PATH)],
        env=env,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            registered = {tool.name for tool in (await session.list_tools()).tools}
            assert registered == {
                "get_customer_summary",
                "list_customers",
                "get_customer_invoices",
                "get_invoice_details",
                "get_ar_aging_report",
                "get_overdue_accounts",
                "get_collection_context",
                "save_draft_communication",
                "list_draft_communications",
                "approve_communication",
            }

            summary = _payload(
                await session.call_tool(
                    "get_customer_summary", {"customer_id": "CUST-0001"}
                )
            )
            assert summary["customer"]["tax_id"] == "***MASKED***"

            customers = _payload(await session.call_tool("list_customers", {}))
            assert customers["count"] == 25

            invoices = _payload(
                await session.call_tool(
                    "get_customer_invoices", {"customer_id": "CUST-0001"}
                )
            )
            assert invoices["count"] > 0

            details = _payload(
                await session.call_tool(
                    "get_invoice_details", {"invoice_id": "INV-0001-01"}
                )
            )
            assert details["line_items"]

            aging = _payload(await session.call_tool("get_ar_aging_report", {}))
            assert aging["total_open_balance"] > 0

            overdue = _payload(await session.call_tool("get_overdue_accounts", {}))
            assert overdue["count"] > 0

            context = _payload(
                await session.call_tool(
                    "get_collection_context", {"customer_id": "CUST-0001"}
                )
            )
            assert context["cases"][0]["case_type"] == "dispute"

            draft = _payload(
                await session.call_tool(
                    "save_draft_communication",
                    {
                        "customer_id": "CUST-0001",
                        "subject": "Integration test",
                        "body": "Test body",
                        "tone": "direct",
                    },
                )
            )
            assert draft["status"] == "pending_review"

            drafts = _payload(
                await session.call_tool("list_draft_communications", {})
            )
            assert drafts["count"] == 1

            denied = _payload(
                await session.call_tool(
                    "approve_communication",
                    {
                        "draft_id": draft["draft_id"],
                        "approver_id": "reviewer@example.com",
                        "approval_token": "wrong",
                    },
                )
            )
            assert "error" in denied

            approved = _payload(
                await session.call_tool(
                    "approve_communication",
                    {
                        "draft_id": draft["draft_id"],
                        "approver_id": "reviewer@example.com",
                        "approval_token": "integration-approval-token",
                    },
                )
            )
            assert approved["approved_by"] == "reviewer@example.com"
            assert "No email or notice was sent" in approved["message"]
