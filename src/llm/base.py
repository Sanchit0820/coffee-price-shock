"""The contract every LLM provider must satisfy."""
from typing import Protocol


class LLMProvider(Protocol):
    """Anything with these attributes and this method counts as a provider.

    `Protocol` means providers don't need to inherit from this class; they
    just need matching attributes (so-called "duck typing", checked by type
    checkers). To add a provider, write a class like GeminiProvider.
    """

    name: str   # e.g. "gemini"; part of the cache key
    model: str  # e.g. "gemini-2.5-flash"; part of the cache key

    def generate_json(self, prompt: str) -> str:
        """Send `prompt` and return the raw text of a JSON response."""
        ...
