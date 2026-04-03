#!/usr/bin/env bash
# Mark current Claude Code session as done with a descriptive name.
# Called by /done skill. Sources secrets for ANTHROPIC_API_KEY if needed.
set -euo pipefail

# Source secrets (API key not in Bash tool environment)
DOT_DIR="${DOT_DIR:-$HOME/code/dotfiles}"
[[ -f "$DOT_DIR/.secrets" ]] && source "$DOT_DIR/.secrets"

# Find current transcript (most recently modified .jsonl in project dir)
PROJECT_DIR="$HOME/.claude/projects/$(pwd | sed 's|/|-|g')"
TRANSCRIPT=$(/bin/ls -t "$PROJECT_DIR"/*.jsonl 2>/dev/null | head -1 || true)
[[ -z "$TRANSCRIPT" ]] && echo "No transcript found in $PROJECT_DIR" && exit 1
SESSION_ID=$(basename "$TRANSCRIPT" .jsonl)

# Check for existing name
EXISTING=$(jq -r 'select(.type == "custom-title") | .customTitle // empty' "$TRANSCRIPT" 2>/dev/null || true)
EXISTING="${EXISTING##*$'\n'}"  # keep last line only

if [[ "$EXISTING" == "✅ "* ]]; then
  echo "Already done: $EXISTING"
  { printf '\033]0;%s\033\\' "$EXISTING" > /dev/tty; } 2>/dev/null || true
  [[ -n "${TMUX:-}" ]] && tmux rename-window "$EXISTING" 2>/dev/null || true
  exit 0
elif [[ -n "$EXISTING" ]]; then
  NAME="$EXISTING"
else
  # Generate name from first user messages via Haiku
  [[ -z "${ANTHROPIC_API_KEY:-}" ]] && echo "ANTHROPIC_API_KEY not set" && exit 1

  CONTEXT=$(jq -r 'select(.type == "user") |
    .message.content // empty |
    if type == "string" then .
    elif type == "array" then [.[] | select(.type == "text") | .text] | join(" ")
    else empty end
  ' "$TRANSCRIPT" 2>/dev/null || true)
  CONTEXT="${CONTEXT:0:1500}"
  [[ -z "$CONTEXT" ]] && echo "No user messages found" && exit 1

  RESPONSE=$(curl -sf --max-time 10 \
    -H "x-api-key: ${ANTHROPIC_API_KEY}" \
    -H "anthropic-version: 2023-06-01" \
    -H "content-type: application/json" \
    -d "$(jq -nc --arg c "$CONTEXT" '{
      model: "claude-haiku-4-5-20251001", max_tokens: 30,
      messages: [{role: "user", content: ("Generate a short (2-5 word) session name for this work. Output ONLY the name, no quotes.\n\n" + $c)}]
    }')" \
    "https://api.anthropic.com/v1/messages" 2>/dev/null) || { echo "Haiku API call failed"; exit 1; }

  NAME=$(echo "$RESPONSE" | jq -r '.content[0].text // empty' 2>/dev/null)
  NAME=$(printf '%s' "$NAME" | tr -d '"\000-\037')
  NAME="${NAME:0:60}"
  [[ -z "$NAME" ]] && echo "Empty name from Haiku" && exit 1
fi

TITLE="✅ $NAME"

# Write custom-title to transcript
jq -nc --arg t "$TITLE" --arg s "$SESSION_ID" \
  '{"type":"custom-title","customTitle":$t,"sessionId":$s}' >> "$TRANSCRIPT"

# Set terminal + tmux title
{ printf '\033]0;%s\033\\' "$TITLE" > /dev/tty; } 2>/dev/null || true
if [[ -n "${TMUX:-}" ]]; then
  tmux set-option -w automatic-rename off 2>/dev/null || true
  tmux rename-window "$TITLE" 2>/dev/null || true
fi

echo "Session marked done: $TITLE"
