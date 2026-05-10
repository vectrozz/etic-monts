"""CRUD for recurrent (weekly) delivery slots.

Each row represents one regular delivery, e.g. "Tournée Mardi" with its own
weekday, cutoff weekday, cutoff time and vehicle defaults. Acts as the source
of truth for `schedule.upcoming_slots`. When the table is empty (legacy or
fresh install before seeding), `schedule` falls back to the
`delivery_cycle` JSON setting.
"""
from __future__ import annotations

from typing import Any

from .db import execute


def list_all(only_active: bool = False) -> list[dict]:
    where = "WHERE is_active" if only_active else ""
    rows = execute(
        f"SELECT id, name, weekday, cutoff_weekday, cutoff_time, default_driver, "
        f"default_vehicle, vehicle_max_weight_kg, vehicle_max_volume_l, "
        f"start_address, start_lat, start_lng, is_active "
        f"FROM recurrent_deliveries {where} ORDER BY weekday",
        fetch="all", dict_rows=True,
    ) or []
    return [dict(r) for r in rows]


def list_active() -> list[dict]:
    return list_all(only_active=True)


def get(rid: int) -> dict | None:
    row = execute(
        "SELECT id, name, weekday, cutoff_weekday, cutoff_time, default_driver, "
        "default_vehicle, vehicle_max_weight_kg, vehicle_max_volume_l, "
        "start_address, start_lat, start_lng, is_active "
        "FROM recurrent_deliveries WHERE id = %s",
        (rid,), fetch="one", dict_rows=True,
    )
    return dict(row) if row else None


def _coerce_weekday(value: Any) -> int:
    n = int(value)
    if n < 0 or n > 6:
        raise ValueError(f"weekday must be 0..6, got {n}")
    return n


def _coerce_decimal(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def upsert(*, rid: int | None, name: str, weekday: Any, cutoff_weekday: Any,
           cutoff_time: str, default_driver: str | None,
           default_vehicle: str | None, vehicle_max_weight_kg: Any,
           vehicle_max_volume_l: Any, start_address: str | None,
           start_lat: Any, start_lng: Any, is_active: bool) -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("name required")
    wd = _coerce_weekday(weekday)
    cw = _coerce_weekday(cutoff_weekday)
    payload = (
        name, wd, cw, cutoff_time or "20:00",
        (default_driver or "").strip() or None,
        (default_vehicle or "").strip() or None,
        _coerce_decimal(vehicle_max_weight_kg),
        _coerce_decimal(vehicle_max_volume_l),
        (start_address or "").strip() or None,
        _coerce_decimal(start_lat),
        _coerce_decimal(start_lng),
        bool(is_active),
    )
    if rid:
        execute(
            "UPDATE recurrent_deliveries SET name=%s, weekday=%s, cutoff_weekday=%s, "
            "cutoff_time=%s, default_driver=%s, default_vehicle=%s, "
            "vehicle_max_weight_kg=%s, vehicle_max_volume_l=%s, start_address=%s, "
            "start_lat=%s, start_lng=%s, is_active=%s WHERE id=%s",
            (*payload, rid),
        )
        return rid
    row = execute(
        "INSERT INTO recurrent_deliveries (name, weekday, cutoff_weekday, cutoff_time, "
        "default_driver, default_vehicle, vehicle_max_weight_kg, vehicle_max_volume_l, "
        "start_address, start_lat, start_lng, is_active) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        payload, fetch="one",
    )
    return row[0] if row else 0


def delete(rid: int) -> None:
    execute("DELETE FROM recurrent_deliveries WHERE id = %s", (rid,))


def toggle_active(rid: int) -> None:
    execute("UPDATE recurrent_deliveries SET is_active = NOT is_active WHERE id = %s", (rid,))
