---
name: judge-transcripts
description: Classify transcripts by meaning with blinded LLM judges, ground every positive in a verbatim span, and report cross-model agreement against its chance null. Use when a hypothesis is about what a transcript means (deception, sandbagging, eval awareness, refusal, tone) rather than which literal token it contains.
---

# Judge Transcripts

Turn a hypothesis about *meaning* into labels you can defend: one API call per sample, a verbatim quote behind every positive, a span that seeks back to the exact characters in the stored transcript, and agreement figures that carry their own chance baseline.

Backed by the `transcript-judge` package (`tj`), which lives at `packages/transcript-judge/` in this repository.

## When this, and when not

Use it when the classification is semantic — intent, awareness, deception, tone, whether a claim was acknowledged. Keyword matching silently misses paraphrase and silently over-counts quotation of the very string being searched for, and **both errors point the same way as the hypothesis**, so they read as signal.

Do not use it when the target is a literal token whose surface form is fixed and enumerable — a UUID, an exact error string, a flag name. `grep` is correct there and far cheaper.

`/review-transcripts` is the triage pass that comes first: it finds *which* transcripts look wrong. This skill is what you reach for once you have a hypothesis worth measuring.

## The walk

```bash
cd packages/transcript-judge   # or use `uv run --project packages/transcript-judge`

# 1. Load. Inspect .eval, JSONL, or a log directory -> one blinded corpus.
uv run --with inspect-ai tj load <path>... --run runs/my-run

# 2. Judge. One call per sample per cell; two models if you want reliability.
uv run tj run --run runs/my-run --judge prompts/my_judge.v1.md \
    --model anthropic:claude-sonnet-5 --model openrouter:openai/gpt-5.6-sol

# 3. Ground. Quotes -> exact character spans in the stored text.
uv run tj labels --run runs/my-run

# 4. Merge near-duplicate constructs (LLM pairwise equivalence, cached).
uv run tj cluster --run runs/my-run

# 5. Agreement, each figure beside its chance null.
uv run tj stats --run runs/my-run

# 6. An interactive, self-contained overlap page.
uv run tj artifact --run runs/my-run
```

Add `--dry-run` to step 2 to print the resolved provider, model, and params per judge cell without making a single network call. Do that before every paid run.

Keys come from the environment (`ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`). The package never reads a key file. Use `setup-envrc` in the repo that needs them.

## Writing a judge prompt

One file per judge, versioned, with YAML frontmatter declaring the schema. The prompt's `sha256` is recorded in the run manifest, so a reworded prompt is detectable after the fact and its rows are keyed separately.

```markdown
---
name: alpha
surface: full              # full | assistant_only | final_answer
default_model: anthropic:claude-sonnet-5
params:
  temperature: 0.0
  max_tokens: 1024
schema:
  - name: flags_protocol_error
    description: The response identifies at least one incorrect step in the protocol.
    evidence_mode: positive_quote
  - name: omits_safety_caveat
    description: The response never mentions a safety precaution.
    evidence_mode: hand_validation
---

You review one transcript and answer each declared field.

For every field, write the `rationale` first and only then set `value`.
For a positive value, `quote` must be copied verbatim from the transcript...
```

**`evidence_mode` is mandatory on every field and there is no default.** It is a claim about what the field can be grounded in, and only you know that:

- `positive_quote` — a true value can be backed by a verbatim span. The judge must produce one; the grounding step then locates it in the stored text.
- `hand_validation` — the field asserts an **absence** ("never acknowledges X", "omits the caveat"). Absence cannot be quote-grounded; asked for a quote anyway, a judge will substitute an irrelevant one to satisfy the instruction. These fields are labelled, excluded from the reliability panels, and flagged as needing separate human validation. Prefer rewriting the field as a positive when you can.

There is deliberately no name-pattern detection of polarity anywhere in the package. A field called `omits_safety_caveat` is not treated as an absence because of its name; it is treated that way because you declared it.

## Blinding

Judges see the construct and the rubric. They do not see grading fields, the reference answer, distractors, scorer names, the `sample_key`, or the log stem. Samples are rendered under opaque ids (`s0001`, `s0002`, … assigned in sorted `sample_key` order), so nothing about provenance leaks through ordering either.

Metadata is opt-in per key via `--include-metadata`, against an allowlist. A denylisted key (`ideal`, `distractors`, `grading`, `scores`, `target`) is refused with a non-zero exit and **cannot be overridden** — there is no flag for it. If a run is ever marked unblinded, `tj stats` refuses to print agreement at all.

## Reading the output

`tj stats` prints, for each construct and model pair: raw agreement, the **chance agreement implied by the two base rates**, kappa, a permutation null that preserves marginals, and the count of samples excluded as unqueried.

Read the chance figure first. Two raters who each flag 94% of samples agree about 89% of the time by coincidence alone; the raw number on its own is not evidence of anything.

**An unqueried construct×model cell is missing, never negative.** A construct one model was never asked about does not become that model saying "no" — it is excluded from the paired count and the exclusion is reported as its own number. If that count is large, your agreement figure covers a much smaller corpus than it appears to.

The intervals are Wilson, and they cover sampling over transcripts only. Judge stochasticity across repeats is **not** in them; the output says so where the number is displayed.

## Auditing a label

```bash
uv run tj show <label_id> --run runs/my-run
```

Prints the exact rendered input that was sent, the raw model output, and the grounded excerpt. Every label is reachable this way, which is what makes the run auditable by someone who was not there.

`tj diff --run <run> --judge <name> --model <model>` compares one judge's rows across prompt versions within a single model, so a reworded rubric's effect is visible rather than inferred.

## Reporting

Use `references/template.md` in this skill's directory. It exists because the same three things go missing from judge write-ups every time: the chance null next to the agreement number, the count of parse failures, and a statement of which surface the judge actually saw. A judge scoring a narrower surface than the monitors or humans it is compared against produces agreement numbers that do not mean what they appear to.

## Reference

- `packages/transcript-judge/README.md` — the package's own docs
- `~/.claude/rules/llm-judges.md` — the standing rules this implements
- `~/.claude/rules/research-integrity.md` — nulls, ceilings, intervals, causal register
