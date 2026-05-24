from openai import OpenAI
from xhs_research.config import AISettings


class AIClient:
    def __init__(self, settings: AISettings):
        kwargs = {"api_key": settings.api_key or "sk-placeholder"}
        if settings.base_url:
            kwargs["base_url"] = settings.base_url
        self.client = OpenAI(**kwargs)
        self.model = settings.model

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.3) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""
