"""Gemini implementation of LLMProvider (planned for Phase 3).

This is the only file that knows about Google's SDK. Swapping providers
means writing a sibling file with the same `name`, `model` and
`generate_json` members.
"""
import os

from src import config


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str | None = None):
        # Imported here, not at the top, so the rest of the project works
        # even if the google-genai package is not installed yet.
        from google import genai

        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self._client = genai.Client(api_key=config.get_secret("GEMINI_API_KEY"))

    def generate_json(self, prompt: str) -> str:
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            # Asks Gemini to reply with bare JSON (no prose, no ``` fences).
            config={"response_mime_type": "application/json", "temperature": 0},
        )
        return response.text
