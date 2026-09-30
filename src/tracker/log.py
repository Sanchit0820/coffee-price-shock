"""Error and warning lines that GitHub Actions shows as annotations on the run
page (::error:: / ::warning::); plain "ERROR:" / "WARNING:" elsewhere."""
import os
import sys

_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"


def error(msg: str) -> None:
    print(f"::error::{msg}" if _ACTIONS else f"ERROR: {msg}", file=sys.stderr, flush=True)


def warning(msg: str) -> None:
    print(f"::warning::{msg}" if _ACTIONS else f"WARNING: {msg}", file=sys.stderr, flush=True)
