"""LLM attributes for products the tracker hasn't seen before.

    data/clean/tracker_inputs.csv      each new product's titles and variants, from
                                       when it was first seen. NOT its description:
                                       that is the shop's own text, so it is read from
                                       this month's cached products.json (the runner's
                                       temporary space) and never committed. A product
                                       still pending next month gets next month's text.
    data/clean/tracker_attributes.csv  one row per new product: attributes, or
                                       status "pending"
    data/review/tracker_review.csv     products needing a person

Same prompt (attrs-v2), batch size, validation and post-processing rules as
Phase 3. "Seen before" = in Phase 3's product_attributes.csv, or already
labelled here.

If the API fails for ANY reason - quota used up (429), overloaded (503), bad or
missing key, network - the products not yet done are marked "pending" and the
run carries on; they are retried next month. After the first failure no
further calls are made, so a spent quota isn't hammered. The tracker's key is a
free-tier key in a project with no billing, so it can't incur charges; running
out of quota is expected and harmless.
"""
import pandas as pd

from src import config
from src.extract_attributes import (ALLOWED, PROMPT_VERSION, RUN_BATCH_SIZE, ProductAttributes,
                                    batch_prompt, postprocess, product_text, review_rows)
from src.llm.client import extract_items
from src.product_inputs import CAP, cap
from src.tracker.log import warning

INPUTS = config.CLEAN_DIR / "tracker_inputs.csv"
ATTRIBUTES = config.CLEAN_DIR / "tracker_attributes.csv"
REVIEW = config.DATA_DIR / "review" / "tracker_review.csv"
PHASE3 = config.CLEAN_DIR / "product_attributes.csv"
# Free tier allows about 20 requests a day; stay well under it. Anything left
# over is "pending" and done next month.
MAX_CALLS = 15


def _read(path) -> pd.DataFrame:
    """The CSV as text columns; empty if missing or written with no rows or columns."""
    try:
        return pd.read_csv(path, dtype=str).fillna("")
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def _keys(df: pd.DataFrame) -> set:
    return set(zip(df.roaster, df.product_id)) if len(df) else set()


def new_inputs(month_rows: pd.DataFrame, known: set, month: str) -> pd.DataFrame:
    """Committed input rows (no shop text) for products in this month's rows that
    aren't in `known`."""
    rows = []
    for (roaster, pid), g in month_rows.groupby(["roaster", "product_id"], sort=True):
        if (roaster, pid) in known:
            continue
        variants = list(dict.fromkeys(t for t in g.variant_title if t))
        rows.append({"roaster": roaster, "product_id": pid, "first_month": month,
                     "product_title": g.product_title.iloc[-1], "other_titles": "",
                     "product_type": g.product_type.iloc[-1],
                     "variant_titles": cap(" | ".join(variants), CAP["variant_titles"]),
                     "title_changed": False,
                     "is_coffee_guess_p2": g.is_coffee_guess.mode().iloc[0],
                     "is_bundle_p2": (g.is_bundle == "True").any()})
    return pd.DataFrame(rows)


def with_description(todo: pd.DataFrame, desc: dict) -> pd.DataFrame:
    """Add this month's description (in memory only). desc: (roaster, product_id) -> text."""
    return todo.assign(card_text="", description=[
        cap(desc.get(k, ""), CAP["description"]) for k in zip(todo.roaster, todo.product_id)])


def to_do(inputs: pd.DataFrame, attrs: pd.DataFrame) -> pd.DataFrame:
    """Inputs with no final result yet: never tried, or pending from an earlier run."""
    done = attrs[attrs.status != "pending"] if len(attrs) else attrs
    return inputs[[k not in _keys(done) for k in zip(inputs.roaster, inputs.product_id)]] \
        if len(inputs) else inputs


