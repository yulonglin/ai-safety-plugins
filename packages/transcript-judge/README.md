# transcript-judge

One importable pipeline for transcript review with LLM judges: load transcripts, fan out blinded judge prompts, ground every label back to an exact character span, cluster equivalent labels across judges, and emit an interactive overlap artifact.

Judge conduct is governed by `claude/rules/llm-judges.md` in dotfiles; this package is the machinery.

## Install

```bash
uv run --project packages/transcript-judge tj --help
```

The Inspect `.eval` loader is an optional extra, imported lazily:

```bash
uv run --project packages/transcript-judge --with inspect-ai tj load <path.eval>
```

## Pipeline

```
tj load     transcripts -> runs/<run_id>/transcripts.jsonl (+ manifest)
tj run      one API call per sample per judge cell -> judgements/<judge>.jsonl
tj labels   parsed findings -> grounded labels.jsonl (quote -> exact char span)
tj cluster  merge-judge pairwise equivalence -> clusters/assignments.json
tj stats    Wilson intervals, chance-agreement nulls, kappa, permutation test
tj artifact overlap.json + self-contained overlap.html
```

Inspection is one step from any label: `tj show <label_id> --part input|output|excerpt|all`.

## The unit of measurement is the cell

A **judge cell** is the triple `(judge_name, prompt_sha256, model_id)`. Resume, the manifest, `label_id`, and `tj diff` all key on the cell — never on the judge name alone. Editing a prompt changes its sha256, so every sample becomes a cache miss under the new sha while the old rows stay untouched in the same append-only file.

## API keys

Read from the environment only (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`). The package never reads a key file.
