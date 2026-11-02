"""Parse a farm's availability list as posted in the WhatsApp group.

    "betterave rouge, choux cabus, batavia rouge 2 colis, poireaux 5 colis"
      → betterave rouge (—), choux cabus (—), batavia rouge (2 colis), poireaux (5 colis)

Pure functions, no database: the result is a preview for the coordinator.
Matching lines to catalogue products and writing stocks comes later.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Spelling → normalised unit.
_UNITS = {
    "colis": "colis", "coli": "colis",
    "cagette": "cagette", "cagettes": "cagette",
    "caisse": "caisse", "caisses": "caisse",
    "carton": "carton", "cartons": "carton",
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg",
    "g": "g", "gr": "g", "grammes": "g",
    "botte": "botte", "bottes": "botte", "bte": "botte", "btes": "botte",
    "piece": "pièce", "pieces": "pièce", "pièce": "pièce", "pièces": "pièce",
    "pc": "pièce", "pcs": "pièce", "pce": "pièce", "pces": "pièce", "p": "pièce",
    "barquette": "barquette", "barquettes": "barquette",
    "sac": "sac", "sacs": "sac",
    "plateau": "plateau", "plateaux": "plateau",
    "filet": "filet", "filets": "filet",
    "tete": "pièce", "tetes": "pièce", "tête": "pièce", "têtes": "pièce",
    "l": "litre", "litre": "litre", "litres": "litre",
}
_UNIT_RE = "|".join(sorted((re.escape(u) for u in _UNITS), key=len, reverse=True))
_QTY = r"(?P<qty>\d+(?:[.,]\d+)?)"

# "poireaux 5 colis", "salade x2", "pommes : 1,5 kg", "œufs = 30"
_TRAILING = re.compile(  # a multiplier "x" needs a space before it: "poireaux 5" keeps its x
    rf"^(?P<product>.+?)(?:\s*[:=\-–]\s*|\s+x\s*|\s*×\s*|\s+){_QTY}\s*(?P<unit>{_UNIT_RE})?\.?$", re.I)
# "5 colis de poireaux", "2x salade", "3 bottes radis"
_LEADING = re.compile(
    rf"^{_QTY}\s*(?:x|×)?\s*(?P<unit>{_UNIT_RE})?\s+(?:de\s+|d['’]\s*)?(?P<product>.+)$", re.I)

# Split items on newlines, ';', '•', and commas that are not decimal commas ("1,5").
_SPLIT = re.compile(r"[\n;•·]+|(?<!\d),|,(?!\d)")
_BULLET = re.compile(r"^[\s\-*+>–—·•]+")
_GREETING = re.compile(
    r"\b(bonjour|bonsoir|salut|coucou|merci|cette semaine|pour (mardi|vendredi|jeudi|lundi|mercredi)|"
    r"dispo(nible)?s?\s*:|voici|bonne journ[ée]e|a\+|à \+)\b", re.I)
_DELETED = re.compile(r"^(ce message a été supprimé|this message was deleted|vous avez supprimé ce message)\.?$", re.I)


@dataclass(frozen=True)
class ParsedLine:
    raw: str
    kind: str                 # "item" | "text"
    product: str | None = None
    qty: float | None = None
    unit: str | None = None

    @property
    def qty_label(self) -> str:
        if self.qty is None:
            return "—"
        q = int(self.qty) if float(self.qty).is_integer() else str(self.qty).replace(".", ",")
        return f"{q} {self.unit}" if self.unit else str(q)


def _strip_emoji(s: str) -> str:
    return "".join(ch for ch in s if unicodedata.category(ch) not in ("So", "Sk", "Cs") and ch != "️")


def _clean(s: str) -> str:
    s = _strip_emoji(s)
    s = _BULLET.sub("", s)
    s = re.sub(r"\s+", " ", s).strip(" .!-–—:")
    return s


def _product(s: str) -> str:
    s = _clean(s)
    return s[:1].upper() + s[1:] if s else s


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def parse_line(chunk: str) -> ParsedLine | None:
    text = _clean(chunk)
    if not text:
        return None
    if _DELETED.match(text):
        return None
    if text.endswith(":") or _GREETING.search(text):
        return ParsedLine(raw=text, kind="text")
    for rx in (_TRAILING, _LEADING):
        m = rx.match(text)
        if m and m.group("product") and not m.group("product").strip().isdigit():
            unit = m.group("unit")
            return ParsedLine(raw=text, kind="item", product=_product(m.group("product")),
                              qty=_num(m.group("qty")), unit=_UNITS.get(unit.lower()) if unit else None)
    if len(text.split()) > 6:          # a sentence, not a product name
        return ParsedLine(raw=text, kind="text")
    return ParsedLine(raw=text, kind="item", product=_product(text))


def parse_list(message: str) -> list[ParsedLine]:
    """Split a message into items (product, quantity, unit) and free-text lines."""
    out: list[ParsedLine] = []
    for chunk in _SPLIT.split(message or ""):
        line = parse_line(chunk)
        if line is not None:
            out.append(line)
    return out
