"""Project paths and settings, loaded once from .env.

Every other module imports paths from here instead of building its own,
so moving a folder means changing one line.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# src/config.py -> parent is src/, parent.parent is the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"            # cached HTTP responses (never re-fetched)
CLEAN_DIR = DATA_DIR / "clean"        # tidy tables produced by the pipeline
LLM_CACHE_DIR = DATA_DIR / "cache" / "llm"
REVIEW_QUEUE = DATA_DIR / "review_queue.jsonl"  # LLM rows that failed validation
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# Reads .env into os.environ. Existing environment variables are not overwritten.
load_dotenv(PROJECT_ROOT / ".env")

SCRAPE_DELAY_SECONDS = float(os.getenv("SCRAPE_DELAY_SECONDS", "5"))
LLM_DELAY_SECONDS = float(os.getenv("LLM_DELAY_SECONDS", "6"))
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "")


def get_secret(name: str) -> str:
    """Return a required secret from the environment, or fail with a clear message."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return value
