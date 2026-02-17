#!/bin/bash
# Warn when TaskOutput is used — results arrive via notifications instead
# Companion to task_force_background.sh
# See: https://github.com/anthropics/claude-code/issues/16789

[[ "${CLAUDE_TASK_FORCE_BG:-1}" == "0" ]] && exit 0

printf '%s\n' '{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "TaskOutput returns raw JSONL (#16789). Wait for <task-notification> with <result> tag instead. The background agent will notify you when complete."
  }
}'
