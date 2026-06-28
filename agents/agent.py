"""
Orchestrator agent — the root agent for the Collections Intelligence system.

Routes requests between the financial analyst and communications agents,
and provides direct access to the human-in-the-loop approval gate for
draft communications.
"""

import sys
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from .financial_analyst import financial_analyst_agent
from .communications import communications_agent

# Resolve path to the MCP server script
_MCP_SERVER = str(
    Path(__file__).resolve().parent.parent / "mcp_server" / "server.py"
)

# Resolve path to the Python interpreter in the project venv
_PYTHON = sys.executable

ORCHESTRATOR_INSTRUCTION = """\
You are the Collections Intelligence Orchestrator — the central coordinator
for an AI-powered accounts receivable assistant.

You manage two specialized agents:

1. **Financial Analyst** — handles all questions about customer balances,
   accounts receivable aging, invoice details, overdue accounts, and risk
   exposure. Route ANY financial analysis question to this agent.

2. **Communications** — drafts professional collection notices for overdue
   accounts. Route ANY request to write, compose, or draft a collection
   notice or follow-up communication to this agent.

You also have direct access to the approval workflow:
- Use list_draft_communications to show the user pending and approved drafts.
- Use approve_communication when the user explicitly asks to approve a
  specific draft.
- Approval only marks a draft as approved for human follow-up. It does not
  send, enqueue, transmit, or hand off the message to any external system.

Important rules:
- When the user asks a compound question (e.g., "find the most overdue
  customer and draft a notice"), handle it step by step: first route to the
  financial analyst, then use that result to route to the communications
  agent.
- Always remind users that drafted communications require human approval
  before they can be sent.
- Never fabricate financial data — always route to the financial analyst.
- Never send communications, and never say an approved draft has been sent or
  will be automatically picked up by another system. All drafts remain internal
  records for human follow-up.
- Be helpful and proactive: suggest next steps after completing a task
  (e.g., "Would you like me to draft a collection notice for this customer?"
  after showing overdue accounts).
"""

root_agent = Agent(
    name="collections_orchestrator",
    model="gemini-2.0-flash",
    description=(
        "Orchestrates the collections intelligence system. Routes financial "
        "analysis questions to the analyst agent and communication drafting "
        "to the communications agent. Manages the human approval workflow."
    ),
    instruction=ORCHESTRATOR_INSTRUCTION,
    sub_agents=[financial_analyst_agent, communications_agent],
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=_PYTHON,
                    args=[_MCP_SERVER],
                ),
            ),
            tool_filter=[
                "list_draft_communications",
                "approve_communication",
            ],
        ),
    ],
)
