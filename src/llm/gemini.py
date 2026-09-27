"""Gemini implementation of LLMProvider (planned for Phase 3).

This is the only file that knows about Google's SDK. Swapping providers
means writing a sibling file with the same `name`, `model` and
`generate_json` members.
"""
import os

from src import config
from src.llm.base import RetryableError

RETRYABLE_STATUS = {429, 503}   # rate limited, overloaded ("high demand")


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str | None = None):
        # Imported here, not at the top, so the rest of the project works
        # even if the google-genai package is not installed yet.
        from google import genai
        from google.genai import types

        # gemini-2.5-flash is closed to new API keys (404 as of Sep 2026).
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        # attempts=1 turns OFF the SDK's own retries (default 5 per call). Our
        # backoff in src/llm/retry.py is the only retry layer; with both on, one
        # call could become 6 x 5 = 30 requests during a 503 spell, and every
        # request counts against the free-tier quota.
        self._client = genai.Client(
            api_key=config.get_secret("GEMINI_API_KEY"),
            http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)))

    def generate_json(self, prompt: str) -> str:
        from google.genai import errors

        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                # Asks Gemini to reply with bare JSON (no prose, no ``` fences).
                # Automatic function calling is off: we never give the model tools,
                # and leaving it on only makes the SDK print a warning.
                config={"response_mime_type": "application/json", "temperature": 0,
                        "automatic_function_calling": {"disable": True}},
            )
        except errors.APIError as err:
            # Translate Google's error into the provider-agnostic one the
            # retry logic understands; every other error stays as it is.
            if err.code in RETRYABLE_STATUS:
                raise RetryableError(err.code, err.message or "") from err
            raise
        return response.text
