# Judge run: <construct or hypothesis>

<!--
Fill every section or delete it. Never leave "TBD" — a blank section is a
finding ("we did not measure this"), a "TBD" is a promise nobody kept.

The four things that go missing from judge write-ups, in order of frequency:
the chance null beside the agreement number, the parse-failure count, which
surface the judge actually saw, and the fact that the interval covers sampling
over transcripts but not judge stochasticity across repeats.
-->

## What was asked

**Hypothesis.** <the claim the labels are meant to bear on, in one sentence>

**Constructs.** For each field: name, `evidence_mode`, and why that mode. An absence-asserting field must say here that it is hand-validated and cannot be quote-grounded.

**Why a judge and not a regex.** One sentence naming the paraphrase or quotation failure a keyword list would have made here.

## What the judge saw

| | |
|---|---|
| Surface | `full` / `final_answer` / `cot` — exactly what was rendered |
| Corpus | n samples, source paths, `transcripts_sha256` |
| Blinded | yes/no; if metadata was included, which keys and why |
| Models | provider:model per cell |
| Prompt | file path and `sha256` per judge |
| Params | temperature, max_tokens |

Blinding perimeter: judges saw the construct and rubric only. Grading fields, reference answers, distractors, scorer names, `sample_key` and the log stem were withheld; samples were rendered under opaque ids.

## Yield

| Cell (judge / prompt sha / model) | Samples | Parse OK | Parse failures | Labels |
|---|---|---|---|---|

**Parse failures: n.** Report the number even when it is zero; never silently drop the rows. If any row failed, say what the failure was.

**Grounding.** Of the positive `positive_quote` labels, how many resolved at each tier (`exact` / `nfc` / `punct_fold` / `ws_collapse`) and how many stayed `unresolved`. Unresolved labels are counted, never dropped.

## Rates

For each construct: the positive rate with a **Wilson** interval, and the denominator as a count next to it (0/7, not "0%").

State what the interval covers: sampling over transcripts only. Judge stochasticity across repeats is not included — say so here, next to the number, not only in the limitations section.

## Agreement, and its null

| Construct | Models | Raw agreement | Chance (from base rates) | Kappa | Permutation p | n paired | Excluded as unqueried |
|---|---|---|---|---|---|---|---|

**Read the chance column first.** Two raters flagging 94% each agree ~89% of the time by coincidence. The raw figure alone is uninterpretable.

**Unqueried cells are missing, not negative.** The excluded count is the number of samples one model was never asked about; they are not counted as that model saying "no". If the count is large, the agreement figure covers a much smaller corpus than the header suggests.

**Ceiling.** If you have a repeat of the same model on the same corpus, state it — the same instrument measured twice bounds how much any between-model difference can mean.

## Clusters

Constructs the merge judge grouped as equivalent, and the contradictory triads it produced (count, and where the file is). Complete-link grouping is used because pairwise LLM equivalence is not transitive; a contradiction means the judge said A≡B and B≡C but A≢C, and it is a signal about the constructs, not a bug to hide.

## What the labels show

Findings in the associational register by default — "associated with", "consistent with", "higher in the X condition", "we observe". Reserve causal verbs for tested mechanism or an RCT-style design.

Report the conditions that did not work alongside the ones that did.

## Audit trail

- Run directory: `<path>`
- Reproduce: `tj show <label_id> --run <path>` for any label — prints the exact rendered input, the raw model output, and the grounded excerpt
- Manifest: `tj manifest --run <path>`
- Overlap artifact: `<path>/artifact/overlap.html`

## Limitations

At minimum: judge stochasticity is unmeasured unless you ran repeats; the hand-validated fields are unvalidated until someone reads them; the corpus is whatever it is and does not generalize past it.
