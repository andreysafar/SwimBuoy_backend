"""Эндпоинты для часов (Garmin Connect IQ).

Часы аутентифицируются токеном спортсмена (заголовок X-Athlete-Token или
Authorization: Bearer). Ответы компактные — экономим память/трафик на часах.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Athlete, Route
from ..schemas import WatchActivityIn
from ..security import get_current_athlete
from ..services.activities import create_activity

router = APIRouter(prefix="/api/watch", tags=["watch"])


@router.get("/routes")
def watch_routes(athlete: Athlete = Depends(get_current_athlete),
                 db: Session = Depends(get_db)) -> dict:
    """Компактный список маршрутов для выбора на часах."""
    rows = db.scalars(
        select(Route)
        .where(or_(Route.athlete_id == athlete.id, Route.is_public.is_(True)))
        .order_by(Route.updated_at.desc())
    ).all()
    return {
        "routes": [
            {"id": r.id, "name": r.name, "buoys": len(r.points or {})}
            for r in rows
        ]
    }


@router.get("/routes/{route_id}")
def watch_route(route_id: str, athlete: Athlete = Depends(get_current_athlete),
                db: Session = Depends(get_db)) -> dict:
    """Полный маршрут в формате buoy_route.json для загрузки на часы."""
    route = db.get(Route, route_id)
    if not route or (route.athlete_id != athlete.id and not route.is_public):
        raise HTTPException(status_code=404, detail="Маршрут не найден")
    return route.to_buoy_route()


@router.post("/activities")
def watch_upload(body: WatchActivityIn,
                 athlete: Athlete = Depends(get_current_athlete),
                 db: Session = Depends(get_db)) -> dict:
    """Часы шлют буфер GPS-точек заплыва -> создаём тренировку и отчёт."""
    if not body.points:
        raise HTTPException(status_code=400, detail="Нет точек трека")

    route: Route | None = None
    if body.route_id:
        route = db.get(Route, body.route_id)
        if route and route.athlete_id != athlete.id and not route.is_public:
            route = None

    points = [(p.t, p.lat, p.lon) for p in body.points]
    recorded_at = (
        datetime.fromtimestamp(body.recorded_at, tz=timezone.utc)
        if body.recorded_at else None
    )
    activity = create_activity(
        db, athlete, points,
        route=route,
        name=body.name,
        source="watch",
        recorded_at=recorded_at,
    )
    return {
        "id": activity.id,
        "share_token": activity.share_token,
        "buoys_taken": (activity.report or {}).get("summary", {}).get("buoys_taken"),
    }
