---
name: externalise-handover
description: Externalise important parts of the current conversation into an .md file for handover.
---

# Externalise / Handover tasks

## Instructions

Externalise important parts of the current conversation into an `.md` file to hand over to another colleague or agent.

**Focus on:**
- Tasks to do next.
- What's been accomplished (exact commands run, inputs/args, outputs including file paths).
- Bugs encountered.
- Key areas of uncertainties.
- User instructions and clarifications, touched up to be clearer.

**Context:** Use any additional context provided in the arguments.

**Redact before writing.** Scan for secrets and PII before the file is saved — API keys, tokens, passwords, private URLs with embedded credentials, personal contact details. Replace with a placeholder (e.g. `<REDACTED: API key>`) rather than omitting silently, so the next reader knows something was removed and why.

**Reference, don't duplicate.** If the conversation already produced a spec, plan, PR, commit, or issue that covers a point in full, link or path-reference it instead of re-pasting its content. Only inline the specific delta (what changed since, what's still open) — the handover file should be a map to existing artifacts, not a second copy of them.
