"""Lightweight delivery routing.

Pure-Python: no external geocoder. Coordinates are entered manually on
clients (lat/lng). When coordinates are missing we fall back to ordering by
postal code so the planner still produces a coherent route.

The optimiser is a nearest-neighbour heuristic seeded at the depot, then a
single 2-opt pass — good enough for tournées of 5-30 stops.
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Iterable, Sequence


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1 = a
    lat2, lng2 = b
    rlat1, rlat2 = radians(lat1), radians(lat2)
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    h = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlng / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(h))


def _route_distance(points: Sequence[tuple[float, float]], depot: tuple[float, float]) -> float:
    if not points:
        return 0.0
    total = haversine_km(depot, points[0])
    for i in range(len(points) - 1):
        total += haversine_km(points[i], points[i + 1])
    total += haversine_km(points[-1], depot)
    return total


def nearest_neighbour(points: Sequence[tuple[float, float]],
                      depot: tuple[float, float]) -> list[int]:
    """Return the ordering of point indices."""
    remaining = list(range(len(points)))
    order: list[int] = []
    cursor = depot
    while remaining:
        best = min(remaining, key=lambda i: haversine_km(cursor, points[i]))
        order.append(best)
        cursor = points[best]
        remaining.remove(best)
    return order


def two_opt(order: list[int], points: Sequence[tuple[float, float]],
            depot: tuple[float, float], max_iter: int = 200) -> list[int]:
    """Single-pass 2-opt improvement."""
    if len(order) < 4:
        return order
    best = list(order)
    best_d = _route_distance([points[i] for i in best], depot)
    improved = True
    iters = 0
    while improved and iters < max_iter:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                cand = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                d = _route_distance([points[k] for k in cand], depot)
                if d + 1e-9 < best_d:
                    best = cand
                    best_d = d
                    improved = True
                    break
            if improved:
                break
        iters += 1
    return best


def plan_route(stops: list[dict], depot: dict | None) -> list[dict]:
    """Order a list of stop dicts.

    Each stop must have at least `id`, optionally `lat`, `lng`, `postal_code`.
    Stops with full lat/lng are routed via NN+2-opt anchored at the depot.
    Stops without coordinates are appended at the end, ordered by postal code.

    Returns a new list of stops in route order, with `position` set 1..N.
    """
    geo: list[dict] = []
    rest: list[dict] = []
    for s in stops:
        try:
            lat = float(s.get("lat")) if s.get("lat") is not None else None
            lng = float(s.get("lng")) if s.get("lng") is not None else None
        except (TypeError, ValueError):
            lat = lng = None
        if lat is not None and lng is not None:
            geo.append({**s, "_lat": lat, "_lng": lng})
        else:
            rest.append(s)

    ordered: list[dict] = []
    if geo:
        if depot and depot.get("lat") is not None and depot.get("lng") is not None:
            try:
                d = (float(depot["lat"]), float(depot["lng"]))
            except (TypeError, ValueError):
                d = (geo[0]["_lat"], geo[0]["_lng"])
        else:
            d = (geo[0]["_lat"], geo[0]["_lng"])
        pts = [(s["_lat"], s["_lng"]) for s in geo]
        order = nearest_neighbour(pts, d)
        order = two_opt(order, pts, d)
        ordered.extend(geo[i] for i in order)

    rest.sort(key=lambda s: (str(s.get("postal_code") or ""), str(s.get("city") or "")))
    ordered.extend(rest)

    for idx, s in enumerate(ordered, start=1):
        s["position"] = idx
        s.pop("_lat", None)
        s.pop("_lng", None)
    return ordered
