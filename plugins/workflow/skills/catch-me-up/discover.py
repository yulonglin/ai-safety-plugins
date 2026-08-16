#!/usr/bin/env python3
"""Discover active projects across vault + code dirs for the catch-me-up skill.

Deterministic discovery only — no judgment calls. Emits JSON; the skill's
SKILL.md instructions do the reading/synthesis on top of this.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EXCLUDE_DIRS = {"node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".cache"}


def run(cmd, cwd=None):
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def days_ago(iso_date):
    if not iso_date:
        return None
    try:
        d = datetime.strptime(iso_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - d).days


def find_git_repos(root, max_depth=4):
    root = Path(root)
    if not root.is_dir():
        return []
    repos = []
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".")]
        current = Path(dirpath)
        if (current / ".git").exists():
            repos.append(current)
            dirnames[:] = []  # don't descend into a repo's own subdirs
            continue
        depth = len(current.relative_to(root).parts)
        if depth >= max_depth:
            dirnames[:] = []
    return repos


def repo_signals(path):
    last_commit = run(["git", "log", "-1", "--format=%cd", "--date=short"], cwd=path)
    branch = run(["git", "branch", "--show-current"], cwd=path)
    claude_md = path / "CLAUDE.md"
    has_learnings = claude_md.exists() and "## Learnings" in claude_md.read_text(errors="ignore")
    pr_json = run(
        [
            "gh", "pr", "list", "--author", "@me", "--state", "open",
            "--json", "number,title,url,createdAt,updatedAt,isDraft",
        ],
        cwd=path,
    )
    try:
        open_prs = json.loads(pr_json) if pr_json else []
    except json.JSONDecodeError:
        open_prs = []
    for pr in open_prs:
        pr["days_since_update"] = days_ago(pr.get("updatedAt", "")[:10]) if pr.get("updatedAt") else None
    claims_dir = path / ".agent-claims"
    claims = [str(c) for c in claims_dir.glob("*")] if claims_dir.is_dir() else []
    return {
        "last_commit_date": last_commit or None,
        "days_since_commit": days_ago(last_commit),
        "branch": branch or None,
        "claude_md_learnings": has_learnings,
        "plans_dir": (path / "plans").is_dir(),
        "specs_dir": (path / "specs").is_dir(),
        "open_prs": open_prs,
        "agent_claims": claims,
    }


def vault_signals(path):
    program_md = path / "program.md"
    status_md = path / "status.md"
    mtimes = [
        f.stat().st_mtime
        for f in path.rglob("*")
        if f.is_file() and ".git" not in f.parts
    ]
    last_mtime = max(mtimes) if mtimes else None
    last_active = (
        datetime.fromtimestamp(last_mtime, tz=timezone.utc).date().isoformat()
        if last_mtime
        else None
    )
    return {
        "program_md": str(program_md) if program_md.exists() else None,
        "status_md": str(status_md) if status_md.exists() else None,
        "last_active_date": last_active,
        "days_since_active": days_ago(last_active),
    }


def main():
    since_days = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 21
    code_dir = Path(os.environ.get("CODE_DIR", str(Path.home() / "code")))
    vault_dir = Path.home() / "vault"

    projects = []

    for kind, base in (
        ("vault-research", vault_dir / "research"),
        ("vault-tooling", vault_dir / "tooling"),
    ):
        if not base.is_dir():
            continue
        for sub in sorted(base.iterdir()):
            if not sub.is_dir():
                continue
            sig = vault_signals(sub)
            recency = sig["days_since_active"]
            if recency is not None and recency > since_days:
                continue
            projects.append({"name": sub.name, "path": str(sub), "kind": kind, **sig})

    for repo in find_git_repos(code_dir):
        sig = repo_signals(repo)
        recency = sig["days_since_commit"]
        if recency is not None and recency > since_days:
            continue
        projects.append({"name": repo.name, "path": str(repo), "kind": "repo", **sig})

    projects.sort(key=lambda p: p.get("days_since_commit", p.get("days_since_active")) or 999)
    print(json.dumps({"since_days": since_days, "projects": projects}, indent=2))


if __name__ == "__main__":
    main()
