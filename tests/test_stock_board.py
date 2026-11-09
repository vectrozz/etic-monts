"""Stock board rules (no database)."""
from __future__ import annotations

from datetime import datetime, timedelta

from eticmonts.chat_parser import parse_list, product_key
from eticmonts.stock_board import compute

T0 = datetime(2026, 11, 2, 9, 0)


def msg(i, farm, body, hours=0, farm_name=None):
    return {"id": i, "ferme_id": farm, "farm_name": farm_name or f"Ferme {farm}", "body": body,
            "posted_at": T0 + timedelta(hours=hours)}


def row(board, label_key):
    return next(r for r in board.products if r.key == product_key(label_key))


def test_totals_and_cells_across_farms():
    b = compute([
        msg(1, 1, "batavia rouge 2 colis, poireaux 6 colis, carottes 4 colis"),
        msg(2, 2, "poireau 3 colis\nPoireaux 2\ncarottes, betterave rouge, choux kale", hours=1),
    ])
    assert [f.name for f in b.farms] == ["Ferme 1", "Ferme 2"]
    poireaux = row(b, "poireaux")
    # "2" and "2 colis" are the same quantity: one vegetable, one unit.
    # Farm 2 wrote poireaux twice in the same list: the last line wins for that farm.
    assert poireaux.unit == "colis" and poireaux.qty_sum == 8
    assert poireaux.total_label == "8 colis"
    assert poireaux.cell_label(poireaux.cells[2]) == "2 colis"
    assert set(poireaux.cells) == {1, 2}
    carottes = row(b, "carottes")
    assert carottes.total_label == "4 colis (1 ferme sans quantité)"
    assert carottes.headline == "4 colis" and carottes.unknown_note == "+ 1 ferme sans quantité"
    assert row(b, "choux kale").total_label == "dispo (1 ferme, quantité non précisée)"
    assert row(b, "choux kale").cell_label(row(b, "choux kale").cells[2]) == "dispo"


def test_unitless_quantities_take_the_vegetable_unit():
    b = compute([
        msg(1, 1, "poireaux 2, carottes 3, navets 1"),                       # nobody wrote a unit yet
        msg(2, 2, "poireaux 4 colis, carottes 2, navets 5 bottes", hours=1),
        msg(3, 3, "poireaux 1 colis, salade 1,5, navets 2", hours=2),
    ])
    assert row(b, "poireaux").total_label == "7 colis"
    assert row(b, "carottes").total_label == "5", "no unit anywhere: plain number"
    assert row(b, "navets").total_label == "8 bottes"
    assert row(b, "salade").total_label == "1,5"
    poireaux = row(b, "poireaux")
    assert [poireaux.cell_label(poireaux.cells[f]) for f in (1, 2, 3)] == ["2 colis", "4 colis", "1 colis"]


def test_full_list_replaces_previous_list():
    b = compute([
        msg(1, 1, "poireaux 5 colis, carottes 4 colis, navets 2 colis"),
        msg(2, 1, "courges 3 colis, radis 6 bottes, salade x8", hours=48),
    ])
    keys = {r.key for r in b.products}
    assert keys == {product_key(x) for x in ("courges", "radis", "salade")}
    assert b.farms[0].list_at == T0 + timedelta(hours=48)


def test_short_message_updates_only_named_products():
    b = compute([
        msg(1, 1, "poireaux 5 colis, carottes 4 colis, navets 2 colis"),
        msg(2, 1, "poireaux 2 colis", hours=3),
    ])
    assert row(b, "poireaux").total_label == "2 colis"
    assert row(b, "carottes").total_label == "4 colis"
    assert b.farms[0].updates == 1


def test_sold_out_removes_only_existing_products():
    b = compute([
        msg(1, 1, "poireaux 5 colis, carottes 4 colis, navets 2 colis"),
        msg(2, 1, "plus de poireaux", hours=2),
        msg(3, 1, "Plus de livraison mardi", hours=3),
        msg(4, 1, "radis : terminé", hours=4),
    ])
    assert row(b, "poireaux").total_label == "épuisé" and row(b, "poireaux").farms_available == 0
    assert not any("livraison" in r.key for r in b.products)
    assert not any(r.key == "radis" for r in b.products)
    assert b.products[-1].key == product_key("poireaux"), "sold-out rows sink to the bottom"


def test_chatter_is_not_stock():
    b = compute([
        msg(1, 1, "Merci 🙂\nElle s'appelle Nausicaä"),
        msg(2, 1, "ok à mardi"),
        msg(3, 1, "Livraison le 12"),
        msg(4, 1, "ok pour 3"),
        msg(5, 1, "top merci, 2 colis pour moi"),
        msg(6, 1, "oui, non, peut-être"),
        msg(7, 1, "je passe vers 10h"),
        msg(8, 2, "betterave rouge, choux cabus, choux kale", hours=1),   # 3 products, no quantity: a list
    ])
    assert [f.ferme_id for f in b.farms] == [2]
    assert len(b.products) == 3
    assert b.used == {8}


def test_chatter_after_a_list_does_not_replace_it():
    b = compute([
        msg(1, 1, "poireaux 5 colis, carottes 4 colis, navets 2 colis"),
        msg(2, 1, "oui, non, peut-être", hours=1),
        msg(3, 1, "salade 10", hours=2),            # unknown product, no unit: not counted
        msg(4, 1, "fenouil 3 colis", hours=3),      # new product with a unit: added
        msg(5, 1, "carottes 2", hours=4),           # known product, no unit: updated
    ])
    assert {r.label for r in b.products} == {"Poireaux", "Carottes", "Navets", "Fenouil"}
    assert row(b, "carottes").total_label == "2 colis", "'carottes 2' = 2 colis, carottes come in colis"
    assert b.used == {1, 4, 5}


def test_sold_out_parsing_forms():
    for text in ("plus de poireaux", "fini les poireaux", "poireaux épuisés", "poireaux : terminé",
                 "poireaux fini", "rupture de poireaux", "poireaux plus dispo"):
        p = [x for x in parse_list(text) if x.kind == "item"]
        assert len(p) == 1 and p[0].sold_out and product_key(p[0].product) == "poireau", text


def test_product_key_groups_spellings():
    assert product_key("Poireaux") == product_key("poireau")
    assert product_key("Choux kale") == product_key("chou kale")
    assert product_key("Pommes de terre") == "pomme de terre"
    assert product_key("Œufs") == "oeuf" and product_key("Radis") == "radis" and product_key("Noix") == "noix"
