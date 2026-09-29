"""Candidate generation, link resolution and stable product keys (no LLM)."""
import pandas as pd

from src.matching import (MatchDecision, break_sides, candidate_pairs, norm_title,
                          product_keys, resolve)


def products(rows):
    return pd.DataFrame(rows, columns=["product_id", "product_title"])


def test_norm_title_ignores_case_and_punctuation():
    assert norm_title("Monsooned Malabar - Arabica AA") == norm_title("MONSOONED MALABAR ARABICA AA")


def test_exact_titles_resolved_by_rule_and_removed_from_other_pairs():
    before = products([("1", "Organic Arabica Coffee"), ("2", "Robusta Kaapi Royale")])
    after = products([("11", "ORGANIC ARABICA COFFEE"), ("12", "ROBUSTA KAAPI ROYALE BLEND")])
    pairs = candidate_pairs(before, after)
    exact = [p for p in pairs if p["method"] == "exact_title"]
    assert exact == [{"before_id": "1", "after_id": "11", "similarity": 1.0, "method": "exact_title"}]
    llm = [p for p in pairs if p["method"] == "llm"]
    assert [(p["before_id"], p["after_id"]) for p in llm] == [("2", "12")]   # 11 is taken


def test_top_k_and_threshold():
    before = products([("1", "Ampthill Downs Lot 08")])
    after = products([(str(i), f"Ampthill Downs Lot 0{i}") for i in range(1, 6)] + [("99", "Zzz")])
    pairs = candidate_pairs(before, after)
    assert len(pairs) == 3                                   # top 3 only
    assert "99" not in {p["after_id"] for p in pairs}        # below similarity threshold


def test_break_sides_uses_previous_observed_quarter_and_drops_shared_ids():
    rows = pd.DataFrame({"quarter": ["2024Q1", "2024Q1", "2024Q3", "2024Q3"],
                         "product_id": ["1", "2", "2", "3"],
                         "product_title": ["A", "B", "B", "C"]})
    before_q, before, after = break_sides(rows, "2024Q3")      # no 2024Q2 data
    assert before_q == "2024Q1"
    assert before.product_id.tolist() == ["1"] and after.product_id.tolist() == ["3"]


def pair(ref, b, a, method="llm"):
    return {"pair_ref": ref, "roaster": "R", "before_id": b, "after_id": a, "method": method}


def test_resolve_statuses_and_conflicts():
    pairs = pd.DataFrame([pair("p1", "1", "11", "exact_title"), pair("p2", "2", "12"),
                          pair("p3", "3", "13"), pair("p4", "4", "14"),
                          pair("p5", "5", "15"), pair("p6", "5", "16"), pair("p7", "6", "17")])
    d = {"p2": MatchDecision(ref="p2", same_product="yes", confidence="high", reason="same estate"),
         "p3": MatchDecision(ref="p3", same_product="no", confidence="medium", reason="other lot"),
         "p4": MatchDecision(ref="p4", same_product="yes", confidence="low", reason="unsure"),
         "p5": MatchDecision(ref="p5", same_product="yes", confidence="high", reason="same name"),
         "p6": MatchDecision(ref="p6", same_product="yes", confidence="medium", reason="also similar")}
    resolved = resolve(pairs, d)
    status = dict(zip(resolved.pair_ref, resolved.status))
    assert status == {"p1": "linked", "p2": "linked", "p3": "rejected", "p4": "review",
                      "p5": "conflict", "p6": "conflict", "p7": "no_decision"}


def test_human_decisions_override_model_and_conflicts(tmp_path):
    from src.matching import apply_human, load_human_decisions
    review = tmp_path / "match_review.csv"
    pd.DataFrame({"roaster": ["R", "R", "R", "R"], "before_id": ["1", "2", "5", "9"],
                  "after_id": ["11", "11", "15", "19"],
                  "your_decision": ["yes", "Yes ", "no", ""]}).to_csv(review, index=False)
    decisions = load_human_decisions(review)
    assert decisions == {("R", "1", "11"): "yes", ("R", "2", "11"): "yes", ("R", "5", "15"): "no"}
    p = pd.DataFrame({"roaster": ["R"] * 4, "before_id": ["1", "2", "5", "9"],
                      "after_id": ["11", "11", "15", "19"],
                      "status": ["conflict", "conflict", "linked", "rejected"]})
    out = apply_human(p, decisions)
    assert out.status.tolist() == ["linked_human", "linked_human", "rejected_human", "rejected"]


def test_duplicate_old_listings_share_one_key():
    prods = pd.DataFrame({"roaster": ["Devans"] * 3, "product_id": ["1", "2", "11"],
                          "first_quarter": ["2023Q1", "2023Q2", "2024Q2"]})
    links = pd.DataFrame({"roaster": ["Devans"] * 2, "before_id": ["1", "2"], "after_id": ["11", "11"]})
    keys = product_keys(prods, links)
    assert keys[("Devans", "1")] == keys[("Devans", "2")] == keys[("Devans", "11")] == "devans:1"


def test_product_keys_follow_chains_to_the_earliest_product():
    prods = pd.DataFrame({"roaster": ["Grey Soul"] * 4, "product_id": ["1", "2", "3", "9"],
                          "first_quarter": ["2023Q1", "2023Q2", "2024Q1", "2023Q1"]})
    links = pd.DataFrame({"roaster": ["Grey Soul", "Grey Soul"], "before_id": ["1", "2"],
                          "after_id": ["2", "3"]})
    keys = product_keys(prods, links)
    assert keys[("Grey Soul", "3")] == keys[("Grey Soul", "1")] == "grey-soul:1"
    assert keys[("Grey Soul", "9")] == "grey-soul:9"          # unlinked keeps its own id
