"""Тренировки: ручная загрузка GPX/TCX/FIT, просмотр, отчёт, шаринг."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Activity, Athlete, Route
from ..schemas import ShareToggle
from ..security import get_current_athlete
from ..services.activities import create_activity
from ..services.report import build_report
from ..services.tracks import dicts_to_points, parse_track, sample_track_line

router = APIRouter(prefix="/api/activities", tags=["activities"])


def _owned_activity(activity_id: str, athlete: Athlete, db: Session) -> Activity:
    activity = db.get(Activity, activity_id)
    if not activity or activity.athlete_id != athlete.id:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    return activity


def _route_for(route_id: str | None, athlete: Athlete, db: Session) -> Route | None:
    if not route_id:
        return None
    route = db.get(Route, route_id)
    if not route or (route.athlete_id != athlete.id and not route.is_public):
        raise HTTPException(status_code=404, detail="Маршрут не найден")
    return route


@router.post("/upload")
async def upload_activity(
    file: UploadFile = File(...),
    route_id: str | None = Form(default=None),
    name: str | None = Form(default=None),
    athlete: Athlete = Depends(get_current_athlete),
    db: Session = Depends(get_db),
) -> dict:
    """Ручная загрузка трека: GPX / TCX / FIT."""
    raw = await file.read()
    filename = file.filename or "track"
    try:
        points = parse_track(filename, raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not points:
        raise HTTPException(status_code=400, detail="В файле нет точек трека")

    route = _route_for(route_id, athlete, db)

    # Сохраняем оригинал.
    settings = get_settings()
    stored = settings.uploads_dir / f"{athlete.id}_{datetime.now(timezone.utc):%Y%m%d%H%M%S}_{filename}"
    stored.write_bytes(raw)

    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else "gpx"
    activity = create_activity(
        db, athlete, points,
        route=route,
        name=name or filename,
        source=f"manual_{ext}",
        original_filename=filename,
        stored_file=str(stored.name),
    )
    return activity.to_summary()


@router.get("")
def list_activities(athlete: Athlete = Depends(get_current_athlete),
                    db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(Activity).where(Activity.athlete_id == athlete.id)
        .order_by(Activity.created_at.desc())
    ).all()
    return [a.to_summary() for a in rows]


@router.get("/{activity_id}/track-line")
def activity_track_line(activity_id: str, athlete: Athlete = Depends(get_current_athlete),
                        db: Session = Depends(get_db)) -> dict:
    """Упрощённая линия трека для подложки на карте редактора маршрута."""
    activity = _owned_activity(activity_id, athlete, db)
    if not activity.track:
        raise HTTPException(status_code=404, detail="Трек пуст")
    return {
        "id": activity.id,
        "name": activity.name,
        "line": sample_track_line(activity.track),
    }


@router.get("/{activity_id}")
def get_activity(activity_id: str, athlete: Athlete = Depends(get_current_athlete),
                 db: Session = Depends(get_db)) -> dict:
    activity = _owned_activity(activity_id, athlete, db)
    summary = activity.to_summary()
    summary["report"] = activity.report
    return summary


@router.post("/{activity_id}/recompute")
def recompute(activity_id: str, route_id: str | None = None,
              athlete: Athlete = Depends(get_current_athlete),
              db: Session = Depends(get_db)) -> dict:
    """Пересчитать отчёт (например, привязав трек к маршруту)."""
    activity = _owned_activity(activity_id, athlete, db)
    route = _route_for(route_id or activity.route_id, athlete, db)
    if route is None:
        raise HTTPException(status_code=400, detail="Нужен route_id для отчёта")
    points = dicts_to_points(activity.track)
    activity.route_id = route.id
    activity.report = build_report(route.to_buoy_route(), points)
    db.commit()
    db.refresh(activity)
    return activity.to_summary()


@router.post("/{activity_id}/share")
def set_share(activity_id: str, body: ShareToggle,
              athlete: Athlete = Depends(get_current_athlete),
              db: Session = Depends(get_db)) -> dict:
    activity = _owned_activity(activity_id, athlete, db)
    activity.is_public = body.is_public
    db.commit()
    settings = get_settings()
    return {
        "is_public": activity.is_public,
        "share_token": activity.share_token,
        "share_url": f"{settings.base_url}/#/share/{activity.share_token}",
    }


@router.delete("/{activity_id}")
def delete_activity(activity_id: str, athlete: Athlete = Depends(get_current_athlete),
                    db: Session = Depends(get_db)) -> dict:
    activity = _owned_activity(activity_id, athlete, db)
    db.delete(activity)
    db.commit()
    return {"deleted": activity_id}
