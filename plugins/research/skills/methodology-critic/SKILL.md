---
name: methodology-critic
description: Adversarially critique the methodology of a research spec, plan, experiment record, or writeup — circular reasoning, leakage, confounding, post-hoc filtering, overclaimed causality. Use before running an experiment, before sharing results, when interpreting an ambiguous result, or when asked to "review the methodology" / "poke holes in this design".
---

# Methodology Critic

Review an experimental **design** the way a hostile-but-fair reviewer would. The goal is to find the flaw before a reviewer does — while it is still cheap to fix.

## When to Use This Skill

- Before running an experiment, on the spec or plan that defines it
- Before sharing or publishing results, on the writeup
- When a result is ambiguous, surprising, or suspiciously clean
- When asked to "review the methodology", "poke holes in this", "would a reviewer buy this?"
- On an experiment record whose hypothesis and results are both filled in

**Not** for a single command, script, or diff. Circularity, leakage and confounding are properties of a design — a lone tool call almost never contains enough of the design to judge them, and reviewing at that granularity produces mostly false alarms. If you only have a diff, review the design document it implements, or say that you cannot assess methodology from this input.

## Instructions

### Stage 0: Establish the claim

Before critiquing anything, write down in one sentence each:

1. **The claim** — what is asserted to be true.
2. **The comparison** — what is being compared against what.
3. **The manipulated variable** — what deliberately differs between conditions.
4. **The measured outcome** — what is scored, and by what.

If any of these cannot be recovered from the document, that is itself the first finding. An unstated comparison is where most confounds hide.

### Stage 1: The five passes

Run each pass against the document. For each, ask the specific question, not the general one.

**1. Circularity.** Does any label, group assignment, or inclusion decision depend on the outcome being measured?

> General test: *if removing this step would change the reported result, and the step depends on the result, it is circular.*

Look for: labels derived by thresholding a score; membership decided by whether a run "worked"; expected values hardcoded and then "verified"; a pipeline validated by checking it reproduces the anticipated answer.

**2. Leakage.** Does information from the evaluation set reach any decision made before evaluation?

Look for: thresholds, hyperparameters, prompts or filters tuned on test; a dev set that was reused until it stopped being held out; normalisation statistics computed over the full corpus; near-duplicates spanning the split.

**3. Selection.** Was anything dropped, and was the decision to drop it made before or after seeing its effect?

Look for: post-hoc exclusion of runs, outliers, or conditions; a sample filtered on a variable correlated with the outcome; failed conditions absent from the writeup; "we focus on the subset where…".

**4. Confounding.** Do the compared groups differ in anything other than the manipulated variable?

Look for: conditions run at different times, on different models, with different prompts or seeds or context lengths; a baseline that received less tuning effort than the treatment; unequal N with no accounting.

**5. Inference.** Do the claims match what the design can support?

Look for: causal verbs ("causes", "drives", "proves", "demonstrates") on a design that is observational; effect sizes stated without CI or SE; significance reported without effect size; many thresholds or metrics tried and the best one reported; a conclusion that would survive the opposite result.

### Stage 2: Apply the reviewer test

For each candidate finding, ask: **would a reviewer seeing this find it suspect?** If the honest answer is "no, this is standard practice", drop it. Do not pad the review.

Explicitly do **not** flag these — they are correct practice and flagging them trains the user to ignore you:

- Routine metric computation (accuracy, recall, AUC)
- Standard data processing — loading, parsing, aggregating
- Established hyperparameters documented in a config
- Bootstrap resampling or cross-validation
- Threshold selection on a *designated dev set*
- Exploratory inspection of raw data, clearly labelled as exploratory

### Stage 3: Report

Rank findings by severity and stop at the real ones.

- **BLOCKING** — the result as stated does not follow; running this produces a number that cannot be interpreted. Fix before running.
- **SERIOUS** — the result is interpretable but a reviewer would demand a control, an ablation, or a caveat.
- **MINOR** — phrasing, missing uncertainty, an unstated assumption worth writing down.

For each finding give three things and nothing more:

1. **What you noticed** — quote or cite the specific part of the document.
2. **Why it is suspect** — the mechanism by which it produces a wrong or uninterpretable number.
3. **The principled alternative** — what to do instead, concretely.

Frame findings as observations and questions, not as a lecture. "The condition labels appear to come from `run_ok`, which is also the outcome — is that right?" beats "You have committed circular reasoning."

If the design is sound, say so in one line: **"No methodological concerns."** Do not manufacture a finding to justify the review. A clean review is a real result.

## Output

- A ranked list of findings (BLOCKING → SERIOUS → MINOR), each with noticed / why / alternative
- Or the single line "No methodological concerns."
- If Stage 0 could not recover the claim, comparison, variable and outcome: say which were missing, and treat that as the finding

## Notes

- **Severity discipline is the whole value.** This skill replaced an automatic hook that fired on every tool call and reported a non-finding roughly 85% of the time. The failure mode to avoid is not missing a concern — it is crying wolf until the user stops reading.
- **Judge the design, not the author.** Assume competence; most real findings are honest oversights, and phrasing them as questions gets them fixed faster.
- **Report what did not work too.** If the document omits conditions that were run, that omission is a finding under Stage 1 pass 3.
- Cross-reference the user's standing rules rather than re-deriving them: the reviewer test, separation of labelling / scoring / analysis, and the causal-claims register live in `research-integrity`.
