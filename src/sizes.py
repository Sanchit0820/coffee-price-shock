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
