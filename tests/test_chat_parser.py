"""Unit tests for the WhatsApp list parser (no database)."""
from __future__ import annotations

from eticmonts.chat_parser import parse_list


def items(msg):
    return [(p.product, p.qty, p.unit) for p in parse_list(msg) if p.kind == "item"]


def test_example_from_the_group():
    msg = ("betterave rouge, choux cabus, choux kale, courge longues de nice, "
           "batavia rouge 2 colis, poireaux 5 colis, carottes 4 colis")
    assert items(msg) == [
        ("Betterave rouge", None, None),
        ("Choux cabus", None, None),
        ("Choux kale", None, None),
        ("Courge longues de nice", None, None),
        ("Batavia rouge", 2.0, "colis"),
        ("Poireaux", 5.0, "colis"),
        ("Carottes", 4.0, "colis"),
    ]


def test_one_item_per_line_with_bullets_emoji_and_greeting():
    msg = "Bonjour à tous, dispo cette semaine :\n- 🥬 salade x6\n• 3 bottes de radis\n* Pommes : 1,5 kg\nmerci !"
    parsed = parse_list(msg)
    assert [p.kind for p in parsed][0] == "text"
    assert items(msg) == [("Salade", 6.0, None), ("Radis", 3.0, "botte"), ("Pommes", 1.5, "kg")]


def test_decimal_comma_is_not_a_separator():
    assert items("pommes de terre 2,5 kg, oignons 10 kg") == [
        ("Pommes de terre", 2.5, "kg"), ("Oignons", 10.0, "kg")]


def test_units_are_normalised():
    assert items("courgettes 3 cagettes; œufs 30 pièces; persil 4 btes") == [
        ("Courgettes", 3.0, "cagette"), ("Œufs", 30.0, "pièce"), ("Persil", 4.0, "botte")]


def test_qty_label():
    p = parse_list("poireaux 5 colis, pommes 1,5 kg, salade, 3 bottes de radis, persil 1 botte, 2 plateaux fraises")
    assert [x.qty_label for x in p] == ["5 colis", "1,5 kg", "—", "3 bottes", "1 botte", "2 plateaux"]


def test_deleted_and_empty_messages():
    assert parse_list("Ce message a été supprimé") == []
    assert parse_list("") == []
    assert parse_list(" , ;\n") == []


def test_long_sentence_is_text():
    p = parse_list("je serai absent mardi prochain donc pas de livraison de ma part désolé")
    assert [x.kind for x in p] == ["text"]
