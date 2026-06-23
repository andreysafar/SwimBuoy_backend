"""Интеграция с ботом NeZhri: приём Strava-отчётов от имени Telegram-пользователя.

NeZhri сам грузит отчёты сюда (привязка по Telegram id). Пользователь в боте
выбирает только вид тренировки (плавание/бег/вело) и открытость. Доступ к этим
эндпоинтам — по общему ключу интеграции (заголовок X-API-Key, см. require_nezhri).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Activity, Athlete
from ..schemas import SPORTS, NeZhriActivityIn, NeZhriLinkIn, NeZhriVisibilityIn
from ..security import require_nezhri
from ..services.activities import create_activity
from ..services.timeutil import utc_naive_from_epoch
from ..services.tracks import points_to_dicts

router = APIRouter(
    prefix="/api/integrations/nezhri",
    tags=["nezhri"],
    dependencies=[Depends(require_nezhri)],
)


def _get_or_create_athlete(db: Session, telegram_user_id: str, name: str) -> Athlete:
    athlete = db.scalar(
        select(Athlete).where(Athlete.telegram_user_id == telegram_user_id)
    )
    if athlete:
        return athlete
    athlete = Athlete(name=name or f"Боец {telegram_user_id}",
                      telegram_user_id=telegram_user_id)
    db.add(athlete)
    db.commit()
    db.refresh(athlete)
    return athlete


def _athlete_or_404(db: Session, telegram_user_id: str) -> Athlete:
    athlete = db.scalar(
        select(Athlete).where(Athlete.telegram_user_id == telegram_user_id)
    )
    if not athlete:
        raise HTTPException(status_code=404, detail="Спортсмен не привязан к Telegram")
    return athlete


@router.post("/link")
def link_athlete(body: NeZhriLinkIn, db: Session = Depends(get_db)) -> dict:
    """Привязать (или создать) спортсмена по Telegram id. Идемпотентно."""
    athlete = _get_or_create_athlete(db, body.telegram_user_id, body.name)
    # Keep the display name fresh on re-link.
    if body.name and athlete.name != body.name:
        athlete.name = body.name
        db.commit()
    return {
        "athlete_id": athlete.id,
        "telegram_user_id": athlete.telegram_user_id,
        "name": athlete.name,
        "token": athlete.token,
    }


@router.post("/activity")
def ingest_activity(body: NeZhriActivityIn, db: Session = Depends(get_db)) -> dict:
    """Принять Strava-отчёт и создать тренировку. Дедуп по external_id."""
    sport = body.sport if body.sport in SPORTS else "swim"
    athlete = _get_or_create_athlete(
        db, body.telegram_user_id, body.athlete_name or body.name
    )

    points = [(p.t, p.lat, p.lon) for p in body.track]
    recorded_at = utc_naive_from_epoch(body.recorded_at)
    report_override = None
    if not points and (body.distance_m is not None or body.duration_s is not None):
        report_override = {
            "summary": {
                "distance_m": body.distance_m,
                "duration_s": body.duration_s,
                "source": "strava_summary",
            }
        }

    # Idempotency: if this external activity is already imported for this
    # athlete, return it instead of duplicating (NeZhri may re-push on edits).
    if body.external_id:
        existing = db.scalar(
            select(Activity).where(
                Activity.athlete_id == athlete.id,
                Activity.external_id == body.external_id,
            )
        )
        if existing:
            # Allow visibility/sport/time/track to be updated on re-push.
            changed = False
            if existing.is_public != body.is_public:
                existing.is_public = body.is_public
                changed = True
            if existing.sport != sport:
                existing.sport = sport
                changed = True
            new_recorded_at = utc_naive_from_epoch(body.recorded_at)
            if new_recorded_at and existing.recorded_at != new_recorded_at:
                existing.recorded_at = new_recorded_at
                changed = True
            if points:
                new_track = points_to_dicts(points)
                if new_track and existing.track != new_track:
                    existing.track = new_track
                    changed = True
            if report_override:
                existing.report = report_override
                changed = True
            if changed:
                db.commit()
                db.refresh(existing)
            settings = get_settings()
            out = existing.to_summary()
            out["share_url"] = f"{settings.base_url}/#/share/{existing.share_token}"
            out["duplicate"] = True
            return out

    activity = create_activity(
        db, athlete, points,
        route=None,
        name=body.name,
        source="strava",
        sport=sport,
        external_id=body.external_id,
        recorded_at=recorded_at,
        is_public=body.is_public,
        report_override=report_override,
    )
    settings = get_settings()
    out = activity.to_summary()
    out["share_url"] = f"{settings.base_url}/#/share/{activity.share_token}"
    out["duplicate"] = False
    return out


@router.get("/activities/{telegram_user_id}")
def list_athlete_activities(telegram_user_id: str, db: Session = Depends(get_db)) -> dict:
    """Список тренировок пользователя — чтобы в боте выбрать, какие открыть/закрыть."""
    athlete = _athlete_or_404(db, telegram_user_id)
    rows = db.scalars(
        select(Activity).where(Activity.athlete_id == athlete.id)
        .order_by(Activity.created_at.desc())
    ).all()
    return {"athlete_id": athlete.id, "activities": [a.to_summary() for a in rows]}


@router.post("/activity/{activity_id}/visibility")
def set_activity_visibility(activity_id: str, body: NeZhriVisibilityIn,
                            db: Session = Depends(get_db)) -> dict:
    """Открыть/закрыть конкретную тренировку (после автозагрузки)."""
    athlete = _athlete_or_404(db, body.telegram_user_id)
    activity = db.get(Activity, activity_id)
    if not activity or activity.athlete_id != athlete.id:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    activity.is_public = body.is_public
    db.commit()
    settings = get_settings()
    return {
        "id": activity.id,
        "is_public": activity.is_public,
        "share_url": f"{settings.base_url}/#/share/{activity.share_token}",
    }
