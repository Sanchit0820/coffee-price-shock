"""Live tracker: network and LLM are faked."""
import pandas as pd
import pytest

from src import http_client
from src.llm.base import RetryableError
from src.tracker import analysis, attributes, run, snapshot


def roaster(name, enabled=True):
    return {"roaster": name, "tier": "core", "live_url": f"https://{name}.test/collections/all",
            "enabled": enabled}


def month_rows(month, roaster_name, products):
    """products: [(product_id, title, grams, price)]"""
    rows = [{"month": month, "fetched_at": f"{month}-01", "roaster": roaster_name, "tier": "core",
             "product_id": pid, "product_title": t, "product_type": "", "variant_id": f"{pid}-{g}",
             "variant_title": f"{g}g", "sku": "", "price_inr": str(p), "compare_at_price_inr": "",
             "size_grams": str(g), "multipack": "False", "size_source": "variant_title",
             "is_coffee_guess": "True", "is_bundle": "False", "sale_suspected": "False",
             "source_url": ""} for pid, t, g, p in products]
    return pd.DataFrame(rows, columns=snapshot.COLUMNS)


# ---------- cache ----------

def test_snapshot_cache_key_keeps_each_month(tmp_path, monkeypatch):
    monkeypatch.setattr(http_client.config, "RAW_DIR", tmp_path)
    url = "https://shop.test/collections/all/products.json?limit=250&page=1"
    plain, sep, oct_ = (http_client._cache_paths(url)[0], http_client._cache_paths(url, "2026-09")[0],
                        http_client._cache_paths(url, "2026-10")[0])
    assert len({plain, sep, oct_}) == 3            # a new month never overwrites an old one
    assert http_client._cache_paths(url, "2026-10")[0] == oct_   # same month: same file (cache hit)


# ---------- snapshot ----------

def test_snapshot_skips_robots_keeps_rows_on_error_and_never_refetches():
    old = month_rows("2026-09", "A", [("1", "Coffee", 250, 500)])
    old = pd.concat([old, month_rows("2026-10", "C", [("9", "Coffee", 250, 500)])])
    calls = []

    def fetch(r, month):
        calls.append(r["roaster"])
        if r["roaster"] == "B":
            raise ConnectionError("403 from cloud IP")
        return month_rows(month, r["roaster"], [("1", "Coffee", 250, 550)])

    robots = lambda r: (r["roaster"] != "D", "found" if r["roaster"] != "D" else "blocked")  # noqa: E731
    roasters = [roaster("A"), roaster("B"), roaster("C"), roaster("D"), roaster("E", enabled=False)]
    new, status = snapshot.take_snapshot("2026-10", old, roasters, fetch=fetch, robots=robots)
    s = status.set_index("roaster").status
    assert s.to_dict() == {"A": "fetched", "B": "error", "C": "already_fetched",
                           "D": "skipped_robots", "E": "skipped_disabled"}
    assert calls == ["A", "B"]                     # C already has 2026-10 rows; D and E not asked
    assert new.iloc[:len(old)].reset_index(drop=True).equals(old.reset_index(drop=True))
    assert len(new) == len(old) + 1                # only A's new row


def test_big_drop_is_flagged():
    old = month_rows("2026-09", "A", [(str(i), f"Coffee {i}", 250, 500) for i in range(10)])
    fetch = lambda r, m: month_rows(m, "A", [("1", "Coffee 1", 250, 500)])  # noqa: E731
    _, status = snapshot.take_snapshot("2026-10", old, [roaster("A")], fetch=fetch,
                                       robots=lambda r: (True, "found"))
    assert bool(status.big_drop.iloc[0]) and status.prev_products.iloc[0] == 10


# ---------- attributes ----------

def todo_frame(n=3):
    return pd.DataFrame({"roaster": "A", "product_id": [str(i) for i in range(n)],
                         "product_title": [f"Coffee {i}" for i in range(n)], "other_titles": "",
                         "product_type": "", "variant_titles": "250g", "card_text": "",
                         "description": "Washed arabica from Chikmagalur.", "title_changed": False})


class QuotaSpent:
    name, model = "fake", "fake-model"

    def generate_json(self, prompt):
        raise RetryableError(429, "RESOURCE_EXHAUSTED: free-tier quota used up")


class Broken(QuotaSpent):
    def generate_json(self, prompt):
        raise RuntimeError("500 internal error")


@pytest.mark.parametrize("provider", [QuotaSpent, Broken])
def test_quota_error_is_treated_like_any_api_failure(provider, monkeypatch):
    from src.llm import client
    original = client.call_with_backoff
    monkeypatch.setattr(client, "call_with_backoff",       # no real waiting in tests
                        lambda fn, *a, **k: original(fn, *a, sleep=lambda s: None, **k))
    monkeypatch.setattr(client._limiter, "wait", lambda *a, **k: None)
    raw, _ = attributes.extract(todo_frame(), provider)
    assert set(raw.status) == {"pending"} and len(raw) == 3


