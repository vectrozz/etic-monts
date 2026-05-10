"""Order placement: deadline enforcement + atomic stock locking.

The whole order is processed in a single DB transaction. We `SELECT FOR UPDATE`
each stock row so two concurrent clients can't double-claim the same units.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Sequence

import psycopg2.extras

from .db import get_conn
from .schedule import is_ordering_open
from .settings_store import get_delivery_cycle
from .config import load_config


class OrderError(Exception):
    pass


@dataclass
class LineRequest:
    stock_id: int
    quantity: float


@dataclass
class PlacedOrder:
    order_id: int
    total_amount: float
    total_weight_kg: float
    total_volume_l: float
    line_count: int


def place_order(*, client_id: int, cycle_date: date, lines: Sequence[LineRequest],
                notes: str | None = None, now: datetime | None = None) -> PlacedOrder:
    """Place an order atomically. Raises OrderError on validation failure."""
    if not lines:
        raise OrderError("Aucun produit sélectionné.")

    # Normalise + drop empty lines
    cleaned = [l for l in lines if l.quantity and l.quantity > 0]
    if not cleaned:
        raise OrderError("Aucune quantité saisie.")

    cfg = load_config()
    cycle_cfg = get_delivery_cycle()
    is_open, deadline = is_ordering_open(cycle_cfg, cycle_date, tz_name=cfg.timezone, now=now)
    if not is_open:
        raise OrderError(
            "La fenêtre de commande pour cette livraison est fermée"
            + (f" (clôture le {deadline.strftime('%d/%m %H:%M')})" if deadline else "")
        )

    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            # Lock & verify stocks
            stock_ids = [int(l.stock_id) for l in cleaned]
            cur.execute(
                "SELECT s.id, s.product_id, s.producteur_id, s.cycle_date, "
                "s.quantity_available, s.quantity_reserved, s.price, "
                "p.unit_weight_kg, p.unit_volume_l, p.default_price, p.name "
                "FROM stocks s JOIN products p ON p.id = s.product_id "
                "WHERE s.id = ANY(%s) FOR UPDATE",
                (stock_ids,),
            )
            stock_rows = {r["id"]: r for r in cur.fetchall()}
            if len(stock_rows) != len(set(stock_ids)):
                raise OrderError("Un ou plusieurs produits ne sont plus disponibles.")

            # Verify cycle + remaining qty for each line.
            # Pool stocks (cycle_date IS NULL) satisfy any cycle.
            for line in cleaned:
                row = stock_rows[line.stock_id]
                if row["cycle_date"] is not None and row["cycle_date"] != cycle_date:
                    raise OrderError("Cycle de livraison incohérent pour un article.")
                remaining = float(row["quantity_available"]) - float(row["quantity_reserved"])
                if line.quantity > remaining + 1e-9:
                    raise OrderError(
                        f"Stock insuffisant pour {row['name']} : "
                        f"demandé {line.quantity}, disponible {remaining:g}"
                    )

            # Verify client exists and is active
            cur.execute("SELECT id, is_active FROM clients WHERE id = %s FOR UPDATE",
                        (client_id,))
            c = cur.fetchone()
            if c is None or not c["is_active"]:
                raise OrderError("Client inconnu ou désactivé.")

            # Create order
            cur.execute(
                "INSERT INTO orders (client_id, cycle_date, status, notes) "
                "VALUES (%s, %s, 'pending', %s) RETURNING id",
                (client_id, cycle_date, notes),
            )
            order_id = cur.fetchone()["id"]

            total_amount = 0.0
            total_weight = 0.0
            total_volume = 0.0
            for line in cleaned:
                row = stock_rows[line.stock_id]
                unit_price = float(row["price"] if row["price"] is not None
                                   else (row["default_price"] or 0))
                line_total = round(unit_price * line.quantity, 2)
                weight = float(row["unit_weight_kg"] or 0) * line.quantity
                volume = float(row["unit_volume_l"] or 0) * line.quantity
                cur.execute(
                    "INSERT INTO order_items (order_id, stock_id, product_id, "
                    "producteur_id, quantity, unit_price, line_total) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (order_id, line.stock_id, row["product_id"], row["producteur_id"],
                     line.quantity, unit_price, line_total),
                )
                cur.execute(
                    "UPDATE stocks SET quantity_reserved = quantity_reserved + %s, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (line.quantity, line.stock_id),
                )
                total_amount += line_total
                total_weight += weight
                total_volume += volume

            cur.execute(
                "UPDATE orders SET total_amount = %s, total_weight_kg = %s, "
                "total_volume_l = %s WHERE id = %s",
                (round(total_amount, 2), round(total_weight, 3),
                 round(total_volume, 3), order_id),
            )
            conn.commit()
            return PlacedOrder(
                order_id=order_id,
                total_amount=round(total_amount, 2),
                total_weight_kg=round(total_weight, 3),
                total_volume_l=round(total_volume, 3),
                line_count=len(cleaned),
            )
        except OrderError:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            raise OrderError(f"Erreur interne : {e}")
        finally:
            cur.close()
