"""
Financial analyst agent definition.

Answers natural-language questions about customer balances, AR aging,
invoice details, and risk exposure by calling MCP tools. Never fabricates
data — only reports what the tools return.
"""

import sys
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

# Resolve path to the MCP server script
_MCP_SERVER = str(
    Path(__file__).resolve().parent.parent.parent / "mcp_server" / "server.py"
)

# Resolve path to the Python interpreter in the project venv
_PYTHON = sys.executable

FINANCIAL_ANALYST_INSTRUCTION = """\
You are a financial analyst specializing in accounts receivable (AR) for a
collections department. You help finance teams understand customer balances,
analyze AR aging, identify high-risk overdue accounts, and compute exposure.

Use the available tools to query the database. Follow these rules:
- Never fabricate data — only report what the tools return.
- When asked about overdue accounts, always include the aging bucket and
  outstanding amount.
- When asked about a specific customer, include their account tier and
  credit limit for context.
- Format currency values clearly (e.g., $12,345.67).
- When presenting aging data, organize it by bucket (Current, 1-30 days,
  31-60 days, 61-90 days, 90+ days).
- If a customer has no overdue invoices, say so explicitly.
- Highlight any account where overdue balance exceeds 50% of their credit
  limit as high-risk.
"""

financial_analyst_agent = Agent(
    name="financial_analyst",
    model="gemini-2.0-flash",
    description=(
        "Specializes in accounts receivable analysis: customer balances, "
        "AR aging reports, invoice details, overdue accounts, and risk "
        "exposure assessment."
    ),
    instruction=FINANCIAL_ANALYST_INSTRUCTION,
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=_PYTHON,
                    args=[_MCP_SERVER],
                ),
            ),
            tool_filter=[
                "get_customer_summary",
                "list_customers",
                "get_customer_invoices",
                "get_ar_aging_report",
                "get_overdue_accounts",
                "get_invoice_details",
            ],
        ),
    ],
    output_key="financial_analysis",
)