def test_missing_key_leaves_everything_pending():
    def no_key():
        raise RuntimeError("GEMINI_API_KEY is not set.")
    raw, _ = attributes.extract(todo_frame(), no_key)
    assert set(raw.status) == {"pending"}


def test_only_unseen_or_pending_products_are_sent():
    rows = month_rows("2026-10", "A", [("1", "Old", 250, 500), ("2", "New", 250, 500)])
    inputs = attributes.new_inputs(rows, known={("A", "1")}, month="2026-10")
    assert list(inputs.product_id) == ["2"]
    inputs = pd.concat([inputs, attributes.new_inputs(month_rows("2026-10", "A", [("3", "X", 250, 1)]),
                                                      set(), "2026-10")])
    attrs = pd.DataFrame({"roaster": ["A", "A"], "product_id": ["2", "3"], "status": ["ok", "pending"]})
    assert list(attributes.to_do(inputs, attrs).product_id) == ["3"]   # pending is retried


def test_description_is_used_but_never_stored():
    rows = month_rows("2026-10", "A", [("2", "New", 250, 500)])
    inputs = attributes.new_inputs(rows, known=set(), month="2026-10")
    assert "description" not in inputs and "card_text" not in inputs   # what gets committed
    todo = attributes.with_description(inputs, {("A", "2"): "Washed arabica from Coorg."})
    assert todo.description.iloc[0] == "Washed arabica from Coorg."    # what the model sees


# ---------- analysis ----------

def test_monthly_changes_price_pack_and_range():
    sep = month_rows("2026-09", "A", [("1", "Coffee One", 250, 500), ("2", "Coffee Two", 250, 400),
                                      ("3", "Coffee Three", 250, 600), ("4", "Gone", 250, 300)])
    oct_ = month_rows("2026-10", "A", [("1", "Coffee One", 250, 550), ("2", "Coffee Two", 250, 400),
                                       ("3", "Coffee Three", 250, 600), ("5", "New", 250, 700)])
    # Product 2: same variant ID, 250 g -> 200 g at the same price.
    oct_.loc[oct_.product_id == "2", ["size_grams", "variant_id"]] = ["200", "2-250"]
    rows = analysis.add_product_keys(analysis.coffee_rows(pd.concat([sep, oct_]), {}))
    it = analysis.items(rows)
    ch = analysis.changes(rows, it, "2026-10").set_index("change")
    assert ch.loc["price_up", "ppg_change_pct"] == pytest.approx(10.0)
    assert ch.loc["pack_size_change", "ppg_change_pct"] == pytest.approx(25.0)
    assert ch.loc["added", "product_key"] == "5" and ch.loc["dropped", "product_key"] == "4"


def test_reused_page_starts_a_new_product_key():
    rows = pd.concat([month_rows("2026-09", "A", [("1", "VIETNAMESE ROBUSTA COFFEE", 250, 300)]),
                      month_rows("2026-10", "A", [("1", "COLOMBIAN ARABICA COFFEE", 250, 600)])])
    keyed = analysis.add_product_keys(analysis.coffee_rows(rows, {}))
    assert list(keyed.product_key) == ["1", "1#2"]


# ---------- run ----------

def test_write_all_writes_nothing_if_any_output_fails(tmp_path):
    good = tmp_path / "good.csv"
    good.write_text("old\n")

    class Boom:  # not a DataFrame, Path or str: writing it fails
        pass

    with pytest.raises(Exception):
        run.write_all({good: pd.DataFrame({"new": [1]}), tmp_path / "bad.txt": Boom()})
    assert good.read_text() == "old\n"             # the good file was not replaced
    assert not list(tmp_path.glob("*.tmp"))


def test_last_run_line_replaces_only_between_markers():
    text = f"top\n{run.MARK_START}\nold line\n{run.MARK_END}\nbottom\n"
    out = run.with_last_run(text, "new line")
    assert out == f"top\n{run.MARK_START}\nnew line\n{run.MARK_END}\nbottom\n"


def test_too_many_failed_roasters_stops_the_run():
    monthly = month_rows("2026-09", "A", [("1", "Coffee", 250, 500)])
    status = pd.DataFrame({"roaster": list("ABCDE"), "status": ["error"] * 4 + ["fetched"]})
    with pytest.raises(run.TrackerError):
        run.check(monthly, monthly, status, [roaster(x) for x in "ABCDE"], pd.DataFrame())
