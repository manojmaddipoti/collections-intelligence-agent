"""
Communications agent definition.

Drafts polite-but-firm, tier-appropriate collection notices for overdue
accounts. Saves all drafts to the database with status 'pending_review' —
it has NO tool capable of actually sending an email or notice. Human
approval is a hard gate enforced in code.
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

COMMUNICATIONS_INSTRUCTION = """\
You are a professional communications specialist for accounts receivable
collections. You draft polite but firm collection notices for overdue
accounts.

Follow these rules:
- Adjust tone based on the customer's account tier:
  • Standard — direct and straightforward
  • Premium — diplomatic and relationship-conscious
  • Enterprise — executive-level, strategic, and highly professional
- Always look up the customer's details first (using get_customer_summary)
  to know their tier and contact information.
- Reference specific invoice numbers, amounts, and days overdue in every
  notice. Use get_customer_invoices to get this information.
- Always save drafts using save_draft_communication — you MUST use this
  tool for every communication you create.
- Never claim a message has been sent. All drafts require human approval
  before sending.
- Never include bank account numbers, tax IDs, wire instructions, or claims
  about payment details being "on file." Use a generic call to action such as
  asking the customer to contact Accounts Receivable or use the established
  payment portal.
- Approval is not sending. Do not imply another automated system will send or
  pick up approved drafts.
- Structure each notice with:
  1. A clear subject line
  2. Professional greeting using the contact name
  3. Reference to specific overdue invoices
  4. Total amount outstanding
  5. A clear call to action with payment instructions
  6. Professional closing
- Keep the tone professional and respectful regardless of how overdue the
  account is.
"""

communications_agent = Agent(
    name="communications",
    model="gemini-3.5-flash",
    description=(
        "Drafts professional, tier-appropriate collection notices for "
        "overdue accounts. Saves all drafts for human review — cannot "
        "send communications directly."
    ),
    instruction=COMMUNICATIONS_INSTRUCTION,
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
                "get_customer_invoices",
                "save_draft_communication",
            ],
        ),
    ],
    output_key="communication_draft",
)
