#!/bin/bash
# PostToolUse hook: Guide Claude to search when Read fails with file-not-found
#
# Config:
#   CLAUDE_RESOLVE_PATH=0  — disable entirely

[[ "${CLAUDE_RESOLVE_PATH:-1}" == "0" ]] && exit 0

# Fast path: Rust binary
if command -v claude-tools >/dev/null 2>&1; then
    claude-tools resolve-file-path
    exit $?
fi

# Shell fallback
command -v jq >/dev/null 2>&1 || exit 0
INPUT=$(cat)

TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // ""')
[[ "$TOOL_NAME" != "Read" ]] && exit 0

RESPONSE=$(printf '%s' "$INPUT" | jq -r '
  (.tool_response | if type == "object" then (.error // "") else (. // "") end)
')
if ! printf '%s' "$RESPONSE" | grep -qiE 'does not exist|no such file|ENOENT|not found'; then
    exit 0
fi

FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // ""')
BASENAME=$(basename "$FILE_PATH" 2>/dev/null)
DIRNAME=$(dirname "$FILE_PATH" 2>/dev/null | xargs basename 2>/dev/null)

[[ -z "$BASENAME" ]] && exit 0

if [[ -n "$DIRNAME" && "$DIRNAME" != "." && "$DIRNAME" != "/" ]]; then
    HINT="Glob(\"**/$DIRNAME/$BASENAME\") first, then Glob(\"**/$BASENAME\") if no results"
else
    HINT="Glob(\"**/$BASENAME\") or fd -H \"$BASENAME\""
fi

jq -n --arg path "$FILE_PATH" --arg hint "$HINT" '{
    systemMessage: ("File not found at " + $path + ". REQUIRED: Search before giving up.\n1. " + $hint + "\n2. Single match → Read it. Multiple → list candidates and ask user.\n3. Zero matches → ask user for correct path or repo.\nNever silently skip a referenced file.")
}'
