"""Smoke test for the Gemini connection: one tiny live call, no cache.

    python -m src.llm.smoke

1. Lists the models this API key can use and checks GEMINI_MODEL is one of
   them and supports text generation.
2. Sends one tiny prompt through GeminiProvider and prints the reply.

The API key is never printed. Error messages are passed through redact()
in case a library ever echoes the key back.
"""
import os

from src import config
from src.llm.gemini import GeminiProvider

PROMPT = 'Reply with exactly this JSON and nothing else: {"ok": true}'


def redact(text: str) -> str:
    key = os.getenv("GEMINI_API_KEY") or ""
    return text.replace(key, "[REDACTED]") if key else text


def model_available(provider: GeminiProvider) -> bool:
    """True if the key can see provider.model with generateContent support."""
    wanted = f"models/{provider.model}"
    for m in provider._client.models.list():
        if m.name == wanted:
            actions = getattr(m, "supported_actions", None) or []
            return not actions or "generateContent" in actions
    return False


def main() -> None:
    config.get_secret("GEMINI_API_KEY")  # clear error if missing; value not printed
    provider = GeminiProvider()
    print(f"Model: {provider.model}")
    try:
        # Being listed does NOT prove the model is usable (gemini-2.5-flash was
        # listed but refused for new users); only the call below proves that.
        print(f"Listed for this key: {model_available(provider)}")
        reply = provider.generate_json(PROMPT)
        print(f"Reply: {reply}")
    except Exception as err:  # noqa: BLE001 - report any failure, key-free
        print(f"FAILED: {type(err).__name__}: {redact(str(err))}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
