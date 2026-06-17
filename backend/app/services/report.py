"""Движок отчёта по тренировке.

Обобщает scripts/analyze_corridor_shuchye.py: для произвольного маршрута
(точки + порядок + опциональный старт) и трека пловца считает:
  - посещение буёв (ближайшее сближение, факт взятия по arrivalRadius);
  - cross-track отклонение (XTE) по каждому плечу и перцентили;
  - дистанцию/время/темп заплыва и «лишний» путь относительно идеала;
  - коридор вокруг плеч и GeoJSON для отрисовки карты на сайте.

Результат — JSON-сериализуемый dict, кэшируется в БД и рендерится на фронте.
"""
from __future__ import annotations

import statistics as stats
from typing import Optional

from .geo import (
    bearing_deg,
    cross_track_and_along,
    haversine,
    interpolate_leg,
    offset_polyline,
    percentile,
)
from .tracks import TrackPoint

ENDPOINT_BUFFER_M = 50.0   # игнорируем XTE у концов плеча (GPS-конус)
SAFETY_MARGIN_M = 5.0
MIN_CORRIDOR_HALF_M = 20.0
MAX_CORRIDOR_HALF_M = 95.0


class Leg:
    def __init__(self, leg_id: str, a_id: str, b_id: str, a: dict, b: dict):
        self.leg_id = leg_id
        self.from_id = a_id
        self.to_id = b_id
        self.lat1 = a["lat"]
        self.lon1 = a["lon"]
        self.lat2 = b["lat"]
        self.lon2 = b["lon"]

    @property
    def length_m(self) -> float:
        return haversine(self.lat1, self.lon1, self.lat2, self.lon2)


def _build_legs(route: dict) -> list[Leg]:
    """Плечи маршрута: старт → буи (по порядку) → финиш.

    Старт и финиш необязательны; если заданы, коридор строится от старта до
    финиша, а не только между первым и последним буем.
    """
    points = route.get("points", {})
    order = (route.get("session") or {}).get("order") or list(points.keys())
    start = route.get("start")
    finish = route.get("finish")
    seq: list[tuple[str, dict]] = []
    if start:
        seq.append(("start", {"lat": start["lat"], "lon": start["lon"], "name": start.get("name", "Старт")}))
    for pid in order:
        if pid in points:
            seq.append((pid, points[pid]))
    if finish:
        seq.append(("finish", {"lat": finish["lat"], "lon": finish["lon"], "name": finish.get("name", "Финиш")}))
    legs: list[Leg] = []
    for i in range(len(seq) - 1):
        (aid, a), (bid, b) = seq[i], seq[i + 1]
        legs.append(Leg(f"{aid}->{bid}", aid, bid, a, b))
    return legs


def _buoy_visit_indices(pts: list[TrackPoint], coords: list[tuple[float, float]]) -> list[int]:
    """Индекс ближайшего сближения с каждой целью, по порядку прохождения."""
    indices: list[int] = []
    start = 0
    for (blat, blon) in coords:
        best_i = start
        best_d = float("inf")
        for i in range(start, len(pts)):
            d = haversine(pts[i][1], pts[i][2], blat, blon)
            if d < best_d:
                best_d = d
                best_i = i
        indices.append(best_i)
        start = min(best_i + 1, len(pts) - 1)
    return indices


def _collect_xte_on_leg(pts: list[TrackPoint], i0: int, i1: int, leg: Leg) -> list[float]:
    samples: list[float] = []
    lo, hi = min(i0, i1), max(i0, i1)
    for i in range(lo, hi + 1):
        _, lat, lon = pts[i]
        xte, along, leg_len = cross_track_and_along(
            lat, lon, leg.lat1, leg.lon1, leg.lat2, leg.lon2
        )
        if along < ENDPOINT_BUFFER_M or along > leg_len - ENDPOINT_BUFFER_M:
            continue
        samples.append(abs(xte))
    return samples


def _leg_half_width(vals: list[float], leg_len_m: float) -> int:
    """Рекомендуемая полуширина коридора: p95 + запас, либо ~11% длины плеча."""
    if vals:
        return int(round(min(MAX_CORRIDOR_HALF_M,
                             max(MIN_CORRIDOR_HALF_M, percentile(vals, 95) + SAFETY_MARGIN_M))))
    return int(round(max(MIN_CORRIDOR_HALF_M, min(MAX_CORRIDOR_HALF_M, leg_len_m * 0.11 + SAFETY_MARGIN_M))))


def _track_distance(pts: list[TrackPoint]) -> float:
    total = 0.0
    for i in range(1, len(pts)):
        total += haversine(pts[i - 1][1], pts[i - 1][2], pts[i][1], pts[i][2])
    return total


def _stat_block(vals: list[float]) -> Optional[dict]:
    if not vals:
        return None
    return {
        "n": len(vals),
        "median": round(stats.median(vals), 1),
        "p90": round(percentile(vals, 90), 1),
        "p95": round(percentile(vals, 95), 1),
        "max": round(max(vals), 1),
    }


