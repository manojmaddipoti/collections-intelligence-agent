@AGENTS.md

## Claude Code notes

- This project is also opened in Antigravity from time to time — keep
  AGENTS.md as the single source of truth. Only add Claude-Code-specific
  notes below this line; don't duplicate anything already in AGENTS.md.
- Use Plan Mode before touching the MCP masking layer or the
  human-in-the-loop approval gate — these two pieces carry the most weight
  for the "security features" judging criterion, so changes there should
  be reviewed before they're applied, not just run.
- When adding a new MCP tool, after it's working and reviewed, ask to
  capture the pattern as a Project Skill at
  `.claude/skills/add-mcp-tool/SKILL.md` rather than re-explaining the
  steps each time.
