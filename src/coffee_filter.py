"""Rule-based labels for products: is it coffee, and is it a bundle?

is_coffee_guess -> True (coffee), False (genuinely not coffee: equipment,
                   other drinks, drip bags, services) or None (ambiguous,
                   left for Phase 3).
is_bundle       -> True for several coffees sold together (samplers, trios,
                   "5-in-1" packs, gift hampers). Bundles ARE coffee, so they
                   aren't marked non-coffee; they're excluded from
                   price-per-gram work instead, because their size is either
                   per bag or a total across different coffees. A non-coffee
                   item is never a bundle (the caller enforces this), so a
                   "Subscribe - 6 Coffees" plan stays plain non-coffee.

Only the PRODUCT title and product type are checked, never the variant title:
coffee variants are often named after brew methods ("Aeropress", "French
Press", "Channi (Tea Strainer)"), which would otherwise look like equipment/tea.
"""
import re

# STRONG: genuinely not a bag of coffee, whatever the product type.
_STRONG = [
    # equipment and merchandise
    r"dripper", r"grinder", r"kettle", r"filter papers?", r"scale", r"mug", r"cups?",
    r"tumbler", r"bottle", r"server", r"frother", r"v60", r"chemex", r"moka pot",
    r"brewer", r"equipment", r"merch(andise)?", r"t-?shirt", r"tote", r"sticker", r"apron",
    # non-bean coffee formats
    r"drip bags?", r"coffee bags?", r"cold brew bags?", r"dip n sip", r"easy pour",
    r"pour ?over bags?", r"pourtable", r"concentrate", r"cans?", r"capsules?", r"pods?",
    r"instant", r"chicory", r"cascara", r"flour",
    # pantry items some roasters sell (not "honey": honey-process coffees are common)
    r"cardamom", r"jaggery", r"pepper",
    # services and kits (kits are mostly equipment with a little coffee)
    r"subscriptions?", r"subscribe", r"kit", r"gift card", r"e-gift",
    r"workshop", r"course", r"class", r"event", r"ticket",
]
# WEAK: also used as tasting notes in coffee names ("Dark Chocolate Espresso",
# "Milk Chocolate & Cherry"). A coffee product type overrides them; without
# one the row is left ambiguous (None) rather than guessed.
_WEAK = [r"tea", r"matcha", r"chocolate", r"cacao", r"oat", r"milk", r"syrup",
         r"french press", r"aeropress"]
# BUNDLE: several coffees sold as one product.
#   "pack" but NOT "pack of N": "SKIA Coffee (Pack of 2)" is one coffee in two
#   bags (a multipack, sized 2 x 200 g), while "Coffees (Pack of 3)" is still
#   caught by the plural "coffees".
_BUNDLE = [
    r"samplers?", r"sample packs?", r"bundles?", r"combo", r"gift ?box", r"hamper",
    r"coffees", r"trio", r"\d+\s*-\s*in\s*-\s*1", r"pack(?!\s+of\s+\d)",
]


def _words(patterns: list[str]) -> re.Pattern:
    return re.compile(r"\b(" + "|".join(patterns) + r")\b", re.IGNORECASE)


_STRONG_RE, _WEAK_RE, _BUNDLE_RE = _words(_STRONG), _words(_WEAK), _words(_BUNDLE)
# Product types (set by the shop owner) that mean "roasted coffee".
_COFFEE_TYPE_RE = re.compile(r"\bcoffee\b|\bbeans?\b|\broast", re.IGNORECASE)


def is_bundle(product_title: str) -> bool:
    """Title only: some shops use the product type loosely (Black Baza types
    single pantry items like cardamom and jaggery as "Bundles")."""
    return bool(_BUNDLE_RE.search(product_title or ""))


def is_coffee_guess(product_title: str, product_type: str, has_gram_size: bool,
                    bundle: bool = False) -> bool | None:
    """True / False / None (ambiguous). See module docstring for the rules."""
    text = f"{product_title} {product_type}"
    if _STRONG_RE.search(text):
        return False
    if _COFFEE_TYPE_RE.search(product_type or "") or bundle:
        return True   # a coffee type, or a bundle of coffees
    if _WEAK_RE.search(text):
        # "Oat Milk" or "Dark Chocolate Espresso"? Can't tell without a type.
        return None
    # No keyword and no helpful type: a weight in grams is decent evidence of a
    # bag of coffee (tea/chicory with grams were caught by keywords above).
    if has_gram_size:
        return True
    return None
