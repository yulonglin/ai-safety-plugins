---
name: new-experiment
description: Create a new experiment record from template with structured frontmatter and hypothesis.
---

# New Experiment

Create a structured experiment record to track hypotheses, setup, results, and learnings.

## When to Use This Skill

- Starting a new experiment or evaluation run
- Logging a planned experiment before executing it
- Creating a record for an experiment you're about to run

**Disambiguation**: For Hydra config setup and experiment infrastructure, use `/experiment-setup` instead.

## Instructions

1. **Ask the user** (if not already provided):
   - What is the experiment testing? (hypothesis)
   - Which dataset and method? (e.g., MATH + C3, GPQA + lie detector)
   - Priority level? (P0-P3, default P1)

2. **Generate the filename** using UTC date and a short kebab-case name:
   ```
   docs/experiments/YYYY-MM-DD_short-name.md
   ```
   Example: `docs/experiments/2026-02-20_c3-honest-wrong-control.md`

3. **Copy the template** from `docs/experiments/_template.md` if it exists in the project. If not, use the reference template at `references/template.md`.

4. **Fill in the frontmatter** from the user's description:
   - `title`: Descriptive experiment title
   - `date`: Current UTC date (YYYY-MM-DD)
   - `status`: `planned` (default) or `active`
   - `dataset`: Which dataset(s)
   - `method`: Which detection method(s)
   - `priority`: P0-P3
   - `tags`: Relevant tags

5. **Fill in the body sections**:
   - **Hypothesis**: What you expect to find and why
   - **Setup**: Commands, configs, key parameters
   - Leave Results, Analysis, and Learnings empty (filled after running)

6. **Update the experiment index**:
   ```bash
   python scripts/update_experiment_index.py
   ```
   If the script doesn't exist, skip this step and note it.

7. **Report** the created file path and suggest next steps:
   - Run the experiment with `/run-experiment`
   - Or mark as `status: active` when starting

## Example

User: "new experiment testing C3 on honest-wrong samples with MATH dataset"

Creates `docs/experiments/2026-02-20_c3-honest-wrong.md`:
```yaml
---
title: "C3 detection on honest-wrong control samples"
date: 2026-02-20
status: planned
dataset: MATH-L5
method: C3
priority: P0
tags: [honest-wrong, control, confounders]
---
```

With hypothesis filled from user's description and setup section outlining the planned commands.
