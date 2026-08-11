from __future__ import annotations

from google import genai

from core.config import settings


class AIEngine:
    def __init__(self) -> None:
        self.client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None
        self.model = "gemini-2.5-flash"

    def ask(self, prompt: str, system: str | None = None) -> str:
        if not self.client:
            return "AI is not configured yet. Set GEMINI_API_KEY in the environment."
        contents = f"System: {system}\n\nUser: {prompt}" if system else prompt
        response = self.client.models.generate_content(model=self.model, contents=contents)
        return response.text or "No response generated."


ai_engine = AIEngine()
