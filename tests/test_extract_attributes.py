"""Attribute schema validation and label scoring (no LLM)."""
import pandas as pd
import pytest
from pydantic import ValidationError

from src.evaluate_labels import agreement, field_scores, norm_free
from src.extract_attributes import ProductAttributes, product_text

TEXT = ("Title: Attikan Estate - Washed\nVariants: 250g / Whole Beans\n"
        "Description: A washed Arabica from Chikmagalur, medium roast.")
UNKNOWN = {"value": "unknown", "confidence": "high", "evidence": ""}


def item(**overrides):
    base = {f: dict(UNKNOWN) for f in ["is_coffee", "origin_country", "region", "estate",
                                       "species", "origin_type", "process", "roast_level",
                                       "decaf", "flavoured_infused"]}
    base.update(overrides)
    return {"ref": "r1", **base}


def validate(raw):
    return ProductAttributes.model_validate(raw, context={"inputs": {"r1": TEXT}})


def test_valid_item_with_verbatim_evidence():
    a = validate(item(process={"value": "Washed", "confidence": "high", "evidence": "a washed arabica"},
                      region={"value": "Chikmagalur", "confidence": "high", "evidence": "from Chikmagalur"}))
    assert a.process.value == "washed"          # dropdown values lower-cased
    assert a.region.value == "Chikmagalur"      # free text kept as written


def test_invented_evidence_fails():
    with pytest.raises(ValidationError, match="not in the product text"):
        validate(item(region={"value": "Coorg", "confidence": "high", "evidence": "grown in Coorg"}))


def test_value_without_evidence_fails():
    with pytest.raises(ValidationError, match="no evidence"):
        validate(item(species={"value": "arabica", "confidence": "high", "evidence": ""}))


def test_disallowed_value_fails():
    with pytest.raises(ValidationError, match="not in"):
        validate(item(process={"value": "fermented", "confidence": "low", "evidence": "washed"}))


def test_evidence_for_unknown_is_dropped():
    a = validate(item(decaf={"value": "unknown", "confidence": "high", "evidence": "medium roast"}))
    assert a.decaf.evidence == ""


def test_evidence_check_ignores_case_whitespace_and_curly_quotes():
    text = "Title: Ell’sworth   Red Honey"   # curly apostrophe, extra spaces
    a = ProductAttributes.model_validate(
        item(process={"value": "honey", "confidence": "high", "evidence": "Ell'sworth red HONEY"}),
        context={"inputs": {"r1": text}})
    assert a.process.value == "honey"


def test_product_text_skips_empty_fields():
    row = pd.Series({"product_title": "Dhak Blend", "other_titles": "", "product_type": "nan",
                     "variant_titles": "250g", "card_text": "", "description": ""})
    assert product_text(row) == "Title: Dhak Blend\nVariants: 250g"


# ---------- post-processing rules ----------

def attrs_frame():
    from src.labels import ALLOWED
    rows = []
    for pid, status, flav, flav_ev, decaf, decaf_ev, estate, otype in [
        ("1", "ok", "no", "100% Arabica", "no", "Arabica", "unknown", "unknown"),
        ("2", "ok", "no", "No added flavours, ever", "no", "Regular caffeinated coffee", "Attikan Estate", "unknown"),
        ("3", "invalid_or_missing", "", "", "", "", "", ""),
        ("4", "ok", "yes", "aged in rum casks", "unknown", "", "unknown", "single_origin"),
    ]:
        row = {"roaster": "R", "product_id": pid, "status": status}
        for f in ALLOWED:
            row |= {f: "unknown", f"{f}_confidence": "high", f"{f}_evidence": ""}
        row |= {"flavoured_infused": flav, "flavoured_infused_evidence": flav_ev,
                "decaf": decaf, "decaf_evidence": decaf_ev, "estate": estate, "origin_type": otype}
        rows.append(row)
    products = pd.DataFrame({"roaster": ["R"] * 4, "product_id": ["1", "2", "3", "4"],
                             "product_title": ["House Blend", "Attikan Estate", "Mystery", "Cask Lot"],
                             "text": ["Title: House Blend", "Title: Attikan Estate", "Title: Mystery",
                                      "Title: Cask Lot\nDescription: a single origin lot"]})
    return pd.DataFrame(rows), products


