---
name: status-report
description: Generate a capstone status report from recent git history. Use when the user asks for a status report, weekly update, progress summary, or reflection for Jeremy, Alpha, or the team.
---

# Status report

Arguments (optional): a start date or period (default: the last 7 days) and a teammate
(Jeremy, Alpha, or team).

Delegate this to the `status-reporter` subagent, which runs on Haiku to keep it cheap, using
the Agent tool. Pass along the date range and teammate. Don't read the git history yourself.

When the agent returns, show the report to the user as-is and offer to save it to
`docs/status-reports/<YYYY-MM-DD>-<author>.md`. Only save it if they say yes.
