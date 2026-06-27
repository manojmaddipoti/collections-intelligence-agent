# Demo Video Outline

Target length: 4 to 5 minutes.

## 0:00 - 0:30 Problem And Value

- Introduce the Agents for Business track.
- Explain the accounts receivable pain: aging analysis, risk prioritization, and collection follow-up drafting are repetitive but sensitive.
- State the value: faster analysis, consistent drafts, and a human approval gate.

## 0:30 - 1:20 Architecture

- Show `docs/media/architecture.svg`.
- Explain the ADK orchestrator, financial analyst agent, communications agent, MCP server, and SQLite database.
- Mention that all data is synthetic.

## 1:20 - 2:40 Live Demo

- Run `adk web agents/`.
- Ask: `Who are our top 3 most overdue accounts?`
- Show the financial analyst response with aging and overdue exposure.
- Ask: `Draft a collection notice for the highest overdue account.`
- Show that the communications agent saves a draft as `pending_review`.

## 2:40 - 3:30 Safety

- Show `mcp_server/server.py`.
- Point to `_mask_customer_row()` and explain server-side masking.
- Point to the tool filters in the agent files and explain that the communications agent cannot send email.
- Approve a draft and state clearly that approval only updates internal status.

## 3:30 - 4:20 Build And Deployability

- Show `Dockerfile`, `.env.example`, and setup commands.
- Mention ADK, MCP, SQLite, Faker, and Gemini.
- Mention that the project was built and reviewed with agent-assisted coding workflows such as Antigravity/Codex and the Agents CLI style workflow.

## 4:20 - 5:00 Close

- Summarize the business impact.
- Show the GitHub repository and README.
- End with the project link.

## Recording Checklist

- Keep the video under 5 minutes.
- Upload to YouTube.
- Attach the YouTube video to the Kaggle Writeup media gallery.
- Attach `docs/media/cover.svg` or an exported PNG as the cover image.
- Add the public GitHub URL as the project link if no live demo URL is available.
