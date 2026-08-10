---
name: unknown_param
surface: full
default_model: anthropic:claude-sonnet-5
params:
  max_tokens: 500
  top_p: 0.9
schema:
  - name: flags_something
    description: Declares a param no provider forwards, alongside one that is forwarded.
    evidence_mode: positive_quote
---

Body is irrelevant; this file exists to be refused. `top_p` is recorded by the
manifest and dropped by every provider, so accepting it would describe a
sampling regime the request never carried.
