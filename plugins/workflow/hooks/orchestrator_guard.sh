#!/bin/bash
# Claude Code PreToolUse hook: Soft warning when orchestrator mode is active
# and Claude uses implementation tools directly instead of delegating.
#
# Activation: Create marker file to enable orchestrator mode:
#   touch "$TMPDIR/claude-orchestrator-mode"
# Deactivation: Remove marker to disable:
#   rm -f "$TMPDIR/claude-orchestrator-mode"
#
# Exit codes:
#   0 - Always allow (warnings only, never blocks)

set -euo pipefail

# Only active when orchestrator mode marker exists
MARKER="${TMPDIR:-/tmp}/claude-orchestrator-mode"
[ -f "$MARKER" ] || exit 0

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // ""')

# Tools that are always allowed in orchestrator mode (no warning)
case "$TOOL" in
    Agent|SendMessage|TaskCreate|TaskUpdate|TaskGet|TaskList|TaskOutput|TaskStop|\
    TodoWrite|TodoRead|EnterPlanMode|ExitPlanMode|Skill|AskUserQuestion|\
    ToolSearch|Config)
        exit 0
        ;;
esac

# Bash: allow git status/log/diff --stat for situational awareness
if [ "$TOOL" = "Bash" ]; then
    COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
    # Allow short git commands for coordination awareness
    if echo "$COMMAND" | grep -qE '^\s*git\s+(status|log|diff\s+--stat|branch|remote)'; then
        exit 0
    fi
fi

# Everything else gets a soft warning
case "$TOOL" in
    Read)
        echo "ORCHESTRATOR: Consider delegating this read to an efficient-explorer agent instead of reading directly." >&2
        ;;
    Edit|Write)
        echo "ORCHESTRATOR: Consider delegating this edit to a codex or claude agent instead of writing directly." >&2
        ;;
    Bash)
        echo "ORCHESTRATOR: Consider delegating this command to a subagent instead of running it directly." >&2
        ;;
    Grep|Glob)
        echo "ORCHESTRATOR: Consider delegating this search to an Explore agent instead of searching directly." >&2
        ;;
    WebFetch|WebSearch)
        echo "ORCHESTRATOR: Consider delegating this research to a general-purpose agent instead of fetching directly." >&2
        ;;
    NotebookEdit)
        echo "ORCHESTRATOR: Consider delegating notebook edits to a subagent." >&2
        ;;
    *)
        # Unknown tool — gentle generic reminder
        echo "ORCHESTRATOR: You're in orchestrator mode. Consider whether this should be delegated." >&2
        ;;
esac

exit 0
