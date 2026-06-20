"""Геометрия на сфере: расстояния, азимуты, cross-track, смещение полилиний.

Перенос логики из scripts/analyze_corridor_shuchye.py в обобщённый вид
(без привязки к конкретному озеру). Используется движком отчёта и при
экспорте GPX коридора.
"""
from __future__ import annotations

import math

EARTH_RADIUS_M = 6371000.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние между двумя точками в метрах."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2.0) ** 2
    )
    return EARTH_RADIUS_M * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Начальный азимут (0..360) от точки 1 к точке 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def destination(lat: float, lon: float, brg_deg: float, dist_m: float) -> tuple[float, float]:
    """Точка на расстоянии dist_m по азимуту brg_deg от (lat, lon)."""
    r = EARTH_RADIUS_M
    p1 = math.radians(lat)
    l1 = math.radians(lon)
    brg = math.radians(brg_deg)
    p2 = math.asin(
        math.sin(p1) * math.cos(dist_m / r)
        + math.cos(p1) * math.sin(dist_m / r) * math.cos(brg)
    )
    l2 = l1 + math.atan2(
        math.sin(brg) * math.sin(dist_m / r) * math.cos(p1),
        math.cos(dist_m / r) - math.sin(p1) * math.sin(p2),
    )
    return math.degrees(p2), math.degrees(l2)


def cross_track_and_along(
    lat: float,
    lon: float,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> tuple[float, float, float]:
    """(cross_track_m со знаком, along_m, leg_length_m). +XTE = справа от курса плеча."""
    leg_len = haversine(lat1, lon1, lat2, lon2)
    if leg_len < 1.0:
        return 0.0, 0.0, leg_len
    brg_12 = bearing_deg(lat1, lon1, lat2, lon2)
    brg_1p = bearing_deg(lat1, lon1, lat, lon)
    dist_1p = haversine(lat1, lon1, lat, lon)
    rel = math.radians(brg_1p - brg_12)
    along = dist_1p * math.cos(rel)
    xte = dist_1p * math.sin(rel)
    return xte, along, leg_len


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(round((p / 100.0) * (len(s) - 1)))
    return s[idx]


def interpolate_leg(
    lat1: float, lon1: float, lat2: float, lon2: float, step_m: float = 20.0
) -> list[tuple[float, float]]:
    """Линейная интерполяция хорды плеча (для рисования коридора)."""
    length = haversine(lat1, lon1, lat2, lon2)
    n = max(2, int(length / step_m) + 1)
    pts: list[tuple[float, float]] = []
    for i in range(n):
        t = i / (n - 1)
        pts.append((lat1 + t * (lat2 - lat1), lon1 + t * (lon2 - lon1)))
    return pts


def route_chord_distance_m(route: dict) -> float:
    """Сумма длин хорд по плечам маршрута (старт → буи → финиш)."""
    points = route.get("points") or {}
    order = (route.get("session") or {}).get("order") or list(points.keys())
    start = route.get("start")
    finish = route.get("finish")
    seq: list[tuple[float, float]] = []
    if start:
        seq.append((start["lat"], start["lon"]))
    for pid in order:
        if pid in points:
            p = points[pid]
            seq.append((p["lat"], p["lon"]))
    if finish:
        seq.append((finish["lat"], finish["lon"]))
    total = 0.0
    for i in range(len(seq) - 1):
        a, b = seq[i], seq[i + 1]
        total += haversine(a[0], a[1], b[0], b[1])
    return total


def offset_polyline(
    center: list[tuple[float, float]], half_width_m: float, side: int
) -> list[tuple[float, float]]:
    """Смещение полилинии на half_width_m влево (side<0) или вправо (side>0)."""
    if len(center) < 2:
        return center
    out: list[tuple[float, float]] = []
    sign = 1.0 if side > 0 else -1.0
    for i in range(len(center)):
        lat, lon = center[i]
        if i < len(center) - 1:
            nlat, nlon = center[i + 1]
        else:
            plat, plon = center[i - 1]
            lat, lon = center[i]
            nlat, nlon = lat + (lat - plat), lon + (lon - plon)
        brg = bearing_deg(lat, lon, nlat, nlon)
        off_brg = (brg + sign * 90.0) % 360.0
        out.append(destination(lat, lon, off_brg, half_width_m))
    return out
