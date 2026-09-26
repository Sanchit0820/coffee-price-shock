"""Rule-based guess at whether a product is roasted coffee (beans or ground).

Returns True (coffee), False (clearly not coffee) or None (ambiguous: left for
Phase 3). Nothing is deleted; this only fills the is_coffee_guess column.

Only the PRODUCT title and product type are checked, never the variant title:
coffee variants are often named after brew methods ("Aeropress", "French
Press", "Channi (Tea Strainer)"), which would otherwise look like equipment/tea.
"""
import re

# STRONG: these always mean "not a bag of coffee", whatever the product type.
_STRONG = [
    # equipment and merchandise
    r"dripper", r"grinder", r"kettle", r"filter papers?", r"scale", r"mug", r"cups?",
    r"tumbler", r"bottle", r"server", r"frother", r"v60", r"chemex", r"moka pot",
    r"brewer", r"equipment", r"merch(andise)?", r"t-?shirt", r"tote", r"sticker", r"apron",
    # non-bean coffee formats
    r"drip bags?", r"coffee bags?", r"cold brew bags?", r"dip n sip", r"easy pour",
    r"pour ?over bags?", r"pourtable", r"concentrate", r"cans?", r"capsules?", r"pods?",
    r"instant", r"chicory", r"cascara",
    # bundles, subscriptions, services
    r"subscriptions?", r"subscribe", r"samplers?", r"sample pack", r"bundle", r"combo",
    r"kit", r"box of", r"gift ?box", r"hamper", r"gift card", r"e-gift",
    r"\d+\s*x\s*coffees", r"workshop", r"course", r"class", r"event", r"ticket",
]
# WEAK: also used as tasting notes in coffee names ("Dark Chocolate Espresso",
# "Milk Chocolate & Cherry"). A coffee product type overrides them; without
# one the row is left ambiguous (None) rather than guessed.
_WEAK = [r"tea", r"matcha", r"chocolate", r"cacao", r"oat", r"milk", r"syrup",
         r"french press", r"aeropress"]


def _words(patterns: list[str]) -> re.Pattern:
    return re.compile(r"\b(" + "|".join(patterns) + r")\b", re.IGNORECASE)


_STRONG_RE, _WEAK_RE = _words(_STRONG), _words(_WEAK)
# Product types (set by the shop owner) that mean "roasted coffee".
_COFFEE_TYPE_RE = re.compile(r"\bcoffee\b|\bbeans?\b|\broast", re.IGNORECASE)


def is_coffee_guess(product_title: str, product_type: str, has_gram_size: bool) -> bool | None:
    """True / False / None (ambiguous). See module docstring for the rules."""
    text = f"{product_title} {product_type}"
    if _STRONG_RE.search(text):
        return False
    coffee_type = bool(_COFFEE_TYPE_RE.search(product_type or ""))
    if coffee_type:
        return True
    if _WEAK_RE.search(text):
        # "Oat Milk" or "Dark Chocolate Espresso"? Can't tell without a type.
        return None
    # No keyword and no helpful type: a weight in grams is decent evidence of a
    # bag of coffee (tea/chicory with grams were caught by keywords above).
    if has_gram_size:
        return True
    return None
