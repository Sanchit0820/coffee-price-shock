"""Disk cache for LLM responses: one JSON file per (provider, model, prompt).

Re-running the pipeline costs no API calls and gives identical results.
Changing the prompt or the model produces a new key and therefore a new call.
"""
import hashlib
import json
from datetime import datetime, timezone

from src import config


def _path(provider: str, model: str, prompt: str):
    # "\x00" separates the parts so ("ab", "c") and ("a", "bc") hash differently.
    raw = f"{provider}\x00{model}\x00{prompt}".encode("utf-8")
    return config.LLM_CACHE_DIR / f"{hashlib.sha256(raw).hexdigest()}.json"


def get(provider: str, model: str, prompt: str) -> str | None:
    path = _path(provider, model, prompt)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))["response"]


def put(provider: str, model: str, prompt: str, response: str) -> None:
    path = _path(provider, model, prompt)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "provider": provider,
        "model": model,
        "prompt": prompt,
        "response": response,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
