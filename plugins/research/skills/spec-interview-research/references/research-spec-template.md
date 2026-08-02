# Research Interview Spec: [Topic]

Four sections carry the spec — the usual three (Overview, Requirements, Acceptance Criteria) plus Research Question & Hypotheses, which feature specs don't need. Everything after the divider is optional — include only if it earns its place, and delete the section entirely if it doesn't apply. Never fill an unused section with "N/A" / "None" / "TBD".

**Created**: DD-MM-YYYY · **Status**: Draft

## Overview
[1-2 sentences: what we're studying and why]

## Research Question & Hypotheses
[Specific, measurable question]
- **H1**: [Hypothesis] → Prediction: [outcome] → Falsification: [what would disprove it]

## Requirements
*What defines the experiment — the actual contract, not prose.*
- **Independent variables**: [what we manipulate + levels, e.g. model size: 1B/7B/13B]
- **Dependent variables**: [exact metric definitions, e.g. "exact_match accuracy on MMLU"]
- **Baselines**: [what we compare against, why fair]
- **Datasets & models**: [name/version/source; model + key hyperparameters, with justification for non-default values]

## Acceptance Criteria
- **Validation**: [N and justification, significance threshold — how we'll know the result is trustworthy, not just present]
- **Output path**: [exact directory, e.g. `out/DD-MM-YYYY_HH-MM-SS_experiment_name/`]

---

Add only if it earns its place — a real, non-obvious answer, not a placeholder:

## Design
[Control variables, confound handling, why this baseline is fair, sample-size derivation — only if non-obvious]

## Planned Visualizations
- **Figure 1**: [X-axis, Y-axis, grouping, purpose — only if the plots aren't the obvious "metric vs. condition"]

## Engineering Notes
[Only nonstandard caching / concurrency / retry / error-handling choices for this experiment — standard patterns already live in `docs/research-methodology.md` and `docs/async-and-performance.md`; link to them instead of re-deriving. Random seeds / code version only if reproducibility is unusually tight for this study.]

## Resources & Constraints
[Only if compute/budget/timeline is a real risk for this run — omit if it's a routine-sized experiment]

## Open Questions
- [ ] [Unresolved question — delete this section if there are none]
