---
name: done
description: Mark session as done — generates a descriptive name (if needed) and prepends a checkmark. Use when wrapping up, finishing, or the user says "done", "finished", "ship it", "/done".
---

# Mark Session Done

## Steps

1. **Generate a name** by running the done script. It returns the title to use:

```bash
"${CLAUDE_PLUGIN_ROOT}/skills/done/done.sh"
```

2. **Apply the name** using `/rename <title>` with the output from step 1.

The script handles:
- Detecting existing titles (reuses them, strips duplicate checkmarks)
- Generating new names via Haiku from the first user messages
- Prepending the ✅ checkmark

**Important:** You MUST use `/rename` to set the title — writing directly to the transcript JSONL does NOT update the live session UI. The `/rename` command updates both the file and the in-memory cache.

If the script reports "Already done", the session was already marked — just confirm to the user.
