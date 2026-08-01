---
name: openrouter-fusion
description: Use when querying OpenRouter — invoking the openrouter:fusion server tool for
  multi-model synthesis on deep-research / compare-and-contrast prompts, or for a quick
  reference on auth, the /models endpoint, and the /chat/completions request format.
---

# OpenRouter Fusion & API Reference

## Fusion: Multi-Model Synthesis

**When to invoke:** Research questions, multi-domain critique, compare-and-contrast tasks.
Fusion adds latency and cost — skip it for simple factual lookups or generation tasks.

### How it works

1. Your prompt is dispatched to all panel models **in parallel**, each with access to `openrouter:web_search` and `openrouter:web_fetch`.
2. A judge model synthesizes their outputs into a structured analysis.
3. The entire pipeline is server-side — one API call from your side.

### Minimal request

```python
import httpx, os

resp = httpx.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
    json={
        "model": "anthropic/claude-opus-4-8",
        "messages": [{"role": "user", "content": "Your research question"}],
        "tools": [{"type": "openrouter:fusion"}],
        "tool_choice": "required",
    },
)
```

### Full Fusion parameters

```json
{
  "tools": [{
    "type": "openrouter:fusion",
    "parameters": {
      "analysis_models": [
        "deepseek/deepseek-v3.2",
        "~moonshotai/kimi-latest"
      ],
      "model": "~anthropic/claude-opus-latest",
      "max_tool_calls": 8,
      "max_completion_tokens": 4000,
      "reasoning": { "effort": "medium", "max_tokens": 10000 },
      "temperature": 1.0
    }
  }],
  "tool_choice": "required"
}
```

| Parameter | Range | Default | Notes |
|---|---|---|---|
| `analysis_models` | 1-8 models | Quality preset | Panel that answers in parallel |
| `model` | any slug | Outer model | Judge that synthesizes |
| `max_tool_calls` | 1-16 | 8 | Web search calls per panel model |
| `max_completion_tokens` | - | Provider default | Limits each panel response |
| `reasoning.effort` | low/medium/high | Provider default | Reasoning depth |
| `temperature` | 0-2 | Provider default | |

### Response structure

The synthesis contains these structured fields:
- `consensus` - points all panel models agreed on
- `contradictions` - where they disagreed
- `partial_coverage` - topics only some models addressed
- `unique_insights` - standout findings from individual models
- `blind_spots` - gaps across all responses

---

## OpenRouter API quick-reference

```
Base URL:  https://openrouter.ai/api/v1
Auth:      Authorization: Bearer $OPENROUTER_API_KEY
```

Optional headers (for usage leaderboard):
- `HTTP-Referer: <your-site>`
- `X-OpenRouter-Title: <your-app-name>`

### List available models

```bash
curl https://openrouter.ai/api/v1/models \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" | jq '.data[] | {id, context_length, pricing}'
```

The model catalog is dynamic - query it rather than hardcoding slugs. Browse at `openrouter.ai/models`.

### Minimal chat completion

```bash
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d '{"model":"~openai/gpt-latest","messages":[{"role":"user","content":"Hello"}]}'
```

API is OpenAI-compatible - any OpenAI SDK works with `base_url="https://openrouter.ai/api/v1"`.

### API key setup

Use `setup-envrc` to configure `OPENROUTER_API_KEY` per-project via direnv - not a global
export. Or `with-secrets OPENROUTER_API_KEY -- <cmd>` for one-shot access.
