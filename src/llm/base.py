"""The contract every LLM provider must satisfy."""
from typing import Protocol


class RetryableError(Exception):
    """A temporary failure worth retrying: rate limited (429) or overloaded (503).

    Providers translate their own SDK's errors into this, so the retry logic in
    src/llm/retry.py works the same whichever provider is used.
    """

    def __init__(self, status: int, message: str = ""):
        super().__init__(f"{status}: {message}")
        self.status = status


class LLMProvider(Protocol):
    """Anything with these attributes and this method counts as a provider.

    `Protocol` means providers don't need to inherit from this class; they
    just need matching attributes (so-called "duck typing", checked by type
    checkers). To add a provider, write a class like GeminiProvider.
    """

    name: str   # e.g. "gemini"; part of the cache key
    model: str  # e.g. "gemini-3.8-flash"; part of the cache key

    def generate_json(self, prompt: str) -> str:
        """Send `prompt` and return the raw text of a JSON response.

        Raise RetryableError for rate limits / overload; anything else propagates.
        """
        ...
