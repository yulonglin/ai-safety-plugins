---
name: review-transcripts
description: Review experiment transcripts for issues. Runs deterministic checks then LLM-based review on sampled transcripts. Supports .eval, JSONL, log directories, and custom formats.
---

# Review Transcripts

Review experiment transcripts to catch scorer misconfiguration, LLM confusion, eval awareness, refusals, and other issues that aggregate metrics hide.

## Usage

```
/review-transcripts <path>                    # Auto-detect format
/review-transcripts <path> --score-field outcome  # Custom score field for JSONL
/review-transcripts                           # Find most recent .eval or JSONL
```

## Instructions

### 1. Locate the experiment output

If the user provides a path, use it. Otherwise, find the most recent output:
```bash
# Check common locations for recent experiment output
ls -t logs/*.eval tmp/*.eval out/**/*.eval 2>/dev/null | head -5
ls -t results/*.jsonl out/**/*.jsonl tmp/*.jsonl 2>/dev/null | head -5
```

If no output found, ask the user for the path.

### 2. Run Tier 1: Deterministic checks

```bash
python check_transcripts.py <path> --output-dir transcript_review
```

This auto-detects format (.eval, JSONL, directory, JSON, text) and produces:
- `transcript_review/summary.json` — structured findings
- `transcript_review/samples/*.json` — extracted transcript files
- Human-readable report to stdout

If `check_transcripts.py` is not found, check `scripts/check_transcripts.py` relative to the project root or the ai-safety-plugins research plugin directory.

Pass through user options:
- `--format` if user specifies input format
- `--score-field` for custom JSONL score fields
- `--max-samples` to control sample count
- `--score-threshold` for non-binary scoring

### 3. Review Tier 1 output

Read `transcript_review/summary.json` and report Tier 1 findings to the user:
- Score distribution
- Any CRITICAL or WARNING issues found deterministically
- Number of samples extracted for deeper review

### 4. Run Tier 2: LLM-based review

Spawn the transcript-reviewer agent on the extracted samples:

```
Agent tool:
  subagent_type: "research:transcript-reviewer"
  prompt: "Review the extracted transcripts in transcript_review/.
           Read summary.json first for Tier 1 findings, then review each sample in samples/.
           Focus on: scorer correctness, eval awareness, instruction misunderstanding,
           refusals, and whether individual transcripts support the aggregate metrics.
           The experiment was: [brief description of what was being tested]."
```

### 5. Present combined report

Combine Tier 1 (deterministic) and Tier 2 (LLM) findings:

```
## Transcript Review: [experiment name]

### Tier 1 (deterministic checks)
- [findings from check_transcripts.py]

### Tier 2 (LLM review of N sampled transcripts)
- [findings from transcript-reviewer agent]

### Recommendation
- [Trust / Investigate / Rerun with fixes]

### Optional: Deep analysis
- For Inspect AI evals: `scout scan <eval_log>` (if inspect_scout installed)
```

### 6. Suggest next steps

Based on findings:
- **CRITICAL issues**: Recommend fixing scorer/setup and rerunning
- **WARNING issues**: Recommend investigating specific samples
- **Clean**: Confirm results can be trusted, suggest `data-analyst` for full statistical analysis

## Notes

- Tier 1 runs in seconds, no LLM cost
- Tier 2 uses the transcript-reviewer agent (Read+Grep only, no recursion risk)
- For Inspect AI evals, recommend `scout scan` for Tier 3 deep LLM-powered scanning
- The hook `nudge_transcript_review.sh` will remind you to do this after experiment commands
