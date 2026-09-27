"""Backoff on 429/503 and per-item batch validation (no network)."""
import json

import pytest
from pydantic import BaseModel

from src import config
from src.llm import client as client_module
from src.llm.base import RetryableError
from src.llm.client import extract_items
from src.llm.retry import backoff_delays, call_with_backoff


def test_backoff_delays_double_and_cap():
    assert backoff_delays() == [2, 4, 8, 16, 32]
    assert backoff_delays(attempts=8, cap=60) == [2, 4, 8, 16, 32, 60, 60]


def test_retries_then_succeeds():
    calls, waits = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RetryableError(503, "high demand")
        return "ok"

    assert call_with_backoff(flaky, sleep=waits.append, jitter=lambda: 0) == "ok"
    assert waits == [2, 4]            # two retries, doubling


def test_gives_up_after_max_attempts():
    waits = []

    def always_429():
        raise RetryableError(429, "rate limited")

    with pytest.raises(RetryableError):
        call_with_backoff(always_429, sleep=waits.append, jitter=lambda: 0, attempts=3)
    assert waits == [2, 4]


def test_other_errors_are_not_retried():
    waits = []

    def bad_request():
        raise ValueError("400 bad request")

    with pytest.raises(ValueError):
        call_with_backoff(bad_request, sleep=waits.append)
    assert waits == []


# ---------- batch validation ----------

class Item(BaseModel):
    ref: str
    n: int


class FakeProvider:
    name, model = "fake", "fake-1"

    def __init__(self, reply):
        self.reply = reply

    def generate_json(self, prompt):
        return self.reply


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LLM_CACHE_DIR", tmp_path / "llm")
    monkeypatch.setattr(config, "REVIEW_QUEUE", tmp_path / "review.jsonl")
    monkeypatch.setattr(client_module._limiter, "min_interval", 0)


def review_lines():
    return [json.loads(line) for line in config.REVIEW_QUEUE.read_text(encoding="utf-8").splitlines()]


def test_batch_keeps_good_items_and_reviews_bad_ones():
    reply = json.dumps({"items": [{"ref": "a", "n": 1}, {"ref": "b", "n": "not a number"},
                                  {"ref": "zzz", "n": 3}]})
    out = extract_items(FakeProvider(reply), "prompt 1", Item, ["a", "b", "c"])
    assert set(out) == {"a"}
    reasons = {r["row_id"]: r["error"] for r in review_lines()}
    assert "b" in reasons                              # invalid item
    assert "unexpected" in reasons["zzz"]              # not asked for
    assert "missing" in reasons["c"]                   # never returned


def test_unparseable_batch_reviews_every_ref():
    out = extract_items(FakeProvider("not json"), "prompt 2", Item, ["a", "b"])
    assert out == {}
    assert {r["row_id"] for r in review_lines()} == {"a", "b"}
