#!/bin/sh
# PostToolUse hook: bash output truncation
#
# Per-line truncation (long lines) + head/tail truncation (large output).
# Runs entirely locally — no output ever leaves the machine.
#
# Configuration (env vars):
#   CLAUDE_TRUNCATE_THRESHOLD  - Overall truncation threshold in chars (default: 5000)
#   CLAUDE_LINE_MAX_CHARS      - Per-line truncation threshold (default: 500)

command -v jq >/dev/null 2>&1 || exit 0

TMPDIR="${TMPDIR:-/tmp/claude}"
INPUT_FILE="$TMPDIR/hook_input_$$.json"
DECISION_FILE="$TMPDIR/hook_decision_$$.json"
trap 'rm -f "$INPUT_FILE" "$DECISION_FILE"' EXIT
mkdir -p "$TMPDIR"

# Fast path: skip jq for small output (<6KB covers ~90% of bash commands)
cat > "$INPUT_FILE"
INPUT_SIZE=$(wc -c < "$INPUT_FILE" | tr -d ' ')
[ "$INPUT_SIZE" -lt 6000 ] && exit 0

# jq extracts fields and applies truncation
jq -c --arg line_max "${CLAUDE_LINE_MAX_CHARS:-500}" \
      --arg threshold "${CLAUDE_TRUNCATE_THRESHOLD:-5000}" '
  if .tool_name != "Bash" then empty
  else
    .tool_response as $r |
    .tool_input.command as $cmd |
    ($r.stdout // "") as $stdout |
    ($r.stderr // "") as $stderr |
    ($r.exit_code // 0) as $exit |
    (($stdout | length) + ($stderr | length)) as $total |
    ($line_max | tonumber) as $lmax |
    ($threshold | tonumber) as $thresh |

    if $total < $thresh then empty
    else
      # Per-line truncation: collapse lines longer than $lmax chars
      def truncate_line:
        if length > $lmax then
          .[:200] + " ... [" + (length | tostring) + " chars] ... " + .[-100:]
        else . end;

      # Truncate stdout: per-line + head 15 / tail 30 for large output
      (if ($stdout | length) > 1500 then
        ($stdout | split("\n") | map(truncate_line)) as $lines |
        if ($lines | length) <= 45 then ($lines | join("\n"))
        else
          ([$lines[:15][], "",
            "... [" + ($stdout | length | tostring) + " chars, " +
            (($stdout | split("\n") | length) | tostring) + " lines truncated] ...",
            "", $lines[-30:][]] | join("\n"))
        end
      else
        ($stdout | split("\n") | map(truncate_line) | join("\n"))
      end) as $trunc_stdout |

      # Truncate stderr: per-line + last 20 lines
      (if ($stderr | length) > 500 then
        "... [stderr truncated] ...\n\n" +
        (($stderr | split("\n"))[-20:] | map(truncate_line) | join("\n"))
      else
        ($stderr | split("\n") | map(truncate_line) | join("\n"))
      end) as $trunc_stderr |

      # Build truncated message
      ("Command: " + $cmd + "\nExit code: " + ($exit | tostring) +
       "\nOutput (truncated from " + ($total | tostring) + " chars):\n\n" +
       $trunc_stdout +
       (if ($trunc_stderr | length) > 0 then
         "\n\n--- stderr ---\n" + $trunc_stderr
       else "" end)) as $truncated_msg |

      {suppressOutput: true, systemMessage: $truncated_msg}
    end
  end
' < "$INPUT_FILE" > "$DECISION_FILE"

# No output means small/non-bash — pass through
[ ! -s "$DECISION_FILE" ] && exit 0

cat "$DECISION_FILE"
