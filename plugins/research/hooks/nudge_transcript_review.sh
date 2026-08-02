#!/bin/bash
set -euo pipefail

# PostToolUse(Bash) hook: nudge transcript review after experiment commands.
# NUDGES: experiment-running commands (run_*.py, inspect eval, etc.)
# EXCLUDES: check_transcripts.py, scout scan (avoid self-referential nudges)
# Does NOT block (exit 0 always) — informational nudge only.

input=$(cat)
command=$(echo "$input" | jq -r '.tool_input.command // ""')
exit_code=$(echo "$input" | jq -r '.tool_output.exit_code // "0"')
session_id=$(echo "$input" | jq -r '.session_id // "global"')

# The nudge text below is a fixed block — every fire is byte-identical, so
# repeating it carries no information. Measured at 1454 fires across recent
# transcripts (~1.13M chars). One reminder per session per window is the whole
# signal; the rest is duplication. Window and fail-open behaviour mirror
# dotfiles' nudge_modern_tools.sh.
DEBOUNCE_DIR="${HOME}/.cache/claude/nudge-transcript-review.d"
DEBOUNCE_SECS=$((30 * 60))

should_nudge() {
    local key="$1" marker now last
    mkdir -p "$DEBOUNCE_DIR" 2>/dev/null || return 0  # fail open
    marker="$DEBOUNCE_DIR/$key"
    now=$(date +%s)
    if [[ -f "$marker" ]]; then
        last=$(stat -f%m "$marker" 2>/dev/null || stat -c%Y "$marker" 2>/dev/null || echo 0)
        if [[ $(( now - last )) -lt $DEBOUNCE_SECS ]]; then
            return 1
        fi
    fi
    : > "$marker" 2>/dev/null || return 0  # fail open
    return 0
}

# Quick exit if empty or command failed
[[ -z "$command" ]] && exit 0
[[ "$exit_code" != "0" ]] && exit 0

# Exclusions: don't nudge about our own review tools
[[ "$command" == *"check_transcripts"* ]] && exit 0
[[ "$command" == *"scout scan"* ]] && exit 0
[[ "$command" == *"transcript_review"* ]] && exit 0

# Pattern matching for experiment commands
is_experiment=false

# Direct experiment runner scripts
if [[ "$command" =~ run_[a-zA-Z0-9_]*\.(py|sh) ]]; then
    is_experiment=true
# Inspect AI CLI
elif [[ "$command" =~ inspect[[:space:]]+eval ]]; then
    is_experiment=true
# Python running experiment scripts
elif [[ "$command" =~ (python3?|uv[[:space:]]+run[[:space:]]+python3?)[[:space:]]+(run_|run[[:space:]]) ]]; then
    is_experiment=true
# Python module execution with eval/experiment keywords
elif [[ "$command" =~ (python3?|uv[[:space:]]+run[[:space:]]+python3?)[[:space:]]+-m[[:space:]]+.*([Ee]val|[Ee]xperiment|[Bb]enchmark) ]]; then
    is_experiment=true
# Script names containing experiment-related keywords
elif [[ "$command" =~ (^|[/[:space:]])(eval|experiment|benchmark|scaffold|latteries|safety.tooling)[a-zA-Z0-9_]*\.(py|sh) ]]; then
    is_experiment=true
# pytest with eval/benchmark paths
elif [[ "$command" =~ pytest.*([Ee]val|[Bb]enchmark) ]]; then
    is_experiment=true
fi

if [[ "$is_experiment" == "true" ]] && should_nudge "$session_id"; then
    nudge="⚠️ **Experiment command detected.** Before reporting results, review transcripts:
1. Run: \`python check_transcripts.py <output_path>\` (Tier 1: deterministic checks — supports .eval, JSONL, log dirs, raw text)
2. Spawn \`research:transcript-reviewer\` on extracted samples (Tier 2: LLM review)
3. For Inspect AI evals: \`scout scan <eval_log>\` if installed (Tier 3: deep LLM scan)

**Focus on failures** — sample a few to understand WHY they failed.
For custom scaffolds: check if model behavior matches researcher intent."

    jq -n --arg msg "$nudge" '{
      systemMessage: $msg
    }'
fi

exit 0
