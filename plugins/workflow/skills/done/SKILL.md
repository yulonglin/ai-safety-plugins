---
name: done
description: Mark session as done — generates a descriptive name (if needed) and prepends a checkmark. Use when wrapping up, finishing, or the user says "done", "finished", "ship it", "/done".
---

# Mark Session Done

1. Run the script to generate the session title:

```bash
"${CLAUDE_PLUGIN_ROOT}/skills/done/done.sh"
```

2. The script outputs the title (e.g., `✅ Build Done Skill`). Tell the user to run:

```
/rename <the title from step 1>
```

**Why /rename is needed:** Writing to the transcript JSONL only persists for `/resume`. The live session UI reads from an in-memory cache that only `/rename` updates. There is no external API to set it programmatically.

If the script outputs "Already done" to stderr, the session is already marked — confirm to the user.
