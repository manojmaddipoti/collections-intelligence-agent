# Collections Intelligence Agent Walkthrough

The core multi-agent system has been fully implemented according to the
`AGENTS.md` spec. The system is built on Google ADK and uses an MCP server for
data access.

## What was built

### 1. MCP Server & PII Masking
We created `mcp_server/server.py` using `FastMCP`. It provides 9 read/write
tools to interact with the SQLite database.

Crucially, **PII masking is enforced in Python, not in a prompt**.
The `_mask_customer_row()` helper ensures that any tool returning customer data
strips `tax_id` and `bank_account_number` before the data is serialized and
sent to the agent's context.

### 2. Specialized Sub-agents
We created two specialized sub-agents:
- **Financial Analyst (`agents/financial_analyst/agent.py`)**: Connected to
  the MCP server's read-only analysis tools (`get_ar_aging_report`,
  `get_overdue_accounts`, etc.). It computes exposure and identifies
  high-risk accounts.
- **Communications (`agents/communications/agent.py`)**: Connected to customer
  context tools and `save_draft_communication`. It cannot send messages
  directly.

### 3. Orchestrator & The HITL Gate
The **Orchestrator (`agents/agent.py`)** acts as the router. When you ask it to
"Draft a notice for the most overdue account", it:

1. Delegates to the Financial Analyst to find the account.
2. Delegates to the Communications agent to draft the notice.
3. The Communications agent saves the draft to the `DRAFT_COMMUNICATIONS` table with a `pending_review` status.

The Orchestrator itself holds the `approve_communication` tool. You can review
drafts via the CLI and explicitly ask the Orchestrator to approve one, which
flips the database status to `approved`. Approval is internal only: the system
does not send, enqueue, or hand off email.

## Verification Results

- Verified the virtual environment and dependencies (`google-adk`, `mcp`, `faker`).
- Verified the MCP server tool definitions and standard `StdioConnectionParams`
  implementation.
- Verified the database seed populated 25 customers, 140 invoices, 281 line
  items, 63 payments, and 0 draft communications.
- Verified the Dockerfile launches a reproducible ADK Web demo path.
- Verified the LLM model logic explicitly uses `gemini-3.5-flash`.
