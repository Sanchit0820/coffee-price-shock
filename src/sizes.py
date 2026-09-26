"""Parse pack sizes like "250g", "1 Kilogram" or "2 x 500 gms" into grams."""
import re
from dataclasses import dataclass

# Longest unit spellings first so "kilogram" isn't cut short to "kilo" or "kg",
# and "grams" isn't read as "g" followed by junk.
_UNITS = r"kilograms?|kilos?|kgs?|grams?|gms?|gm|g"
_SIZE = re.compile(
    r"(?<![\d.])"                       # not in the middle of a longer number
    r"(?:(\d+)\s*[x×]\s*)?"             # optional multipack count: "2 x "
    r"(\d+(?:\.\d+)?)\s*"               # the quantity: "250", "1", "1.5"
    rf"({_UNITS})\b",                   # the unit, as a whole word
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Size:
    grams: float        # total grams (count x per-pack size for multipacks)
    multipack: bool     # True for "2 x 500 gms"


_PACK_OF = re.compile(r"\bpack\s+of\s+(\d+)\b", re.IGNORECASE)


def pack_count(text: str | None) -> int | None:
    """N from "(Pack of N)" in a product title, e.g. "SKIA Coffee (Pack of 2)" -> 2."""
    m = _PACK_OF.search(text or "")
    return int(m.group(1)) if m else None


def apply_pack_count(size: Size, count: int | None) -> Size:
    """Per-bag size x "Pack of N" -> total, flagged multipack.

    Skipped if the size is already a multipack ("2 x 500 gms"), so a pack
    count is never applied twice.
    """
    if not count or count < 2 or size.multipack:
        return size
    return Size(grams=size.grams * count, multipack=True)


def parse_size_grams(text: str | None) -> Size | None:
    """First pack size in `text`, converted to grams; None if there isn't one.

    Millilitres and other units are deliberately not parsed (not a coffee weight).
    """
    if not text:
        return None
    m = _SIZE.search(text)
    if not m:
        return None
    count, qty, unit = m.groups()
    grams = float(qty) * (1000 if unit.lower().startswith("k") else 1)
    if count:
        return Size(grams=grams * int(count), multipack=True)
    return Size(grams=grams, multipack=False)
