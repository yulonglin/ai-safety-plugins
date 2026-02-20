# PATTERNS.md Format Reference

## Entry Format

Each entry is a single line with timestamp, tag, and description:

```
- YYYY-MM-DD: [tag] Description (source: experiment-file.md)
```

## Tags

| Tag | Use When |
|-----|----------|
| `[result]` | An experiment produced a clear, reproducible finding |
| `[finding]` | An observation from analysis — not yet confirmed by repeat experiments |
| `[surprise]` | Something contradicted expectations or prior assumptions |
| `[agent-mistake]` | A workflow or agent error that should be avoided in future |
| `[gotcha]` | A subtle technical issue (config, API, tooling) that wastes time |

## Sections

Organize entries under these headings in PATTERNS.md:

```markdown
# Research Patterns

## Detection Results
<!-- Findings about C3, lie detector, trusted monitor, etc. -->

## Methodology
<!-- What works/doesn't for running experiments -->

## Agent Workflow
<!-- Patterns in how Claude/agents handle research tasks -->

## Technical Gotchas
<!-- Config, API, tooling issues -->
```

## Examples

```markdown
## Detection Results
- 2026-02-15: [result] C3 recall drops from 94% to 67% on USACO vs MATH — free-form coding problems are harder to distinguish (source: 2026-02-10_c3-usaco-baseline.md)
- 2026-02-12: [surprise] Lie detector accuracy drops from 89% to 2% when controlling for model identity — it was detecting models, not lying (source: 2026-02-08_ld-model-identity.md)

## Methodology
- 2026-02-14: [finding] k=10 samples needed for stable C3 scores; k=5 has high variance on GPQA (source: 2026-02-11_k-sensitivity.md)

## Agent Workflow
- 2026-02-13: [agent-mistake] Forgot --multirun flag on sweep config, ran only defaults for 2 hours (source: 2026-02-13_math-sweep.md)

## Technical Gotchas
- 2026-02-11: [gotcha] message_selection=0 required for MCQ datasets (GPQA), =last for free-form (MATH/USACO) — silent wrong results if mismatched (source: 2026-02-09_c3-gpqa-debug.md)
```

## Revision

When a pattern is contradicted by new evidence:
```
- 2026-02-18: [REVISED] Previously: "C3 requires k>=10". Updated: k=5 sufficient for GPQA with new aggregation (source: 2026-02-17_k-revisit.md)
```
