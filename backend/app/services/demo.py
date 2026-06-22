"""Авто-импорт демо-тренировки из backend/Архив.zip (Щучье 2026-06-14).

Идемпотентно: при первом запуске создаёт публичный маршрут Щучьего, спортсменов
по именам файлов в архиве и публичные тренировки с отчётами. Повторные запуски
ничего не делают (проверка по наличию тренировок с source="demo").
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Activity, Athlete, Route
from .activities import create_activity
from .athletes import create_athlete
from .tracks import parse_gpx_bytes

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
ARCHIVE = BACKEND_DIR / "Архив.zip"
ROUTE_JSON = REPO_ROOT / "routes" / "komarovo_shuchye.buoy_route.json"
DEMO_TITLE = "Щучье 2026-06-14"


def _decode_name(zip_name: str) -> str:
    """Имена в zip записаны в UTF-8, но без флага — восстанавливаем из cp437."""
    try:
        return zip_name.encode("cp437").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return zip_name


def bootstrap_demo(db: Session) -> None:
    already = db.scalar(
        select(func.count()).select_from(Activity).where(Activity.source == "demo")
    )
    if already:
        return
    if not ARCHIVE.exists() or not ROUTE_JSON.exists():
        return

    data = json.loads(ROUTE_JSON.read_text(encoding="utf-8"))
    session = data.get("session", {})

    # Владелец публичного маршрута — системный спортсмен.
    owner = db.scalar(select(Athlete).where(Athlete.name == "SwimBuoy"))
    if owner is None:
        owner = create_athlete(db, "SwimBuoy")

    route = Route(
        athlete_id=owner.id,
        name=data.get("name", "Щучье озеро"),
        guidance_mode=data.get("guidanceMode", "point_proximity"),
        arrival_radius_m=int(data.get("arrivalRadiusM", 20)),
        dwell_sec=int(data.get("dwellSec", 4)),
        order_mode=session.get("orderMode", "fixed"),
        points=data.get("points", {}),
        order=session.get("order") or list(data.get("points", {}).keys()),
        start=data.get("start"),
        finish=data.get("finish"),
        is_public=True,
    )
    db.add(route)
    db.commit()

    with zipfile.ZipFile(ARCHIVE) as z:
        for info in z.infolist():
            if info.filename.startswith("__MACOSX") or not info.filename.endswith(".gpx"):
                continue
            swimmer = _decode_name(info.filename)[:-4]
            points = parse_gpx_bytes(z.read(info))
            if not points:
                continue
            athlete = db.scalar(select(Athlete).where(Athlete.name == swimmer))
            if athlete is None:
                athlete = create_athlete(db, swimmer)
            create_activity(
                db, athlete, points,
                route=route,
                name=f"{DEMO_TITLE} · {swimmer}",
                source="demo",
                is_public=True,
            )
