"""Группировка заплывов в совместные тренировки.

Две тренировки объединяются, если их временные интервалы пересекаются И центры
областей координат находятся в пределах радиуса близости (2 км). Группы —
компоненты связности этого отношения.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Activity, Route
from .geo import haversine
from .tracks import dicts_to_points

AREA_RADIUS_M = 2000.0   # радиус близости областей
MAX_TRACK_POINTS = 1500  # прореживание трека для совместной карты


def _track_meta(activity: Activity) -> tuple[float, float, float, float] | None:
    """(t_start, t_end, lat_centroid, lon_centroid) или None."""
    pts = dicts_to_points(activity.track or [])
    if len(pts) < 2:
        return None
    times = [t for (t, _, _) in pts if t is not None]
    lat = sum(p[1] for p in pts) / len(pts)
    lon = sum(p[2] for p in pts) / len(pts)
    if times:
        return min(times), max(times), lat, lon
    if activity.recorded_at:
        ts = activity.recorded_at.timestamp()
        return ts, ts, lat, lon
    return None


def _related(m1, m2) -> bool:
    s1, e1, la1, lo1 = m1
    s2, e2, la2, lo2 = m2
    time_overlap = s1 <= e2 and s2 <= e1
    near = haversine(la1, lo1, la2, lo2) <= AREA_RADIUS_M
    return time_overlap and near


def group_public_activities(db: Session) -> list[list[Activity]]:
    acts = db.scalars(
        select(Activity).where(Activity.is_public.is_(True))
        .order_by(Activity.recorded_at, Activity.created_at)
    ).all()
    items = [(a, _track_meta(a)) for a in acts]
    items = [(a, m) for (a, m) in items if m is not None]

    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    for i in range(n):
        for j in range(i + 1, n):
            if _related(items[i][1], items[j][1]):
                union(i, j)

    groups: dict[int, list[Activity]] = {}
    for idx, (a, _m) in enumerate(items):
        groups.setdefault(find(idx), []).append(a)
    # Сортируем участников по времени старта.
    out = list(groups.values())
    for g in out:
        g.sort(key=lambda a: (a.recorded_at or a.created_at))
    out.sort(key=lambda g: (g[0].recorded_at or g[0].created_at), reverse=True)
    return out


def _downsample(points: list[tuple], limit: int = MAX_TRACK_POINTS) -> list[tuple]:
    if len(points) <= limit:
        return points
    step = (len(points) + limit - 1) // limit
    sampled = points[::step]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def _route_legs(route: Route) -> list[dict]:
    points = route.points or {}
    order = route.order or list(points.keys())
    seq: list[tuple[str, dict]] = []
    if route.start:
        seq.append(("start", route.start))
    for pid in order:
        if pid in points:
            seq.append((pid, points[pid]))
    if route.finish:
        seq.append(("finish", route.finish))
    legs = []
    for i in range(len(seq) - 1):
        (aid, a), (bid, b) = seq[i], seq[i + 1]
        legs.append({
            "from": aid, "to": bid,
            "a": [a["lat"], a["lon"]],
            "b": [b["lat"], b["lon"]],
        })
    return legs


def build_group_payload(db: Session, members: list[Activity]) -> dict:
    """Данные совместной тренировки для карты: маршрут, плечи, треки пловцов."""
    route = None
    for a in members:
        if a.route_id:
            route = db.get(Route, a.route_id)
            if route:
                break

    route_data = None
    if route:
        points = route.points or {}
        order = route.order or list(points.keys())
        route_data = {
            "id": route.id,
            "name": route.name,
            "arrivalRadiusM": route.arrival_radius_m,
            "points": points,
            "order": order,
            "start": route.start,
            "finish": route.finish,
            "legs": _route_legs(route),
        }

    swimmers = []
    for a in members:
        pts = _downsample(dicts_to_points(a.track or []))
        summary = (a.report or {}).get("summary") if a.report else None
        buoys = (a.report or {}).get("buoys") if a.report else None
        swimmers.append({
            "id": a.id,
            "share_token": a.share_token,
            "name": a.athlete.name if a.athlete else a.name,
            "recorded_at": a.recorded_at.isoformat() if a.recorded_at else None,
            "track": [[lat, lon] for (_, lat, lon) in pts],
            "summary": summary,
            "buoys": buoys,
        })

    start = members[0].recorded_at
    return {
        "group_id": members[0].share_token,
        "route": route_data,
        "recorded_at": start.isoformat() if start else None,
        "swimmers": swimmers,
    }
