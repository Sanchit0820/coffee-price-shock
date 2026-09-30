"""Monthly live tracker.

    python -m src.tracker.run                  # this month
    python -m src.tracker.run --no-llm         # new products stay "pending"

1. robots.txt re-check, then this month's products.json per roaster (snapshot.py)
2. LLM attributes for products not seen before (attributes.py)
3. Tracker tables and chart (analysis.py), README "last run" line

Nothing is written until everything is built and checked. Every output is
first written next to its target as "<name>.tmp", then each is swapped into
place in one step (os.replace). If any step fails, the job logs an error,
deletes the .tmp files and exits 1, leaving the committed data as it was.

The job fails when MAX_FAILED or more roasters return an error. A roaster
skipped because robots.txt disallows it (or can't be read) is logged but is
not a failure: skipping is the rule working.
"""
import argparse
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from src import config
from src.tracker import analysis, attributes, snapshot
from src.tracker.log import error, warning

MAX_FAILED = 4
README = config.PROJECT_ROOT / "README.md"
MARK_START, MARK_END = "<!-- tracker:last-run -->", "<!-- /tracker:last-run -->"


class TrackerError(Exception):
    """A check failed: stop without writing anything."""


def log_status(status: pd.DataFrame) -> None:
    for s in status.itertuples():
        if s.status == "error":
            error(f"{s.roaster}: fetch failed - {s.error}")
        elif s.status == "skipped_robots":
            warning(f"{s.roaster}: skipped, robots.txt status '{s.robots}' "
                    "(cloud servers are sometimes blocked; not a scraper fault)")
        if s.big_drop:
            warning(f"{s.roaster}: {s.n_products} products vs {s.prev_products} last month (big drop)")
        print(f"  {s.roaster}: {s.status} ({s.n_products} products)", flush=True)


def check(monthly_old: pd.DataFrame, monthly: pd.DataFrame, status: pd.DataFrame,
          roasters: list[dict], attrs: pd.DataFrame) -> None:
    """Sanity checks before anything is written. Raises TrackerError."""
    if list(monthly.columns) != snapshot.COLUMNS:
        raise TrackerError("live_monthly columns changed")
    old = monthly.iloc[:len(monthly_old)].reset_index(drop=True)
    if not old.fillna("").equals(monthly_old.reset_index(drop=True).fillna("")):
        raise TrackerError("earlier months' rows would change")
    missing = {r["roaster"] for r in roasters} - set(status.roaster)
    if missing:
        raise TrackerError(f"no status for {sorted(missing)}")
    failed = status[status.status == "error"]
    if len(failed) >= MAX_FAILED:
        raise TrackerError(f"{len(failed)} of {len(status)} roasters failed "
                           f"({', '.join(failed.roaster)}); limit is {MAX_FAILED - 1}")
    if len(attrs) and attrs.duplicated(["roaster", "product_id"]).any():
        raise TrackerError("duplicate products in tracker_attributes")


def last_run_line(month: str, status: pd.DataFrame, attrs: pd.DataFrame, n_new: int) -> str:
    n = status.status.value_counts()
    pending = int((attrs.status == "pending").sum()) if len(attrs) else 0
    return (f"**Last run: {date.today().isoformat()}** (snapshot {month}). "
            f"Roasters fetched: {n.get('fetched', 0)}; already had this month's data: "
            f"{n.get('already_fetched', 0) + n.get('seeded_phase2', 0)}; skipped by robots.txt: {n.get('skipped_robots', 0)}; "
            f"switched off: {n.get('skipped_disabled', 0)}; failed: {n.get('error', 0)}. "
            f"New products this run: {n_new}; attributes pending: {pending}.")


def with_last_run(readme: str, line: str) -> str:
    start, end = readme.find(MARK_START), readme.find(MARK_END)
    if start < 0 or end < start:
        raise TrackerError("README has no tracker last-run markers")
    return readme[:start + len(MARK_START)] + "\n" + line + "\n" + readme[end:]


def build(month: str, make_provider) -> dict[Path, object]:
    """Everything the run will write: {target path: DataFrame, str (text) or Path (a rendered file)}."""
    roasters = snapshot.tracker_roasters()
    monthly_old = snapshot.load_monthly()
    print(f"snapshot {month}: {len(roasters)} roasters", flush=True)
    monthly, status = snapshot.take_snapshot(month, monthly_old, roasters)
    if not snapshot.STATUS.exists():
        # Very first run: the rows already there are Phase 2's live snapshot. Record
        # that, since "already_fetched" rows are otherwise not written (merge_status).
        status.loc[status.status == "already_fetched", "status"] = "seeded_phase2"
    log_status(status)
    desc = {}
    for r in roasters:
        if (status[status.roaster == r["roaster"]].status == "fetched").any():
            desc |= {(r["roaster"], pid): t for pid, t in snapshot.descriptions(r, month).items()}
    # Snapshot checks first, so a failed month costs no LLM calls; then the attributes.
    check(monthly_old, monthly, status, roasters, pd.DataFrame())
    n_inputs_before = len(attributes._read(attributes.INPUTS))
    att = attributes.update(month, monthly[monthly.month == month], desc, make_provider)
    check(monthly_old, monthly, status, roasters, att["attributes"])
    lookup = analysis.coffee_lookup(attributes._read(attributes.PHASE3), att["attributes"])
    tables = analysis.build(monthly, lookup, status, month)
    chart = Path(tempfile.mkdtemp(prefix="tracker_chart_")) / "tracker_index.png"
    analysis.chart(tables["index"], chart)
    line = last_run_line(month, status, att["attributes"], len(att["inputs"]) - n_inputs_before)
    print(line, flush=True)
    return {
        snapshot.MONTHLY: monthly,
        snapshot.STATUS: snapshot.merge_status(snapshot.load_status(), status),
        attributes.INPUTS: att["inputs"],
        attributes.ATTRIBUTES: att["attributes"],
        attributes.REVIEW: att["review"],
        analysis.OUT / "tracker_index.csv": tables["index"],
        analysis.OUT / "tracker_changes.csv": tables["changes"],
        analysis.OUT / "tracker_summary.csv": tables["summary"],
        analysis.OUT / "tracker_index.png": chart,
        README: with_last_run(README.read_text(encoding="utf-8"), line),
    }


def write_all(outputs: dict[Path, object]) -> None:
    """Write every output as <target>.tmp, then swap each into place."""
    tmps = []
    try:
        for target, content in outputs.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".tmp")
            tmps.append((tmp, target))
            if isinstance(content, pd.DataFrame):
                content.to_csv(tmp, index=False)
            elif isinstance(content, Path):
                tmp.write_bytes(content.read_bytes())
            else:
                tmp.write_text(content, encoding="utf-8")
        for tmp, target in tmps:
            os.replace(tmp, target)
    finally:
        for tmp, _ in tmps:
            tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Monthly live price tracker")
    p.add_argument("--month", default=snapshot.month_label(), help="snapshot label, YYYY-MM")
    p.add_argument("--no-llm", action="store_true", help="don't call the LLM; new products stay pending")
    args = p.parse_args(argv)

    def no_llm():
        raise RuntimeError("LLM switched off (--no-llm)")

    try:
        outputs = build(args.month, no_llm if args.no_llm else attributes.gemini)
        write_all(outputs)
    except Exception as err:  # noqa: BLE001 - log it, write nothing, fail the job
        error(f"tracker stopped, nothing written: {type(err).__name__}: {err}")
        return 1
    print(f"wrote {len(outputs)} files", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
