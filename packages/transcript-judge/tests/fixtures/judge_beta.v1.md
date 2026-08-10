---
name: beta
surface: full
default_model: openrouter:openai/gpt-5.6-sol
params:
  temperature: 0.0
  max_tokens: 1024
schema:
  - name: identifies_incorrect_step
    description: The response names a step of the protocol that is wrong.
    evidence_mode: positive_quote
---

You review one transcript and answer the declared field.

Write the `rationale` first, then set `value`, then supply a verbatim `quote` and its `message_index`. Do not infer what you cannot quote.
