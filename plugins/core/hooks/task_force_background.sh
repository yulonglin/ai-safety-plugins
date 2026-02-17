#!/bin/bash
# Force Task tool calls to background mode
# Workaround for: https://github.com/anthropics/claude-code/issues/16789
#
# Config:
#   CLAUDE_TASK_FORCE_BG=0        — disable entirely
#   CLAUDE_TASK_FORCE_BG_DEBUG=1  — enable stderr logging

[[ "${CLAUDE_TASK_FORCE_BG:-1}" == "0" ]] && exit 0
command -v jq &>/dev/null || exit 0

INPUT=$(cat)

debug() { [[ "${CLAUDE_TASK_FORCE_BG_DEBUG:-0}" == "1" ]] && printf 'task_force_bg: %s\n' "$*" >&2; }

# Validate JSON input
if ! printf '%s' "$INPUT" | jq -e '.' &>/dev/null; then
  debug "invalid JSON input, skip"
  exit 0
fi

# Defensive: verify this is a Task tool call (in case matcher misconfigured)
TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null)
if [[ "$TOOL_NAME" != "Task" ]]; then
  debug "not a Task call (got: $TOOL_NAME), skip"
  exit 0
fi

# Skip if already backgrounded
if printf '%s' "$INPUT" | jq -e '.tool_input.run_in_background == true' &>/dev/null; then
  debug "already backgrounded, skip"
  exit 0
fi

# Skip resume calls (agent already running in background)
if printf '%s' "$INPUT" | jq -e '.tool_input.resume != null' &>/dev/null; then
  debug "resume call, skip"
  exit 0
fi

# Force background mode
# Note: updatedInput REPLACES tool_input entirely — must merge with + to preserve all fields
# (.tool_input // {}) guards against null tool_input (same bug class as the jq -n fix)
RESULT=$(printf '%s' "$INPUT" | jq '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    updatedInput: ((.tool_input // {}) + { run_in_background: true }),
    additionalContext: "Task auto-backgrounded (#16789). Results arrive via <task-notification>. Do NOT use TaskOutput — it returns raw JSONL. Agents may show failed due to #24181 — verify output exists before retrying."
  }
}' 2>/dev/null) || {
  debug "jq transform failed, allowing unmodified"
  exit 0
}

debug "forcing background mode"
printf '%s\n' "$RESULT"
