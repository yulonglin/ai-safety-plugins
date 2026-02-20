---
name: audit-docs
description: Audit project documentation for staleness, gaps, and inconsistencies with code.
---

# Audit Docs

Check project documentation against recent code changes to find stale or missing docs.

## When to Use This Skill

- When the SessionStart hook warns docs are stale
- Before a paper submission or release
- After a burst of code changes
- Periodically (every 2-4 weeks during active development)

## Instructions

### 1. Gather Recent Changes

```bash
git log --since='2 weeks ago' --stat -- src/ configs/ scripts/
```

Note which files changed, what was added/removed, and any new modules or configs.

### 2. Read Current Documentation

Read the following files (delegate heavy reads to Gemini CLI agent if >500 lines total):

- `CLAUDE.md` — project quick reference
- `AGENTS.md` — agent configuration (if exists)
- `docs/core/CLI_REFERENCE.md` — CLI examples
- `docs/core/TROUBLESHOOTING.md` — known issues
- `docs/methods/` — detection method docs
- `docs/experiments/` — experiment records (scan frontmatter only)
- `specs/RESEARCH_SPEC.md` — research priorities

### 3. Cross-Reference Against Checklist

Use `references/audit-checklist.md` to systematically check each area. For each item, note:
- **OK**: Doc matches code
- **STALE**: Doc references something that changed
- **MISSING**: Code has no corresponding doc
- **ABANDONED**: Experiment record with `status: active` but no log entries in 2+ weeks

### 4. Interview User

Present findings organized by severity:
1. **Breaking** — CLI examples that would fail if copy-pasted
2. **Misleading** — Descriptions that no longer match behavior
3. **Missing** — New features/methods with no docs
4. **Housekeeping** — Minor updates, stale experiment records

Ask the user which items to fix and any context you're missing.

### 5. Propose and Apply Edits

For each approved fix:
- Show the specific edit (old text -> new text)
- Apply with the Edit tool
- For large doc rewrites, delegate to a subagent

### 6. Update Experiment Records

For experiments with `status: active` but no activity in 2+ weeks:
- Ask user: still active, completed, or abandoned?
- Update status accordingly
- Move abandoned experiments to `status: archived` with a note

## Delegation Strategy

- **Gemini CLI**: For reading large doc files (>500 lines combined) and cross-referencing against code
- **Direct**: For git log analysis, small file reads, and applying edits

## Notes

- Run this skill BEFORE `/reflect` — audit-docs catches structural issues, reflect catches content insights
- Don't auto-fix anything — always present findings and get user approval
- Focus on actionable items: skip cosmetic issues unless they cause confusion
