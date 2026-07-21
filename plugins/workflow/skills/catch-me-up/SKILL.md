---
name: catch-me-up
description: Cross-project status digest for returning to work after time away. Triggers on "catch me up", "where are we", "what's going on across my projects", or when the user wants to reorient across multiple repos/research projects at once. Not for single-repo status (use git log / CLAUDE.md Learnings directly for that).
argument-hint: "[since-days] or [project-name-substring]"
---

# Catch Me Up

Produces a cross-project status report: goals, what's done, what's left, and what needs the user's attention — grounded in real files on disk, not invented.

## 1. Discover active projects

Run the discovery script:

```bash
${CLAUDE_PLUGIN_ROOT}/skills/catch-me-up/discover.py [since-days]
```

- If `$1` (the skill argument) is purely numeric, pass it through as `since-days` (default 21).
- If `$1` is a non-numeric string, treat it as a project-name substring filter: run discovery with the default window, then keep only projects whose `name` or `path` contains the substring (case-insensitive).
- The script scans `~/vault/research/*`, `~/vault/tooling/*` (vault-convention projects — `program.md`/`status.md`), and git repos under `$CODE_DIR` (default `~/code`), keeping only ones active within the window. It shells out to `git` and `gh pr list` per repo — this can take a few seconds for many repos, that's expected.
- If the script returns zero projects, say so plainly and stop — do not invent activity. Suggest widening the window (`catch-me-up 60`).

## 2. Gather detail per project

For each project in the discovery output, read its actual detail source — do not summarize from memory or guess:

- **Vault-convention projects** (`program_md`/`status_md` non-null): Read `program.md` for the `## Active` section (current goal) and `## Specs / plans in flight` section (what's queued). Read the tail of `status.md` (newest entries are last) for recent activity. Grep both for `Open Decision #` and `blocked` — these are the user's own convention for flagging genuine blockers; treat every match as a "needs attention" item.
- **Repos without the vault convention**: Read the `## Learnings` section of `CLAUDE.md` if `claude_md_learnings` is true. Run `git log --oneline -10` in the repo for recent activity. There is no explicit "goal" statement for these — infer one from repo name, recent commit messages, and README if present, and mark it explicitly as **inferred, not stated**.
- **Any project with `open_prs` non-empty**: these are near-certain "needs attention" items (a PR sitting open needs either review, merge, or closing). Use `days_since_update` to distinguish fresh (< 3 days, probably just filed) from stale (> 7 days, may be abandoned or forgotten) — flag stale ones explicitly.
- **Any project with `agent_claims` non-empty**: check each claim file's `since:` timestamp. If recent (< 2h), another agent may currently be working in that repo — note this, don't treat it as a blocker on its own.

If there are more than ~4 projects needing detail gathering, dispatch one subagent per project in parallel via the `Agent` tool (not the `Workflow` tool — this is a bounded per-project read task, not multi-agent orchestration). Give each subagent the project's discovery record and the file paths to read; ask it to return goal / done-recently / still-to-do / needs-attention as plain text, with confidence noted for anything inferred.

## 3. Synthesize the report

Structure, per project:

- **Goal** — one line. Mark `(inferred)` if not explicitly stated anywhere.
- **Done recently** — 2-4 bullets grounded in status.md entries / commit log, most recent first.
- **Still to do** — from `program.md` § Specs / plans in flight, or left as "not tracked" if there's no source for it. Never invent a todo list.
- **Needs your attention** — Open Decision markers, stale/open PRs, anything genuinely blocking. Empty is fine and should be stated as empty, not padded.

At the top of the report, before the per-project sections, add a flat **Needs your attention** rollup across all projects — this is what the user reads first.

Mark confidence per project: **high** (vault-convention project with recent status.md entries), **medium** (repo with CLAUDE.md Learnings + recent commits), **low** (repo with only commit history, goal inferred).

Do not invent blockers, deadlines, or next steps that aren't grounded in a file. If a project's state is genuinely unclear, say so rather than guessing.

## 4. Deliver

- Write the report to `$TMPDIR/catch-me-up-$(utc_timestamp).md`.
- Call `SendUserFile` with the full path, `status: "normal"` (this is a direct response to the user's request, not unprompted), `display: "render"`.
- In chat, give a short BLUF: the top 2-3 "needs attention" items across all projects, then the report's full file path (per the vault/codebase reporting convention — always state the full path, never just a filename).
