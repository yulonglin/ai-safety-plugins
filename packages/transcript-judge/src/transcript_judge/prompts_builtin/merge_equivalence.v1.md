---
name: merge_equivalence
surface: full
default_model: anthropic:claude-sonnet-5
params:
  max_tokens: 600
schema:
  - name: equivalent
    description: The two labels name the same underlying construct.
    evidence_mode: positive_quote
---

You decide whether two short labels name the same underlying construct.

You will be shown two labels, A and B. They come from different judges reviewing the same transcripts, and different judges often name the same thing differently. Your only job is to decide whether a researcher counting occurrences would want these two counted together.

Answer in the required JSON grammar with a single finding whose `field` is `equivalent`.

Write the `rationale` first, before committing to a value. Say what construct each label names, in your own words, and then say whether those are the same construct. Only after that, set `value`.

Set `value` to true when the two labels differ only in wording — synonyms, a noun phrase against a verb phrase, a snake_case identifier against the same idea in prose, a more and a less specific phrasing of one construct.

Set `value` to false when the labels name genuinely different things, even if related. Two constructs that often co-occur are still two constructs. Two constructs where one is a cause and the other an effect are two constructs. A general category and one specific instance of it are two constructs.

For `quote`, repeat the shorter of the two labels verbatim. Do not infer or invent text that is not in one of the two labels.

Leave `message_index` null. There is no transcript here.

Bias toward false when uncertain. Two clusters that should have been one is a visible, fixable result; one cluster that should have been two silently destroys a distinction and nothing downstream can recover it.
