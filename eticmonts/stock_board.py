"""Vegetable stock, total and per farm, computed from the WhatsApp lists.

Nothing is typed in: the board is rebuilt from the messages of the period
every time it is displayed, so re-linking a sender to another farm or
excluding a message is reflected immediately.

Rules, per farm, messages in chronological order:
  * full list (≥ FULL_LIST_MIN products) → REPLACES the farm's stock;
  * shorter message → updates only the products it names, and only lines
    with a quantity whose product is known (seen in a full list of the
    period, or already in the farm's stock) or comes with a unit
    ("fenouil 3 colis");
  * "plus de poireaux", "carottes épuisées" → that product is sold out
    (only if the farm had it: never creates a row);
  * anything else is conversation ("Merci !", "Livraison le 12", "ok pour 3").
Spellings are grouped with chat_parser.product_key (poireaux = poireau).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from .chat_parser import ParsedLine, parse_list, product_key
from .db import execute

FULL_LIST_MIN = 3


@dataclass
class Entry:
    label: str                    # product as written by the farm
    line: ParsedLine
    posted_at: datetime
    message_id: int

    @property
    def available(self) -> bool:
        return not self.line.sold_out


@dataclass
class FarmStock:
    ferme_id: int
    name: str
    list_at: datetime | None = None           # last full list
    updated_at: datetime | None = None        # last message that changed the stock
    updates: int = 0                          # partial updates after the last full list
    items: dict[str, Entry] = field(default_factory=dict)   # product key → entry


@dataclass
class ProductRow:
    key: str
    label: str
    cells: dict[int, Entry]                    # ferme_id → entry
    totals: dict[str, float]                   # unit ('' = no unit) → summed quantity
    farms_available: int
    farms_unknown_qty: int                     # available but no quantity given

    @property
    def qty_total(self) -> str:
        """Summed quantities, one per unit: '12 colis + 5 kg' ('' when none was given)."""
        return " + ".join(
            ParsedLine(raw="", kind="item", qty=q, unit=u or None).qty_label
            for u, q in sorted(self.totals.items(), key=lambda kv: (kv[0] == "", kv[0])))

    @property
    def headline(self) -> str:
        return self.qty_total or ("dispo" if self.farms_available else "épuisé")

    @property
    def unknown_note(self) -> str:
        n = self.farms_unknown_qty
        if not n:
            return ""
        farms = f"{n} ferme{'s' if n > 1 else ''}"
        return f"+ {farms} sans quantité" if self.qty_total else f"{farms}, quantité non précisée"

    @property
    def total_label(self) -> str:
        """'12 colis + 5 kg', '3 colis (+ 1 ferme sans quantité)', 'dispo (1 ferme, quantité non précisée)'."""
        return f"{self.headline} ({self.unknown_note.removeprefix('+ ')})" if self.unknown_note else self.headline


@dataclass
class Board:
    farms: list[FarmStock]
    products: list[ProductRow]
    used: set[int] = field(default_factory=set)   # ids of the messages that changed the stock


# First words that make a "product" chatter: "ok pour 3", "2 colis pour moi", "oui, non, peut-être".
_CHATTER = {
    "a", "au", "aux", "bravo", "ca", "c", "cool", "d", "daccord", "de", "des", "du", "elle", "genial", "il", "j",
    "je", "l", "la", "le", "les", "livraison", "commande", "merci", "moi", "non", "nous", "ok", "okay", "on",
    "oui", "parfait", "peut", "pour", "rdv", "super", "top", "toi", "tu", "un", "une", "vous", "yes",
}


def _key(p: ParsedLine) -> str:
    return product_key(p.product) if p.kind == "item" and p.product else ""


def _product_like(key: str) -> bool:
    words = key.replace("'", " ").split()
    return 0 < len(words) <= 5 and words[0] not in _CHATTER


def _is_full_list(items: list[ParsedLine]) -> bool:
    return sum(1 for p in items if not p.sold_out and _product_like(_key(p))) >= FULL_LIST_MIN


def compute(messages: list[dict]) -> Board:
    """messages: dicts with id, ferme_id, farm_name, body, posted_at (any order)."""
    ordered = sorted(messages, key=lambda m: (m["posted_at"], m["id"]))
    parsed = [(m, [p for p in parse_list(m["body"]) if _key(p)]) for m in ordered]
    # vegetables seen in a full list of the period, any farm
    known = {_key(p) for _, items in parsed if _is_full_list(items) for p in items if not p.sold_out}

    farms: dict[int, FarmStock] = {}
    labels: dict[str, Counter] = defaultdict(Counter)
    used: set[int] = set()
    for m, items in parsed:
        farm = farms.get(m["ferme_id"])
        mine = farm.items if farm else {}
        full = _is_full_list(items)
        if full:
            items = [p for p in items if p.sold_out or _product_like(_key(p))]
        else:
            # a short message only touches products with a quantity (or "plus de …" for a product
            # the farm has): "Livraison le 12", "ok pour 3" are conversation
            items = [p for p in items if (p.sold_out and _key(p) in mine) or (
                not p.sold_out and p.qty is not None and _product_like(_key(p))
                and (_key(p) in known or _key(p) in mine or p.unit))]
        if not items:
            continue
        farm = farms.setdefault(m["ferme_id"], FarmStock(m["ferme_id"], m["farm_name"]))
        if full:
            farm.items = {}
            farm.list_at, farm.updates = m["posted_at"], 0
        elif farm.list_at is not None:
            farm.updates += 1
        for p in items:
            if p.sold_out and _key(p) not in farm.items:
                continue                                  # "plus de radis" in a list without radis
            farm.items[_key(p)] = Entry(p.product, p, m["posted_at"], m["id"])
            labels[_key(p)][p.product] += 1
        farm.updated_at = m["posted_at"]
        used.add(m["id"])

    rows: dict[str, ProductRow] = {}
    for farm in farms.values():
        for key, e in farm.items.items():
            row = rows.setdefault(key, ProductRow(key, labels[key].most_common(1)[0][0], {}, {}, 0, 0))
            row.cells[farm.ferme_id] = e
            if not e.available:
                continue
            row.farms_available += 1
            if e.line.qty is None:
                row.farms_unknown_qty += 1
            else:
                unit = e.line.unit or ""
                row.totals[unit] = row.totals.get(unit, 0) + e.line.qty

    products = sorted(rows.values(), key=lambda r: (r.farms_available == 0, r.key))   # key: accent-free
    farm_list = sorted((f for f in farms.values() if f.items), key=lambda f: product_key(f.name))
    return Board(farm_list, products, used)


def load(days: int) -> Board:
    rows = execute(
        "SELECT m.id, s.ferme_id, COALESCE(NULLIF(f.farmname, ''), f.name) AS farm_name, m.body, m.posted_at "
        "FROM chat_messages m JOIN chat_senders s ON s.sender_name = m.sender_name "
        "JOIN fermes f ON f.id = s.ferme_id "
        "WHERE NOT s.ignored AND m.status <> 'ignored' "
        "AND m.posted_at >= now() - make_interval(days => %s)",
        (days,), fetch="all", dict_rows=True,
    ) or []
    return compute([dict(r) for r in rows])
