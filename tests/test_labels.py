"""Hand-label sampling and reading."""
import pandas as pd

from src import labels


def test_allocate_floor_and_total():
    sizes = pd.Series({"A": 87, "B": 10, "C": 16, "D": 3})
    q = labels.allocate(sizes, total=30, floor=5)
    assert sum(q.values()) == 30
    assert q["D"] == 3                      # can't take more than exist
    assert q["B"] >= 5 and q["C"] >= 5
    assert q["A"] > q["C"] > q["B"] - 1     # the rest goes in proportion to size


def test_allocate_real_shape_sums_to_100():
    sizes = pd.Series({"Araku": 16, "Black Baza": 45, "Bloom": 52, "Blue Tokai": 87,
                       "Corridor Seven": 78, "Devans": 62, "Dope Coffee": 25, "Grey Soul": 63,
                       "Kapi Kottai": 36, "Subko": 62, "Third Wave Coffee": 10})
    q = labels.allocate(sizes)
    assert sum(q.values()) == 100 and min(q.values()) >= 5


def test_sample_roaster_takes_ambiguous_first():
    g = pd.DataFrame({"is_coffee_guess_p2": ["", "", "", "True", "True", "True", "True", "False"],
                      "has_description": [False, True, False, True, True, False, False, False]})
    s = labels.sample_roaster(g, 4, seed=1)
    assert len(s) == 4
    assert (s.is_coffee_guess_p2 == "").sum() == 2   # half the quota


def test_read_labels_skips_note_lines(tmp_path, monkeypatch):
    f = tmp_path / "hand_labels.csv"
    f.write_text('# note one\n# note two, with "quotes"\nlabel_id,product_title\n1,Lot #08\n',
                 encoding="utf-8-sig")
    monkeypatch.setattr(labels, "LABELS", f)
    df = labels.read_labels()
    assert df.columns.tolist() == ["label_id", "product_title"]
    assert df.product_title.iloc[0] == "Lot #08"   # '#' inside a value is kept
