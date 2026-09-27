"""The Gemini client must not retry on its own (no network: the client is only built)."""
from src.llm.gemini import GeminiProvider


def test_sdk_retries_are_off(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    provider = GeminiProvider(model="gemini-3.8-flash")
    retry = provider._client._api_client._http_options.retry_options
    assert retry is not None and retry.attempts == 1
