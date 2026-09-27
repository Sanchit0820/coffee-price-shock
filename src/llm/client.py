"""Cached, validated structured extraction.

extract() handles one object per call; extract_items() handles a batch, where
the model returns {"items": [...]} and every item is validated on its own, so
one bad item doesn't throw away the rest. Invalid answers go to the review
queue (data/review_queue.jsonl) for a human to check.

Every live call is rate-limited and retried with backoff on 429/503
(src/llm/retry.py). Cached answers are reused without a call.
"""
import json
import sys
from datetime import datetime, timezone
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from src import config
from src.llm import cache
from src.llm.base import LLMProvider
from src.llm.retry import call_with_backoff
from src.ratelimit import RateLimiter

# T stands for "whichever pydantic model the caller passes in", so the return
# type matches the schema (extract(..., ProductInfo, ...) -> ProductInfo | None).
T = TypeVar("T", bound=BaseModel)

_limiter = RateLimiter(config.LLM_DELAY_SECONDS)


def _log_retry(attempt: int, err: Exception, delay: float) -> None:
    print(f"  LLM retry {attempt} after {err} (waiting {delay:.0f}s)", file=sys.stderr, flush=True)


def _one_call(provider: LLMProvider, prompt: str) -> str:
    _limiter.wait(provider.name)   # every attempt, retries included, respects the pace
    return provider.generate_json(prompt)


def _get_response(provider: LLMProvider, prompt: str) -> str:
    """Return the cached response, or call the provider (paced, with backoff) and cache it."""
    cached = cache.get(provider.name, provider.model, prompt)
    if cached is not None:
        return cached
    response = call_with_backoff(_one_call, provider, prompt, on_retry=_log_retry)
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


def extract_items(provider: LLMProvider, prompt: str, item_schema: type[T],
                  refs: list[str], context: dict | None = None) -> dict[str, T]:
    """Batch version: the prompt asks for {"items": [{"ref": ..., ...}, ...]}.

    Each item is validated separately against item_schema (with `context`
    passed to pydantic validators, e.g. the input text for evidence checks).
    Returns {ref: object} for valid items whose ref was asked for. Invalid,
    unexpected or missing items are logged to the review queue; callers can
    retry the missing refs one by one.
    """
    response = _get_response(provider, prompt)
    try:
        items = json.loads(response)["items"]
        assert isinstance(items, list)
    except (ValueError, KeyError, TypeError, AssertionError) as err:
        for ref in refs:
            _send_to_review(ref, provider, response, f"batch not parseable: {err}")
        return {}
    wanted, out = set(refs), {}
    for raw in items:
        ref = str(raw.get("ref", "")) if isinstance(raw, dict) else ""
        if ref not in wanted or ref in out:
            _send_to_review(ref or "?", provider, json.dumps(raw, ensure_ascii=False),
                            "unexpected or duplicate ref in batch")
            continue
        try:
            out[ref] = item_schema.model_validate(raw, context=context)
        except ValidationError as err:
            _send_to_review(ref, provider, json.dumps(raw, ensure_ascii=False), str(err))
    for ref in wanted - set(out):
        if not any(isinstance(r, dict) and str(r.get("ref")) == ref for r in items):
            _send_to_review(ref, provider, "", "missing from batch response")
    return out
