#!/usr/bin/env bash
# Generate a ✅ session title for /done skill.
# Outputs the title to stdout — caller uses /rename to apply it.
set -euo pipefail

# Source secrets (API key not in Bash tool environment)
DOT_DIR="${DOT_DIR:-$HOME/code/dotfiles}"
[[ -f "$DOT_DIR/.secrets" ]] && source "$DOT_DIR/.secrets"

# Find current transcript (most recently modified .jsonl in project dir)
PROJECT_DIR="$HOME/.claude/projects/$(pwd | sed 's|/|-|g')"
TRANSCRIPT=$(/bin/ls -t "$PROJECT_DIR"/*.jsonl 2>/dev/null | head -1 || true)
[[ -z "$TRANSCRIPT" ]] && echo "ERROR: No transcript found in $PROJECT_DIR" >&2 && exit 1

# Check for existing name
EXISTING=$(jq -r 'select(.type == "custom-title") | .customTitle // empty' "$TRANSCRIPT" 2>/dev/null || true)
EXISTING="${EXISTING##*$'\n'}"  # keep last line only

if [[ "$EXISTING" == "✅ "* ]]; then
  echo "Already done: $EXISTING" >&2
  exit 0
elif [[ -n "$EXISTING" ]]; then
  NAME="$EXISTING"
else
  # Generate name from first user messages via Haiku
  [[ -z "${ANTHROPIC_API_KEY:-}" ]] && echo "ERROR: ANTHROPIC_API_KEY not set" >&2 && exit 1

  CONTEXT=$(jq -r 'select(.type == "user") |
    .message.content // empty |
    if type == "string" then .
    elif type == "array" then [.[] | select(.type == "text") | .text] | join(" ")
    else empty end
  ' "$TRANSCRIPT" 2>/dev/null || true)
  CONTEXT="${CONTEXT:0:1500}"
  [[ -z "$CONTEXT" ]] && echo "ERROR: No user messages found" >&2 && exit 1

  RESPONSE=$(curl -sf --max-time 10 \
    -H "x-api-key: ${ANTHROPIC_API_KEY}" \
    -H "anthropic-version: 2023-06-01" \
    -H "content-type: application/json" \
    -d "$(jq -nc --arg c "$CONTEXT" '{
      model: "claude-haiku-4-5-20251001", max_tokens: 30,
      messages: [{role: "user", content: ("Generate a short (2-5 word) session name for this work. Output ONLY the name, no quotes.\n\n" + $c)}]
    }')" \
    "https://api.anthropic.com/v1/messages" 2>/dev/null) || { echo "ERROR: Haiku API call failed" >&2; exit 1; }

  NAME=$(echo "$RESPONSE" | jq -r '.content[0].text // empty' 2>/dev/null)
  NAME=$(printf '%s' "$NAME" | tr -d '"\000-\037')
  NAME="${NAME:0:60}"
  [[ -z "$NAME" ]] && echo "ERROR: Empty name from Haiku" >&2 && exit 1
fi

# Output title — caller applies via /rename
echo "✅ $NAME"
