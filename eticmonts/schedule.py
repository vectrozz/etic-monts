"""Delivery cycle + order cutoff logic.

The settings.delivery_cycle defines:
  - delivery_weekdays: ISO weekdays (0=Mon..6=Sun) on which deliveries happen
  - cutoff_weekdays:    matching weekdays for order deadlines (typically the day before)
  - cutoff_time:        HH:MM at which orders for the next delivery close

If `cutoff_weekdays` and `delivery_weekdays` are both supplied, we pair them
in order. Otherwise we fall back to deadline = (delivery_date - 1 day) at cutoff_time.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

try:
    from zoneinfo import ZoneInfo  # py>=3.9
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


@dataclass(frozen=True)
class CycleSlot:
    delivery_date: date
    deadline: datetime           # tz-aware
    is_open: bool                 # ordering window currently open
    label: str                    # human label e.g. "Mardi 12 mai"

    def to_dict(self) -> dict:
        return {
            "delivery_date": self.delivery_date.isoformat(),
            "deadline": self.deadline.isoformat(),
            "is_open": self.is_open,
            "label": self.label,
        }


def _parse_time(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _tz(name: str):
    if ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone.utc


def _next_weekday(start: date, weekday: int) -> date:
    """Return the next date (>= start) whose weekday matches."""
    diff = (weekday - start.weekday()) % 7
    return start + timedelta(days=diff)


def _load_recurrent_rules() -> list[dict]:
    """Return the list of active recurring slots {weekday, cutoff_weekday, cutoff_time, name}.

    Reads from `recurrent_deliveries` table when available; falls back to the
    legacy `delivery_cycle` setting otherwise (e.g. test environments or
    pre-migration installs).
    """
    try:
        from .recurrent_deliveries import list_active
        rows = list_active()
        if rows:
            return [{
                "weekday": int(r["weekday"]),
                "cutoff_weekday": int(r["cutoff_weekday"]),
                "cutoff_time": r["cutoff_time"].strftime("%H:%M") if hasattr(r["cutoff_time"], "strftime") else str(r["cutoff_time"]),
                "name": r["name"],
            } for r in rows]
    except Exception:
        pass
    return []


def upcoming_slots(cfg: dict, *, tz_name: str = "Europe/Paris",
                   now: datetime | None = None, count: int = 4) -> list[CycleSlot]:
    """Return next `count` delivery slots with their deadlines.

    Source of truth: `recurrent_deliveries` table. When the table is empty,
    the legacy `delivery_cycle` config (cfg argument) is used.
    """
    tz = _tz(tz_name)
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)

    rules = _load_recurrent_rules()

    if not rules:
        # Legacy fallback: derive rules from cfg lists
        delivery_wds = list(cfg.get("delivery_weekdays") or [])
        cutoff_wds = list(cfg.get("cutoff_weekdays") or [])
        ct = str(cfg.get("cutoff_time") or "20:00")
        for i, wd in enumerate(delivery_wds):
            cw = cutoff_wds[i] if i < len(cutoff_wds) else (wd - 1) % 7
            rules.append({"weekday": wd, "cutoff_weekday": cw, "cutoff_time": ct,
                          "name": ""})
    if not rules:
        return []

    by_wd = {r["weekday"]: r for r in rules}

    slots: list[CycleSlot] = []
    cursor_day = now.date()
    safety = 0
    while len(slots) < count and safety < 200:
        safety += 1
        candidates = [_next_weekday(cursor_day, wd) for wd in by_wd.keys()]
        delivery_date = min(candidates)
        rule = by_wd[delivery_date.weekday()]

        cutoff_time = _parse_time(rule["cutoff_time"])
        cutoff_wd = rule["cutoff_weekday"]
        offset = (delivery_date.weekday() - cutoff_wd) % 7
        if offset == 0:
            offset = 7
        cutoff_date = delivery_date - timedelta(days=offset)
        deadline_dt = datetime.combine(cutoff_date, cutoff_time, tzinfo=tz)

        label = _fr_label(delivery_date)
        if rule.get("name"):
            label = f"{rule['name']} — {label}"

        slots.append(CycleSlot(
            delivery_date=delivery_date,
            deadline=deadline_dt,
            is_open=now < deadline_dt,
            label=label,
        ))
        cursor_day = delivery_date + timedelta(days=1)
    return slots


def is_ordering_open(cfg: dict, target: date, *, tz_name: str = "Europe/Paris",
                     now: datetime | None = None) -> tuple[bool, datetime | None]:
    """Return (open, deadline) for a given delivery date."""
    tz = _tz(tz_name)
    now = now or datetime.now(tz)
    for slot in upcoming_slots(cfg, tz_name=tz_name, now=now, count=12):
        if slot.delivery_date == target:
            return slot.is_open, slot.deadline
    return False, None


_FR_DAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
_FR_MONTHS = ["", "janvier", "février", "mars", "avril", "mai", "juin",
              "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def _fr_label(d: date) -> str:
    return f"{_FR_DAYS[d.weekday()]} {d.day} {_FR_MONTHS[d.month]}"
