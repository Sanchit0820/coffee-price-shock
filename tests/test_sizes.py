"""Size parser: every spelling seen in Phase 1, plus edge cases."""
import pytest

from src.sizes import Size, apply_pack_count, pack_count, parse_size_grams


@pytest.mark.parametrize("text, grams", [
    ("250g", 250),
    ("250 g", 250),
    ("250 gm", 250),
    ("250gms", 250),
    ("250 GMS / Whole Bean", 250),       # Grey Soul
    ("250 grams", 250),
    ("Whole Beans / 250 gms", 250),      # Araku
    ("1kg", 1000),
    ("DRIP MACHINE / 1kg", 1000),        # Corridor Seven (missed by the Phase 1 pattern)
    ("1 kg / Whole Beans", 1000),        # Kapi Kottai
    ("1 Kilo", 1000),
    ("1 Kilogram / Whole Bean", 1000),   # Grey Soul
    ("1.5 kg", 1500),
    ("100 g (each)", 100),               # Kapi Kottai samplers
    ("84g", 84),                         # Subko pourover box
])
def test_single_pack_sizes(text, grams):
    assert parse_size_grams(text) == Size(grams=grams, multipack=False)


def test_multipack_is_total_weight_and_flagged():
    assert parse_size_grams("Dark / 2 x 500 gms") == Size(grams=1000, multipack=True)


@pytest.mark.parametrize("text", [
    None, "", "Whole Beans / Tin", "Filter Coffee Concentrate - 250ml",
    "12 months / Once a month / 1", "Coarse Grind",
])
def test_no_size(text):
    assert parse_size_grams(text) is None


@pytest.mark.parametrize("title, n", [
    ("SKIA Coffee (Pack of 2)", 2),
    ("Central Washing Station Coffees (Pack of 5)", 5),
    ("pack of 3", 3),
    ("Monsoon Malabar AA", None),
    ("Sampler Pack", None),
    (None, None),
])
def test_pack_count(title, n):
    assert pack_count(title) == n


def test_apply_pack_count():
    assert apply_pack_count(Size(200, False), 2) == Size(400, True)       # SKIA: 2 x 200 g
    assert apply_pack_count(Size(200, False), None) == Size(200, False)
    assert apply_pack_count(Size(200, False), 1) == Size(200, False)
    # Already a multipack ("2 x 500 gms"): never multiplied twice.
    assert apply_pack_count(Size(1000, True), 2) == Size(1000, True)


def test_unit_must_be_a_whole_word():
    # "250 grind" is not 250 g
    assert parse_size_grams("250 grind") is None
