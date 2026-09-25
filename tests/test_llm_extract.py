"""Tests for the LLM layer using a fake provider (no network, no API key)."""
import json

import pytest
from pydantic import BaseModel

from src import config
from src.llm import client as extract_module
from src.llm import extract


class Pack(BaseModel):
    grams: int
    price_inr: float


class FakeProvider:
    name = "fake"
    model = "fake-1"

    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    def generate_json(self, prompt: str) -> str:
        self.calls += 1
        return self.reply


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Point caches at a temp folder so tests never touch real project data."""
    monkeypatch.setattr(config, "LLM_CACHE_DIR", tmp_path / "llm")
    monkeypatch.setattr(config, "REVIEW_QUEUE", tmp_path / "review.jsonl")
    monkeypatch.setattr(extract_module._limiter, "min_interval", 0)


def test_valid_reply_is_parsed_and_cached():
    provider = FakeProvider('{"grams": 250, "price_inr": 650}')
    first = extract(provider, "prompt A", Pack, row_id="r1")
    second = extract(provider, "prompt A", Pack, row_id="r1")
    assert first == Pack(grams=250, price_inr=650)
    assert second == first
    assert provider.calls == 1  # second call came from the cache


def test_invalid_reply_goes_to_review_queue():
    provider = FakeProvider('{"grams": "a quarter kilo"}')
    assert extract(provider, "prompt B", Pack, row_id="r2") is None
    lines = config.REVIEW_QUEUE.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["row_id"] == "r2"
