#!/usr/bin/env bash
# SessionStart hook: inject active experiment context into Claude sessions.
# Silently exits 0 if no experiments/ directory — safe for global install.

EXPERIMENTS_DIR="docs/experiments"
PATTERNS_FILE="docs/journal/PATTERNS.md"

# Silent exit if not in a project with experiments
[[ -d "$EXPERIMENTS_DIR" ]] || exit 0

echo "# Active Experiments"
echo ""

# Show active/planned experiments from frontmatter
active_lines=()
for f in "$EXPERIMENTS_DIR"/*.md; do
  [[ -f "$f" ]] || continue
  [[ "$(basename "$f")" == "README.md" || "$(basename "$f")" == "_template.md" ]] && continue
  status=$(grep -m1 '^status:' "$f" 2>/dev/null | sed 's/status: *//')
  if [[ "$status" == "planned" || "$status" == "active" ]]; then
    title=$(grep -m1 '^title:' "$f" 2>/dev/null | sed 's/title: *//;s/"//g')
    active_lines+=("- [$status] $title ($(basename "$f"))")
  fi
done

if (( ${#active_lines[@]} == 0 )); then
  echo "- (no active experiments)"
else
  printf '%s\n' "${active_lines[@]}" | head -15
fi

echo ""
echo "## Session Rules"
echo "- Read experiment record in docs/experiments/ BEFORE running commands"
echo "- After running: update record with results and artifacts"
echo "- CRITICAL: --multirun REQUIRED when config has sweep.* parameters"
echo "- CRITICAL: message_selection=0 for MCQ, =last for free-form"

# --- Reflection staleness check ---
if [[ -f "$PATTERNS_FILE" ]]; then
  last_date=$(grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' "$PATTERNS_FILE" | sort -r | head -1)
  if [[ -n "$last_date" ]]; then
    # macOS date -j syntax
    last_epoch=$(date -j -f "%Y-%m-%d" "$last_date" +%s 2>/dev/null)
    if [[ -n "$last_epoch" ]]; then
      now_epoch=$(date +%s)
      days_since=$(( (now_epoch - last_epoch) / 86400 ))
      if (( days_since > 14 )); then
        echo ""
        echo "Warning: Last research reflection: ${days_since} days ago. Consider running /reflect (requires research plugin)"
      fi
    fi
  fi
fi

# --- Staleness detection ---
# Compare last code change vs last docs change
last_code_epoch=$(git log -1 --format=%ct -- 'src/' 2>/dev/null || echo 0)
last_docs_epoch=$(git log -1 --format=%ct -- 'CLAUDE.md' 'docs/' 'AGENTS.md' 2>/dev/null || echo 0)

if (( last_code_epoch > 0 && last_docs_epoch > 0 )); then
  diff_days=$(( (last_code_epoch - last_docs_epoch) / 86400 ))

  # Activity-dependent threshold
  commits_this_week=$(git rev-list --count --since='1 week ago' HEAD -- src/ 2>/dev/null || echo 0)
  if (( commits_this_week > 10 )); then
    threshold=7
  elif (( commits_this_week >= 1 )); then
    threshold=14
  else
    threshold=999  # Low activity, skip warning
  fi

  if (( diff_days > threshold )); then
    echo ""
    echo "Warning: Code changed ${diff_days} days after last docs update."
    echo "   Consider running /audit-docs to check for stale documentation (requires research plugin)."
  fi
fi