def build_report(route: dict, points: list[TrackPoint]) -> dict:
    """Главная функция: маршрут + трек -> отчёт (dict)."""
    if len(points) < 2:
        return {
            "ok": False,
            "error": "Трек слишком короткий (<2 точек).",
            "summary": {"points": len(points)},
        }

    route_points = route.get("points", {})
    order = (route.get("session") or {}).get("order") or list(route_points.keys())
    arrival_radius = float(route.get("arrivalRadiusM", 20))
    legs = _build_legs(route)

    visit_coords = [(route_points[pid]["lat"], route_points[pid]["lon"])
                    for pid in order if pid in route_points]
    visit_idx = _buoy_visit_indices(points, visit_coords)

    # --- Посещение буёв ---
    buoys_report = []
    taken_count = 0
    for k, pid in enumerate([p for p in order if p in route_points]):
        idx = visit_idx[k]
        blat, blon = visit_coords[k]
        closest = haversine(points[idx][1], points[idx][2], blat, blon)
        taken = closest <= arrival_radius
        if taken:
            taken_count += 1
        buoys_report.append({
            "id": pid,
            "name": route_points[pid].get("name", pid),
            "lat": blat,
            "lon": blon,
            "closest_m": round(closest, 1),
            "taken": taken,
        })

    # --- XTE по плечам ---
    legs_report = []
    all_xte: list[float] = []
    # Индекс трека для каждого узла маршрута, выровненный с seq из _build_legs:
    # [старт?] + буи + [финиш?]. Старт = первая точка трека, финиш = последняя.
    has_start = bool(route.get("start"))
    has_finish = bool(route.get("finish"))
    node_idx: list[int] = []
    if has_start:
        node_idx.append(0)
    node_idx.extend(visit_idx)
    if has_finish:
        node_idx.append(len(points) - 1)
    for j, leg in enumerate(legs):
        # leg j соединяет node_idx[j] и node_idx[j+1].
        i_from = node_idx[j]
        i_to = node_idx[j + 1]
        samples = _collect_xte_on_leg(points, i_from, i_to, leg)
        all_xte.extend(samples)
        half = _leg_half_width(samples, leg.length_m)
        block = _stat_block(samples) or {"n": 0}
        legs_report.append({
            "id": leg.leg_id,
            "from": leg.from_id,
            "to": leg.to_id,
            "length_m": round(leg.length_m, 1),
            "corridor_half_m": half,
            "xte": block,
        })

    # --- Сводка ---
    swum = _track_distance(points)
    ideal = sum(leg.length_m for leg in legs)
    times = [t for (t, _, _) in points if t is not None]
    duration = (max(times) - min(times)) if len(times) >= 2 else None
    pace = None
    if duration and swum > 0:
        # темп мин/100м
        pace = round((duration / 60.0) / (swum / 100.0), 2)

    summary = {
        "distance_m": round(swum, 1),
        "ideal_distance_m": round(ideal, 1),
        "extra_distance_m": round(swum - ideal, 1) if ideal else None,
        "efficiency_pct": round(100.0 * ideal / swum, 1) if swum > 0 and ideal else None,
        "duration_s": int(duration) if duration else None,
        "pace_min_100m": pace,
        "points": len(points),
        "buoys_total": len(buoys_report),
        "buoys_taken": taken_count,
        "xte_overall": _stat_block(all_xte),
    }

    return {
        "ok": True,
        "summary": summary,
        "buoys": buoys_report,
        "legs": legs_report,
        "geojson": _build_geojson(route, points, legs, legs_report, buoys_report),
    }


def _build_geojson(
    route: dict,
    points: list[TrackPoint],
    legs: list[Leg],
    legs_report: list[dict],
    buoys_report: list[dict],
) -> dict:
    """FeatureCollection для Leaflet: трек, плечи, коридор, буи, старт."""
    features: list[dict] = []

    # Трек пловца (lon, lat).
    features.append({
        "type": "Feature",
        "properties": {"kind": "track"},
        "geometry": {
            "type": "LineString",
            "coordinates": [[lon, lat] for (_, lat, lon) in points],
        },
    })

    # Плечи (хорды) + коридор.
    half_by_leg = {lr["id"]: lr["corridor_half_m"] for lr in legs_report}
    for leg in legs:
        center = interpolate_leg(leg.lat1, leg.lon1, leg.lat2, leg.lon2, step_m=20.0)
        half = float(half_by_leg.get(leg.leg_id, 25.0))
        left = offset_polyline(center, half, side=-1)
        right = offset_polyline(center, half, side=+1)
        features.append({
            "type": "Feature",
            "properties": {"kind": "leg", "id": leg.leg_id},
            "geometry": {"type": "LineString",
                         "coordinates": [[lon, lat] for (lat, lon) in center]},
        })
        # Полигон коридора: left + reversed(right).
        ring = ([[lon, lat] for (lat, lon) in left]
                + [[lon, lat] for (lat, lon) in reversed(right)])
        if ring:
            ring.append(ring[0])
        features.append({
            "type": "Feature",
            "properties": {"kind": "corridor", "id": leg.leg_id, "half_m": half},
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        })

    # Старт.
    start = route.get("start")
    if start:
        features.append({
            "type": "Feature",
            "properties": {"kind": "start", "name": start.get("name", "Старт")},
            "geometry": {"type": "Point", "coordinates": [start["lon"], start["lat"]]},
        })

    # Финиш.
    finish = route.get("finish")
    if finish:
        features.append({
            "type": "Feature",
            "properties": {"kind": "finish", "name": finish.get("name", "Финиш")},
            "geometry": {"type": "Point", "coordinates": [finish["lon"], finish["lat"]]},
        })

    # Буи.
    for b in buoys_report:
        features.append({
            "type": "Feature",
            "properties": {
                "kind": "buoy",
                "id": b["id"],
                "name": b["name"],
                "taken": b["taken"],
                "closest_m": b["closest_m"],
            },
            "geometry": {"type": "Point", "coordinates": [b["lon"], b["lat"]]},
        })

    return {"type": "FeatureCollection", "features": features}