def test_no_without_real_evidence_becomes_unknown():
    from src.extract_attributes import postprocess
    df, products = attrs_frame()
    out = postprocess(df, products).set_index("product_id")
    assert out.loc["1", "flavoured_infused"] == "unknown" and out.loc["1", "decaf"] == "unknown"
    assert out.loc["1", "flavoured_infused_model"] == "no"          # model's answer kept
    assert out.loc["2", "flavoured_infused"] == "no" and out.loc["2", "decaf"] == "no"   # real evidence
    assert out.loc["4", "flavoured_infused"] == "yes"


def test_failed_products_kept_all_unknown():
    from src.extract_attributes import postprocess
    from src.labels import ALLOWED
    df, products = attrs_frame()
    row = postprocess(df, products).set_index("product_id").loc["3"]
    assert all(row[f] == "unknown" for f in ALLOWED)
    assert "failed validation" in row.rules_applied


def test_origin_type_analysis_rules_and_idempotence():
    from src.extract_attributes import postprocess
    df, products = attrs_frame()
    once = postprocess(df, products)
    out = once.set_index("product_id")
    assert out.loc["1", "origin_type_analysis"] == "blend"           # "Blend" in title
    assert out.loc["2", "origin_type_analysis"] == "single_origin"   # named estate
    assert out.loc["4", "origin_type_analysis"] == "single_origin"   # "single origin" in text
    assert out.loc["1", "origin_type"] == "unknown"                  # model value untouched
    twice = postprocess(once, products)
    assert twice.to_csv(index=False) == once.to_csv(index=False)


# ---------- scoring ----------

def test_region_containment_match():
    from src.evaluate_labels import same
    assert same("region", "Gandha, Andhra Pradesh", "Gandha")
    assert same("region", "Gandha", "Gandha, Andhra Pradesh")
    assert not same("region", "unknown", "Gandha")          # unknown is never "contained"
    assert same("region", "unknown", "unknown")
    assert not same("region", "Coorgshire", "Coorg")         # whole words only
    assert not same("estate", "Salawara Estate Lot 2", "Salawara")   # only region uses containment


def test_norm_free_ignores_filler_words():
    assert norm_free("Salawara Estate") == norm_free("salawara") == "salawara"


def frame(values_by_field, status="ok"):
    rows = []
    for i, values in enumerate(zip(*values_by_field.values())):
        row = {"roaster": "R", "product_id": str(i), "status": status}
        row.update(dict(zip(values_by_field.keys(), values)))
        rows.append(row)
    fields = ["is_coffee", "origin_country", "region", "estate", "species", "origin_type",
              "process", "roast_level", "decaf", "flavoured_infused"]
    df = pd.DataFrame(rows)
    for f in fields:
        if f not in df:
            df[f] = "unknown"
    return df


def test_field_scores_accuracy_found_invented():
    gold = frame({"region": ["Chikmagalur", "unknown", "unknown", "Coorg"]})
    pred = frame({"region": ["chikmagalur", "Coorg", "unknown", "unknown"]})
    s = field_scores(pred, gold).set_index("field").loc["region"]
    assert s.accuracy == 0.5          # rows 0 and 2 right
    assert s.found == 0.5             # of 2 known labels, 1 found
    assert s.invented == 0.5          # of 2 unknown labels, 1 given a value anyway


def test_agreement_only_counts_products_valid_in_both():
    a = frame({"process": ["washed", "natural", "honey"]})
    b = frame({"process": ["washed", "washed", "honey"]})
    b.loc[2, "status"] = "invalid_or_missing"
    s = agreement(a, b).set_index("field").loc["process"]
    assert s.n == 2 and s.agreement == 0.5