def extract(todo: pd.DataFrame, make_provider,
            max_calls: int = MAX_CALLS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Label `todo` in batches of 5, then retry invalid items one at a time.
    Never raises for API trouble: whatever isn't done is returned as "pending".
    Returns (one result row per product, todo with its ref and prompt text)."""
    todo = todo.reset_index(drop=True).copy()
    todo["ref"] = [f"t{i}" for i in range(len(todo))]
    todo["text"] = [product_text(r) for _, r in todo.iterrows()]
    context = {"inputs": dict(zip(todo.ref, todo.text))}
    results, attempted, retried, calls, failure = {}, set(), set(), 0, None
    provider = None
    try:
        provider = make_provider()
    except Exception as err:  # noqa: BLE001 - e.g. no key set: everything stays pending
        failure = err

    def call(batch: pd.DataFrame) -> bool:
        """One LLM call; False (and no more calls) after the first failure or at the cap."""
        nonlocal calls, failure
        if failure is not None or calls >= max_calls:
            return False
        try:
            results.update(extract_items(provider, batch_prompt(batch), ProductAttributes,
                                         list(batch.ref), context=context))
            calls += 1
            return True
        except Exception as err:  # noqa: BLE001 - quota, overload, auth, network: all the same
            failure = err
            return False

    for start in range(0, len(todo), RUN_BATCH_SIZE):
        batch = todo.iloc[start:start + RUN_BATCH_SIZE]
        if call(batch):
            attempted |= set(batch.ref)
    for ref in [r for r in todo.ref if r in attempted and r not in results]:
        if call(todo[todo.ref == ref]):
            retried.add(ref)
    if failure is not None:
        # Type and message only: provider errors carry no key, and the key is never printed.
        warning(f"LLM unavailable ({type(failure).__name__}: {str(failure)[:150]}); "
                f"unfinished products marked pending")
    model = getattr(provider, "model", "")
    rows = []
    for r in todo.itertuples():
        if r.ref in results:
            status = "ok_after_retry" if r.ref in retried else "ok"
        elif r.ref in retried:
            status = "invalid_or_missing"   # failed in its batch and again alone
        else:
            status = "pending"              # not reached, or its retry wasn't reached
        out = {"roaster": r.roaster, "product_id": r.product_id, "ref": r.ref, "status": status}
        attrs = results.get(r.ref)
        for field in ALLOWED:
            fv = getattr(attrs, field) if attrs else None
            out |= {field: fv.value if fv else "", f"{field}_confidence": fv.confidence if fv else "",
                    f"{field}_evidence": fv.evidence if fv else ""}
        out |= {"model": model if status != "pending" else "", "prompt_version": PROMPT_VERSION,
                "batch_size": RUN_BATCH_SIZE}
        rows.append(out)
    return pd.DataFrame(rows), todo


def finish(raw: pd.DataFrame, todo: pd.DataFrame, month: str) -> pd.DataFrame:
    """Phase 3's post-processing rules on the finished rows; pending rows stay blank
    (the rules would turn a not-yet-labelled product into "failed: all unknown")."""
    done = raw[raw.status != "pending"]
    if len(done):
        done = postprocess(done, todo)
    out = pd.concat([done, raw[raw.status == "pending"]], ignore_index=True)
    return out.assign(attempted_month=month)


def update(month: str, month_rows: pd.DataFrame, desc: dict, make_provider,
           max_calls: int = MAX_CALLS) -> dict[str, pd.DataFrame]:
    """New inputs, (re)labelled attributes and the review list, as tables to write."""
    inputs, attrs = _read(INPUTS), _read(ATTRIBUTES)
    known = _keys(_read(PHASE3)) | _keys(inputs)
    inputs = pd.concat([inputs, new_inputs(month_rows, known, month)], ignore_index=True)
    # Older files may still carry text columns: never write them back.
    inputs = inputs.drop(columns=["card_text", "description"], errors="ignore")
    todo = to_do(inputs, attrs)
    if len(todo):
        todo = with_description(todo, desc)
        raw, todo_full = extract(todo, make_provider, max_calls)
        fresh = finish(raw, todo_full, month)
        keep = attrs[[k not in _keys(fresh) for k in zip(attrs.roaster, attrs.product_id)]] \
            if len(attrs) else attrs
        attrs = pd.concat([keep, fresh], ignore_index=True)
        review = review_rows(fresh[fresh.status != "pending"], todo_full) \
            if (fresh.status != "pending").any() else pd.DataFrame()
    else:
        review = pd.DataFrame()
    old_review = _read(REVIEW)
    if len(review):
        review = review.assign(month=month)
    review = pd.concat([old_review, review], ignore_index=True)
    return {"inputs": inputs, "attributes": attrs, "review": review}


def gemini():
    """The tracker's provider. GEMINI_API_KEY comes from the environment (GitHub
    Secrets in Actions, .env locally) - never from code."""
    from src.llm.gemini import GeminiProvider
    return GeminiProvider()
