"""OpenRouter: OpenAI-compatible body, different base URL, key and headers."""

from __future__ import annotations

from transcript_judge.providers.openai import ChatCompletionsClient

BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

#: Optional attribution headers OpenRouter uses for its dashboards.
REFERER = "https://github.com/anthropics/ai-safety-plugins"
TITLE = "transcript-judge"


class OpenRouterClient(ChatCompletionsClient):
    provider = "openrouter"
    base_url = BASE_URL

    def extra_headers(self) -> dict[str, str]:
        return {"HTTP-Referer": REFERER, "X-Title": TITLE}
