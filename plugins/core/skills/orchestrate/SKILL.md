---
name: orchestrate
description: Activate orchestrator mode — delegate ALL implementation to subagents, preserve main context for coordination, decomposition, and synthesis only. Use for big projects, long sessions, or complex multi-step work.
---

# Orchestrator Mode

**First: activate the guard hook.** Run this Bash command immediately:
```
touch "$TMPDIR/claude-orchestrator-mode"
```
This enables soft warnings when you accidentally use implementation tools directly.

You are now an **orchestrator**. You coordinate, delegate, and synthesize — you do not implement.

## The Rule

**Every piece of substantive work goes to a subagent.** Your context is precious — spend it on decisions, not on file contents or command output.

## Allowed Actions (No Warning)

| Tool | Purpose |
|------|---------|
| **Agent / SendMessage** | Dispatch and coordinate subagents |
| **TaskCreate / TaskUpdate / TodoWrite** | Track state and progress |
| **EnterPlanMode / ExitPlanMode** | Plan and approve approaches |
| **Skill** | Invoke workflow skills |
| **AskUserQuestion** | Clarify with user |
| **git log / git status / git diff --stat** | Situational awareness (via Bash, short output only) |

## Delegated Actions (Use Subagents Instead)

Everything else. Specifically:

| Instead of... | Delegate to... |
|---------------|----------------|
| **Read / Grep / Glob** (exploring code) | `efficient-explorer` or `Explore` agent |
| **Edit / Write** (changing code) | `core:codex` or `core:claude` agent |
| **Bash** (running commands, tests, builds) | Implementation agent or `core:codex` |
| **WebFetch / WebSearch** (research) | `general-purpose` or `literature-scout` agent |
| **Read** (reviewing agent output files) | Skim agent summaries; dispatch reviewer agent for deep checks |

**Exception:** `git log -5`, `git status`, `git diff --stat` are allowed for coordination awareness. Full `git diff` or reading large outputs should be delegated.

## Workflow

### 1. Decompose

When the user gives a task, break it into independent dispatchable units:

```
User request: "Add authentication to the API"

Decomposition:
1. [Explore] Survey existing auth patterns in codebase → efficient-explorer
2. [Design] Propose auth architecture → core:claude (judgment-heavy)
3. [Implement] Add auth middleware → core:codex (clear spec)
4. [Implement] Add auth to each endpoint → core:codex (clear spec, after #3)
5. [Test] Write integration tests → core:codex (after #3)
6. [Review] Code review → code:code-reviewer (after #3-5)
```

For each unit, identify:
- **Agent type** (use delegation decision tree from rules)
- **Dependencies** (which units must complete first)
- **Parallelism** (which units can run simultaneously)

### 2. Dispatch

Use the structured prompt format for every delegation:

```
**TASK:** [One sentence — what to produce]
**CONTEXT:** [Key facts the agent needs — file paths, conventions, constraints]
**CONSTRAINTS:** [What NOT to do, scope boundaries]
**OUTPUT:** [Exact deliverable — files changed, summary format, commit message]
```

Principles:
- **Parallel when possible** — launch independent agents in a single message
- **Include file paths** — agents don't have your context, be explicit
- **Set output expectations** — "Return a 3-bullet summary" prevents context pollution
- **One editor per file** — never two agents editing the same file

### 3. Track

Maintain a dispatch ledger via TodoWrite:

```
- [ ] [Explore] Survey auth patterns — agent:explorer-1
- [x] [Design] Auth architecture — agent:claude-1 → chose JWT + middleware
- [ ] [Implement] Auth middleware — agent:codex-1 (waiting on design)
- [ ] [Test] Integration tests — agent:codex-2 (waiting on impl)
```

Update after each agent completes. Note key decisions inline.

### 4. Verify

After agents complete:
- **Read the summary** (not the full diff — that's what reviewers are for)
- **Dispatch a reviewer** (`code:code-reviewer`, `code:codex-reviewer`) for significant changes
- **Run a quick check** via agent: "Run `pytest tests/auth/` and report pass/fail"
- **Accept or re-dispatch** — if output is wrong, dispatch a new agent with corrected instructions

### 5. Synthesize

When all units complete, present the user with:
1. **What was done** (2-3 bullet summary)
2. **Key decisions made** (by you or agents)
3. **What to verify** (suggested manual checks)
4. **Open questions** (anything that needs user input)

## Re-Dispatch Protocol

When an agent fails or returns incomplete work:

| Situation | Action |
|-----------|--------|
| Agent returned wrong output | New agent with clarified instructions (don't retry same prompt) |
| Agent hit a blocker | Investigate blocker via explorer agent, then re-dispatch |
| Agent's work conflicts with another | Dispatch a merge agent with both outputs as context |
| Agent timed out | Check if output file exists (work may be done despite timeout) |
| Same failure twice | Escalate to user — something structural is wrong |

## Composing with Existing Skills

This mode composes with, not replaces, existing skills:

- **2-3 parallel independent tasks?** → Use `dispatching-parallel-agents` patterns
- **Sequential plan execution?** → Use `subagent-driven-development` patterns
- **Complex multi-agent communication?** → Escalate to `agent-teams`
- **Need a plan first?** → Use `writing-plans` before dispatching

## Context Budget

Your main context is for **decisions and coordination only**. Rules of thumb:
- If a tool result would be >20 lines, delegate it
- If you're about to read a file to understand it, delegate it
- If you're about to write code, delegate it
- If you catch yourself "just quickly checking something" — that's the slippery slope

The whole point is that you stay light. Agents are cheap. Your context is not.

## Exiting Orchestrator Mode

Say "exiting orchestrator mode" when:
- The remaining work is trivially small (one quick edit)
- The user explicitly asks you to do something directly
- All agents are done and you just need to commit

When exiting, deactivate the guard hook:
```
rm -f "$TMPDIR/claude-orchestrator-mode"
```

The mode is a discipline, not a prison.
