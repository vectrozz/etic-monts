"""Auto-detect emoji for a product based on its name (with family fallback).

Used as a default when a producteur creates a product without picking one
manually. Order matters in PRODUCT_EMOJI: more specific keywords first.
"""
from __future__ import annotations

import unicodedata


# Each entry: (substring to look for in lower-cased ASCII'd name, emoji).
PRODUCT_EMOJI: list[tuple[str, str]] = [
    # ---- Fruits — specific ----
    ("fraise",       "🍓"),
    ("framboise",    "🍇"),
    ("mure",         "🫐"),
    ("myrtille",     "🫐"),
    ("cassis",       "🫐"),
    ("groseille",    "🍒"),
    ("cerise",       "🍒"),
    ("pomme de terre", "🥔"),
    ("patate douce",   "🍠"),
    ("patate",       "🥔"),
    ("pomme",        "🍎"),
    ("poire",        "🍐"),
    ("peche",        "🍑"),
    ("nectarine",    "🍑"),
    ("abricot",      "🍑"),
    ("prune",        "🍑"),
    ("mirabelle",    "🍑"),
    ("raisin",       "🍇"),
    ("kiwi",         "🥝"),
    ("citron",       "🍋"),
    ("orange",       "🍊"),
    ("clementine",   "🍊"),
    ("mandarine",    "🍊"),
    ("pamplemousse", "🍊"),
    ("melon",        "🍈"),
    ("pasteque",     "🍉"),
    ("ananas",       "🍍"),
    ("banane",       "🍌"),
    ("mangue",       "🥭"),
    ("figue",        "🍇"),
    ("noisette",     "🌰"),
    ("noix",         "🌰"),
    ("chataigne",    "🌰"),
    ("amande",       "🌰"),

    # ---- Légumes-fruits ----
    ("tomate",       "🍅"),
    ("tomate cerise","🍅"),
    ("aubergine",    "🍆"),
    ("courgette",    "🥒"),
    ("concombre",    "🥒"),
    ("cornichon",    "🥒"),
    ("poivron",      "🫑"),
    ("piment",       "🌶️"),
    ("courge",       "🎃"),
    ("potiron",      "🎃"),
    ("citrouille",   "🎃"),
    ("butternut",    "🎃"),
    ("potimarron",   "🎃"),
    ("mais",         "🌽"),

    # ---- Légumes-racines ----
    ("carotte",      "🥕"),
    ("betterave",    "🥕"),
    ("radis",        "🥕"),
    ("navet",        "🥕"),
    ("panais",       "🥕"),
    ("salsifis",     "🥕"),
    ("celeri-rave",  "🥕"),
    ("rutabaga",     "🥕"),
    ("topinambour",  "🥕"),

    # ---- Légumes-feuilles / choux ----
    ("brocoli",      "🥦"),
    ("chou-fleur",   "🥦"),
    ("chou rouge",   "🥬"),
    ("chou rave",    "🥬"),
    ("chou de bruxelles", "🥬"),
    ("chou",         "🥬"),
    ("salade",       "🥬"),
    ("laitue",       "🥬"),
    ("mache",        "🥬"),
    ("epinard",      "🥬"),
    ("blette",       "🥬"),
    ("roquette",     "🥬"),
    ("pissenlit",    "🥬"),
    ("kale",         "🥬"),
    ("endive",       "🥬"),
    ("cresson",      "🥬"),

    # ---- Légumes-tiges / bulbes ----
    ("asperge",      "🌱"),
    ("fenouil",      "🌱"),
    ("celeri",       "🌱"),
    ("rhubarbe",     "🌱"),
    ("oignon",       "🧅"),
    ("ail",          "🧄"),
    ("echalote",     "🧅"),
    ("poireau",      "🧅"),
    ("ciboule",      "🧅"),

    # ---- Légumineuses ----
    ("haricot vert", "🫛"),
    ("haricot",      "🫘"),
    ("petit pois",   "🫛"),
    ("pois ",        "🫛"),
    ("feve",         "🫘"),
    ("lentille",     "🫘"),
    ("pois chiche",  "🫘"),

    # ---- Aromatiques ----
    ("basilic",      "🌿"),
    ("persil",       "🌿"),
    ("menthe",       "🌿"),
    ("thym",         "🌿"),
    ("romarin",      "🌿"),
    ("ciboulette",   "🌿"),
    ("coriandre",    "🌿"),
    ("estragon",     "🌿"),
    ("aneth",        "🌿"),
    ("sauge",        "🌿"),
    ("origan",       "🌿"),
    ("laurier",      "🌿"),
    ("aromatique",   "🌿"),

    # ---- Champignons ----
    ("champignon",   "🍄"),
    ("pleurote",     "🍄"),
    ("shiitake",     "🍄"),

    # ---- Œufs / produits transformés ----
    ("oeuf",         "🥚"),
    ("miel",         "🍯"),
    ("confiture",    "🍯"),
    ("jus",          "🧃"),
    ("sirop",        "🧃"),
    ("vin",          "🍷"),
    ("biere",        "🍺"),
    ("pain",         "🍞"),
    ("farine",       "🌾"),
    ("ble",          "🌾"),
    ("orge",         "🌾"),
    ("avoine",       "🌾"),
    ("seigle",       "🌾"),
    ("riz",          "🌾"),
]


# Family fallbacks (substring → emoji). Tried after PRODUCT_EMOJI fails.
FAMILY_FALLBACKS: list[tuple[str, str]] = [
    ("fruit",        "🍇"),
    ("legume",       "🥬"),
    ("aromat",       "🌿"),
    ("graine",       "🌾"),
    ("cereale",      "🌾"),
    ("baie",         "🫐"),
]


def _normalise(s: str) -> str:
    """Lowercase + strip accents — so 'Pêche' → 'peche'."""
    nfkd = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def detect_emoji(name: str, category: str | None = None) -> str:
    """Best-effort emoji for (name [, category])."""
    haystack = _normalise(name or "")
    cat_norm = _normalise(category or "")

    for needle, emoji in PRODUCT_EMOJI:
        if needle in haystack:
            return emoji
    for needle, emoji in FAMILY_FALLBACKS:
        if needle in haystack or needle in cat_norm:
            return emoji
    return "🌿"
