"""Cached, validated structured extraction.

extract() is what pipeline code calls. It returns a pydantic object when the
LLM's answer is valid, or None after logging the bad answer to the review
queue (data/review_queue.jsonl) for a human to check.
"""
import json
from datetime import datetime, timezone
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from src import config
from src.llm import cache
from src.llm.base import LLMProvider
from src.ratelimit import RateLimiter

# T stands for "whichever pydantic model the caller passes in", so the return
# type matches the schema (extract(..., ProductInfo, ...) -> ProductInfo | None).
T = TypeVar("T", bound=BaseModel)

_limiter = RateLimiter(config.LLM_DELAY_SECONDS)


def _get_response(provider: LLMProvider, prompt: str) -> str:
    """Return the cached response, or call the provider (rate-limited) and cache it."""
    cached = cache.get(provider.name, provider.model, prompt)
    if cached is not None:
        return cached
    _limiter.wait(provider.name)
    response = provider.generate_json(prompt)
    cache.put(provider.name, provider.model, prompt, response)
    return response


def _send_to_review(row_id: str, provider: LLMProvider, response: str, error: str) -> None:
    config.REVIEW_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "row_id": row_id,
        "provider": provider.name,
        "model": provider.model,
        "response": response,
        "error": error,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    # "a" = append: one JSON object per line (JSON Lines format).
    with config.REVIEW_QUEUE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def extract(provider: LLMProvider, prompt: str, schema: type[T], row_id: str) -> T | None:
    """Ask the LLM, validate its JSON against `schema`, and return the parsed object.

    `row_id` identifies the source row (e.g. a product URL + snapshot date)
    so a failed row can be traced back from the review queue.
    """
    response = _get_response(provider, prompt)
    try:
        return schema.model_validate_json(response)
    except ValidationError as err:
        _send_to_review(row_id, provider, response, str(err))
        return None
