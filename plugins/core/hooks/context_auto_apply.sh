#!/usr/bin/env bash
# SessionStart hook: auto-apply context.yaml if present

# Fast path: use Rust binary if available
claude-tools context-apply 2>/dev/null && exit 0

# Shell fallback
CONTEXT_FILE=".claude/context.yaml"
if [ -f "$CONTEXT_FILE" ]; then
    claude-context 2>/dev/null
fi
exit 0  # Don't block session start
