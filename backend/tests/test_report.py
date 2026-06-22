"""Юнит-тесты движка отчёта и парсеров. Запуск: python -m tests.test_report"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.geo import haversine  # noqa: E402
from app.services.report import build_report  # noqa: E402
from app.services.tracks import build_route_gpx, parse_gpx_bytes  # noqa: E402

ROUTE = {
    "routeId": "t1",
    "name": "Тест",
    "arrivalRadiusM": 20,
    "points": {
        "P1": {"lat": 60.0000, "lon": 30.0000, "name": "Старт"},
        "P2": {"lat": 60.0020, "lon": 30.0000, "name": "Буй 2"},
        "P3": {"lat": 60.0040, "lon": 30.0000, "name": "Финиш"},
    },
    "session": {"order": ["P1", "P2", "P3"]},
}


def _line_track() -> list[tuple[float, float, float]]:
    """Прямой трек вдоль маршрута, ~по буям."""
    pts = []
    t = 1_700_000_000
    for i in range(81):
        lat = 60.0000 + 0.00005 * i  # 0..0.0040
        pts.append((float(t + i * 10), lat, 30.0000))
    return pts


def test_build_report_basic() -> None:
    report = build_report(ROUTE, _line_track())
    assert report["ok"], report
    s = report["summary"]
    assert s["buoys_total"] == 3
    assert s["buoys_taken"] == 3, s
    assert s["distance_m"] > 400
    assert len(report["legs"]) == 2
    # Прямой трек -> малое отклонение.
    assert report["summary"]["xte_overall"]["median"] < 10
    # GeoJSON содержит трек, плечи, коридор, буи.
    kinds = {f["properties"]["kind"] for f in report["geojson"]["features"]}
    assert {"track", "leg", "corridor", "buoy"} <= kinds


def test_missed_buoy() -> None:
    # Трек далеко в стороне от P2 -> буй не взят.
    pts = []
    t = 1_700_000_000
    for i in range(81):
        lat = 60.0000 + 0.00005 * i
        lon = 30.0000 + (0.003 if 20 < i < 60 else 0.0)  # большой крюк у P2
        pts.append((float(t + i * 10), lat, lon))
    report = build_report(ROUTE, pts)
    assert report["ok"]
    taken = {b["id"]: b["taken"] for b in report["buoys"]}
    assert taken["P2"] is False, taken


def test_gpx_roundtrip() -> None:
    gpx = build_route_gpx(ROUTE)
    assert "<gpx" in gpx and "rtept" in gpx
    # Трек GPX -> парсинг.
    track_gpx = (
        '<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1">'
        '<trk><trkseg>'
        '<trkpt lat="60.0" lon="30.0"><time>2026-06-14T10:00:00Z</time></trkpt>'
        '<trkpt lat="60.001" lon="30.0"><time>2026-06-14T10:00:10Z</time></trkpt>'
        '</trkseg></trk></gpx>'
    ).encode()
    pts = parse_gpx_bytes(track_gpx)
    assert len(pts) == 2
    assert abs(pts[0][1] - 60.0) < 1e-9
    assert pts[1][0] - pts[0][0] == 10.0


def test_haversine() -> None:
    # ~111 м на 0.001° широты.
    d = haversine(60.0, 30.0, 60.001, 30.0)
    assert 100 < d < 120, d


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK  {name}")
    print("Все тесты пройдены.")
