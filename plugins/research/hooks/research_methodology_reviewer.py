#!/usr/bin/env python3
"""RETIRED PostToolUse hook: LLM-based research methodology reviewer.

UNWIRED from plugin.json. Kept for reference, not registered on any event.
Superseded by the `methodology-critic` skill, which reviews a design document
instead of an individual tool call.

Why it was retired, measured over 878 transcripts and the hook's own log:

  - 2,490 nudges printed. An OK-gate bug (`response.strip().upper() == "OK"`,
    exact match only) let every reply that merely *began* with "OK" through:
    504 of 1,075 logged verdicts leaked this way, against 274 correctly
    suppressed. ~85% of the ~1.9M characters it printed contained no finding.
  - The remaining replies included a recurring confusion mode — "I can't
    execute shell commands", "I don't see the output" — printed as findings.
  - The precision ceiling was set by the *input*, not the prompt. Circular
    reasoning, leakage and confounding are properties of an experimental
    design; a single tool call rarely contains enough of the design to judge
    them, so the reviewer was guessing from a fragment.

Deterministic regex tripwires were evaluated as a cheap replacement and
rejected on evidence: against 213 known-positive payloads (drawn from this
hook's own genuine findings) and 528 known negatives, the union of eight
candidate signals recovered 5.2% of positives while firing on 7.8% of
negatives — no discriminative power. See the analysis scripts referenced in
the PR that retired this hook.

Original behaviour: monitored Bash, Write and Edit; regex pre-filter, then
Haiku. Failed open (exit 0) on any error — informational nudges only.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 200
TIMEOUT_SECONDS = 10
MAX_INPUT_CHARS = 3000
LOG_PATH = os.path.expanduser("~/.cache/claude/research-methodology-reviewer.log")
MAX_LOG_BYTES = 500_000  # 500KB

# ── System prompt for the methodology reviewer ──────────────────────────
SYSTEM_PROMPT = """\
You are a research methodology reviewer embedded in an AI safety researcher's \
workflow. Your job is to flag methodological concerns — the kind of thing a \
reviewer or PhD advisor would find suspect.

Flag:
- Circular reasoning (using outcomes/metrics to determine labels or group assignments)
- Data leakage between train/test or dev/test splits
- Cherry-picking or post-hoc filtering of results
- Hardcoded mappings that should be derived from data or metadata
- Using expected results to validate pipeline correctness
- P-hacking (trying many thresholds/metrics and reporting the best)
- Reporting bias (selectively presenting favorable results)
- Confounded comparisons (comparing groups that differ in more than the variable of interest)

Do NOT flag:
- Routine metric computation (computing accuracy, recall, AUC is fine)
- Standard data processing (loading CSVs, parsing eval files, aggregating scores)
- Using established hyperparameters documented in config files
- Bootstrap resampling or cross-validation (these are good practice)
- Threshold selection on a designated dev set (this is correct methodology)

If you see a concern, explain in 2-4 sentences: what you noticed, why it's \
suspect, and what the principled alternative is. Frame it as an observation or \
question, not a lecture.

If everything looks fine, respond with exactly: OK"""

# ── Regex pre-filters ───────────────────────────────────────────────────
# Bash: fire on any command containing a Python invocation
_PYTHON_CMD = re.compile(r"(?:^|\s|&&|\|\||;)(?:uv\s+run\s+)?python3?\s", re.IGNORECASE)
# Write/Edit: fire on code and data files, skip docs/config
_CODE_DATA_EXT = re.compile(r"\.(?:py|csv|json|jsonl)$", re.IGNORECASE)


def log(msg: str) -> None:
    """Append a timestamped message to the log file."""
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > MAX_LOG_BYTES:
            with open(LOG_PATH, "r") as f:
                lines = f.readlines()
            with open(LOG_PATH, "w") as f:
                f.writelines(lines[len(lines) // 2 :])
        with open(LOG_PATH, "a") as f:
            from datetime import datetime, timezone

            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            f.write(f"{ts} {msg}\n")
    except Exception:
        pass


def should_review_bash(command: str) -> bool:
    """Fire on any Python command; skip simple shell builtins."""
    if not command or not command.strip():
        return False
    # Python anywhere in the command is the positive signal
    return bool(_PYTHON_CMD.search(command))


def should_review_file_op(tool_input: dict) -> bool:
    """Fire on writes to .py, .csv, .json, .jsonl files."""
    file_path = tool_input.get("file_path", "")
    return bool(_CODE_DATA_EXT.search(file_path))


def extract_review_text(tool_name: str, tool_input: dict) -> str:
    """Extract the text to send to the reviewer, truncated to MAX_INPUT_CHARS."""
    if tool_name == "Bash":
        text = f"Command: {tool_input.get('command', '')}"
    elif tool_name == "Write":
        content = tool_input.get("content", "")
        file_path = tool_input.get("file_path", "")
        text = f"File: {file_path}\nContent:\n{content}"
    elif tool_name == "Edit":
        file_path = tool_input.get("file_path", "")
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        text = f"File: {file_path}\nReplacing:\n{old}\nWith:\n{new}"
    else:
        text = json.dumps(tool_input, indent=2)

    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS] + "\n... (truncated)"
    return text


def call_reviewer(text: str) -> str | None:
    """Call Haiku to review the research action. Returns response or None on error."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log("SKIP: ANTHROPIC_API_KEY not set")
        return None

    body = json.dumps({
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": text}],
    }).encode()

    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read())
        return data["content"][0]["text"].strip()
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            raw = str(e)
        log(f"API error (HTTP {e.code}): {raw}")
        return None
    except urllib.error.URLError as e:
        log(f"Network error: {e.reason}")
        return None
    except Exception as e:
        log(f"Unexpected error: {e}")
        return None


def main() -> None:
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    # Pre-filter: only review research-related actions
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if not should_review_bash(command):
            sys.exit(0)
    elif tool_name in ("Write", "Edit"):
        if not should_review_file_op(tool_input):
            sys.exit(0)
    else:
        # Unknown tool type — skip
        sys.exit(0)

    log(f"REVIEWING: {tool_name} — {json.dumps(tool_input)[:200]}")

    # Extract text and call the reviewer
    review_text = extract_review_text(tool_name, tool_input)
    response = call_reviewer(review_text)

    if response is None:
        # API error — fail open
        sys.exit(0)

    # Check if the reviewer found a concern
    if response.strip().upper() == "OK":
        log("OK: no concerns")
        sys.exit(0)

    # Emit a nudge
    log(f"NUDGE: {response[:200]}")
    nudge = f"\U0001f52c **Methodology check:** {response}"
    json.dump({"systemMessage": nudge}, sys.stdout)


if __name__ == "__main__":
    main()
