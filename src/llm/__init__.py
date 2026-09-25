"""Provider-agnostic LLM layer.

Pipeline code uses only `extract()` and an `LLMProvider`; the concrete
provider (Gemini today) is chosen in one place, so it can be swapped.
"""
from src.llm.base import LLMProvider
from src.llm.client import extract

__all__ = ["LLMProvider", "extract"]
