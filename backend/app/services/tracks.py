"""Парсинг треков (GPX / TCX / FIT) в единый список точек и сборка GPX.

TrackPoint = (epoch_seconds | None, lat, lon).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Iterable, Optional

TrackPoint = tuple[Optional[float], float, float]


def _parse_iso(text: str) -> Optional[float]:
    text = text.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_gpx_bytes(data: bytes) -> list[TrackPoint]:
    """Все trkpt из GPX по порядку. Waypoint'ы (wpt) игнорируются."""
    root = ET.fromstring(data)
    pts: list[TrackPoint] = []
    for elem in root.iter():
        if _localname(elem.tag) != "trkpt":
            continue
        lat = elem.get("lat")
        lon = elem.get("lon")
        if lat is None or lon is None:
            continue
        t: Optional[float] = None
        for child in elem:
            if _localname(child.tag) == "time" and child.text:
                t = _parse_iso(child.text)
        pts.append((t, float(lat), float(lon)))
    return pts


def parse_tcx_bytes(data: bytes) -> list[TrackPoint]:
    """Trackpoint из TCX (экспорт Garmin Connect)."""
    root = ET.fromstring(data)
    pts: list[TrackPoint] = []
    for tp in root.iter():
        if _localname(tp.tag) != "Trackpoint":
            continue
        t: Optional[float] = None
        lat = lon = None
        for child in tp:
            name = _localname(child.tag)
            if name == "Time" and child.text:
                t = _parse_iso(child.text)
            elif name == "Position":
                for pos in child:
                    pname = _localname(pos.tag)
                    if pname == "LatitudeDegrees" and pos.text:
                        lat = float(pos.text)
                    elif pname == "LongitudeDegrees" and pos.text:
                        lon = float(pos.text)
        if lat is not None and lon is not None:
            pts.append((t, lat, lon))
    return pts


def parse_fit_bytes(data: bytes) -> list[TrackPoint]:
    """record-сообщения из FIT. Требует пакет fitparse."""
    try:
        from fitparse import FitFile  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ValueError(
            "Для разбора FIT нужен пакет fitparse (pip install fitparse)"
        ) from exc

    import io

    fit = FitFile(io.BytesIO(data))
    pts: list[TrackPoint] = []
    for record in fit.get_messages("record"):
        values = {d.name: d.value for d in record}
        lat_semi = values.get("position_lat")
        lon_semi = values.get("position_long")
        if lat_semi is None or lon_semi is None:
            continue
        # Полукруги (semicircles) -> градусы.
        lat = lat_semi * (180.0 / 2**31)
        lon = lon_semi * (180.0 / 2**31)
        ts = values.get("timestamp")
        t: Optional[float] = None
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            t = ts.timestamp()
        pts.append((t, lat, lon))
    return pts


def parse_track(filename: str, data: bytes) -> list[TrackPoint]:
    """Определить формат по расширению и разобрать."""
    lower = filename.lower()
    if lower.endswith(".gpx"):
        return parse_gpx_bytes(data)
    if lower.endswith(".tcx"):
        return parse_tcx_bytes(data)
    if lower.endswith(".fit"):
        return parse_fit_bytes(data)
    # Фолбэк: попробуем по содержимому.
    head = data[:512].lstrip()
    if head.startswith(b"<"):
        if b"TrainingCenterDatabase" in data[:2048]:
            return parse_tcx_bytes(data)
        return parse_gpx_bytes(data)
    return parse_fit_bytes(data)


def points_to_dicts(points: Iterable[TrackPoint]) -> list[dict]:
    return [{"t": t, "lat": lat, "lon": lon} for (t, lat, lon) in points]


def dicts_to_points(rows: Iterable[dict]) -> list[TrackPoint]:
    out: list[TrackPoint] = []
    for r in rows:
        out.append((r.get("t"), float(r["lat"]), float(r["lon"])))
    return out


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_route_gpx(route: dict) -> str:
    """GPX маршрута для часов/карт: waypoint'ы буёв + rte с порядком.

    route — словарь формата buoy_route.json (points, session.order, start).
    """
    gpx = ET.Element(
        "gpx",
        {
            "xmlns": "http://www.topografix.com/GPX/1/1",
            "version": "1.1",
            "creator": "SwimBuoy backend",
        },
    )
    meta = ET.SubElement(gpx, "metadata")
    ET.SubElement(meta, "name").text = route.get("name", route.get("routeId", "route"))
    ET.SubElement(meta, "time").text = _iso_now()

    points = route.get("points", {})
    start = route.get("start")
    finish = route.get("finish")
    order = (route.get("session") or {}).get("order") or list(points.keys())

    # Waypoint'ы: старт (если есть) + буи + финиш (если есть).
    if start:
        wpt = ET.SubElement(
            gpx, "wpt", {"lat": f"{start['lat']:.6f}", "lon": f"{start['lon']:.6f}"}
        )
        ET.SubElement(wpt, "name").text = start.get("name", "Start")
        ET.SubElement(wpt, "type").text = "Start"

    for pid in order:
        p = points.get(pid)
        if not p:
            continue
        wpt = ET.SubElement(
            gpx, "wpt", {"lat": f"{p['lat']:.6f}", "lon": f"{p['lon']:.6f}"}
        )
        ET.SubElement(wpt, "name").text = p.get("name", pid)
        ET.SubElement(wpt, "type").text = "Buoy"

    if finish:
        wpt = ET.SubElement(
            gpx, "wpt", {"lat": f"{finish['lat']:.6f}", "lon": f"{finish['lon']:.6f}"}
        )
        ET.SubElement(wpt, "name").text = finish.get("name", "Finish")
        ET.SubElement(wpt, "type").text = "Finish"

    # Маршрут (rte) для импорта как курс.
    rte = ET.SubElement(gpx, "rte")
    ET.SubElement(rte, "name").text = route.get("name", route.get("routeId", "route"))
    seq = []
    if start:
        seq.append(("start", start))
    for pid in order:
        if pid in points:
            seq.append((pid, points[pid]))
    if finish:
        seq.append(("finish", finish))
    for pid, p in seq:
        rtept = ET.SubElement(
            rte, "rtept", {"lat": f"{p['lat']:.6f}", "lon": f"{p['lon']:.6f}"}
        )
        ET.SubElement(rtept, "name").text = p.get("name", pid)

    tree = ET.ElementTree(gpx)
    ET.indent(tree, space="  ")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            + ET.tostring(gpx, encoding="unicode"))


def sample_track_line(track: list, max_pts: int = 400) -> list[list[float]]:
    """Downsample track dicts to [[lat, lon], ...] for map overlay."""
    coords = [
        [float(p["lat"]), float(p["lon"])]
        for p in track
        if isinstance(p, dict) and "lat" in p and "lon" in p
    ]
    if len(coords) <= max_pts:
        return coords
    out: list[list[float]] = []
    step = (len(coords) - 1) / (max_pts - 1)
    for i in range(max_pts):
        idx = int(round(i * step))
        out.append(coords[idx])
    return out
