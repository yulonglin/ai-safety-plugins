---
name: done
description: Mark session as done — generates a descriptive name (if needed) and prepends a checkmark. Use when wrapping up, finishing, or the user says "done", "finished", "ship it", "/done".
---

# Mark Session Done

Run the done script to mark this session complete:

```bash
"${CLAUDE_PLUGIN_ROOT}/skills/done/done.sh"
```

This will:
1. Find the current session's transcript
2. If no name exists, call Haiku to generate a 2-5 word descriptive name from user messages
3. Prepend ✅ and write it as the session title
4. Set terminal + tmux window name

If it reports "Already done", the session was already marked. Confirm the result to the user.
