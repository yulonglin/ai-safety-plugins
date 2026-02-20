---
name: reflect
description: Mine experiment records and conversations for patterns, update the research journal.
---

# Reflect

Synthesize learnings from recent experiments into the research patterns journal.

## When to Use This Skill

- After completing a batch of experiments
- When the SessionStart hook warns reflection is stale (>14 days)
- Periodically to consolidate what you've learned
- When prompted with "what have we learned?"

## Instructions

### Stage 1: Experiment Mining (cheap, always run)

1. **Read all experiment records**:
   ```bash
   ls docs/experiments/*.md
   ```
   Read each file with status `completed` or `active` that has results filled in.

2. **Read current patterns**:
   ```
   docs/journal/PATTERNS.md
   ```

3. **Identify new observations** not yet captured in PATTERNS.md:
   - Results that confirmed or contradicted hypotheses
   - Surprising findings or unexpected behaviors
   - Recurring agent mistakes or workflow gotchas
   - Cross-experiment trends (e.g., "C3 consistently fails on X")

4. **Draft new entries** using the format in `references/patterns-format.md`:
   ```
   - YYYY-MM-DD: [tag] Description (source: experiment-file.md)
   ```

5. **Present findings to user** before writing:
   - Show proposed new entries
   - Flag any existing entries that may be outdated or contradicted
   - Ask if anything should be added from their memory

6. **Update PATTERNS.md**:
   - Append new entries under the appropriate section
   - Mark contradicted entries with `[REVISED]` prefix
   - Keep entries sorted by date (newest first within each section)

### Stage 2: Conversation Mining (expensive, optional)

Only run if user requests deeper analysis or says "deep reflect".

1. **Delegate to Gemini CLI agent** for large context analysis:
   - Pre-filter conversation transcripts to relevant sessions (experiment-related)
   - Ask Gemini to identify: recurring problems, workflow inefficiencies, decisions made without clear rationale
   - Merge Gemini's findings with Stage 1 results

2. **Cross-reference** with experiment records to validate conversation-mined insights.

## Output

- Updated `docs/journal/PATTERNS.md` with timestamped, tagged entries
- Summary of what was added/revised (shown to user)

## Notes

- Default to Stage 1 only — it's fast and covers most value
- Stage 2 requires explicit user opt-in ("deep reflect")
- Never delete existing pattern entries — mark as `[REVISED]` if outdated
- Source attribution is required: always link back to the experiment record
