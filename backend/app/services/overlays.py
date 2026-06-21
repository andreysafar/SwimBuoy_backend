"""Список тренировок для подложки в редакторе маршрута."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Activity, Athlete

OVERLAY_LIST_LIMIT = 150


def _overlay_item(activity: Activity) -> dict:
    s = activity.to_summary()
    return {
        "id": activity.id,
        "name": activity.name,
        "athlete": activity.athlete.name if activity.athlete else None,
        "recorded_at": s.get("recorded_at"),
        "distance_m": s.get("distance_m"),
        "source": activity.source,
    }


def athlete_overlay_candidates(
    db: Session,
    athlete: Athlete,
    route_id: str | None,
) -> dict:
    """Тренировки спортсмена: на маршруте и без привязки к маршруту."""
    on_route: list[dict] = []
    if route_id:
        rows = db.scalars(
            select(Activity)
            .where(Activity.athlete_id == athlete.id, Activity.route_id == route_id)
            .order_by(Activity.recorded_at.desc().nullslast(), Activity.created_at.desc())
            .limit(OVERLAY_LIST_LIMIT)
        ).all()
        on_route = [_overlay_item(a) for a in rows]

    unassigned_rows = db.scalars(
        select(Activity)
        .where(Activity.athlete_id == athlete.id, Activity.route_id.is_(None))
        .order_by(Activity.recorded_at.desc().nullslast(), Activity.created_at.desc())
        .limit(OVERLAY_LIST_LIMIT)
    ).all()
    return {
        "on_route": on_route,
        "unassigned": [_overlay_item(a) for a in unassigned_rows],
        "limit": OVERLAY_LIST_LIMIT,
    }


def admin_overlay_candidates(db: Session, route_id: str | None) -> dict:
    """Все тренировки на маршруте и без маршрута (для админ-редактора)."""
    on_route: list[dict] = []
    if route_id:
        rows = db.scalars(
            select(Activity)
            .where(Activity.route_id == route_id)
            .order_by(Activity.recorded_at.desc().nullslast(), Activity.created_at.desc())
            .limit(OVERLAY_LIST_LIMIT)
        ).all()
        on_route = [_overlay_item(a) for a in rows]

    unassigned_rows = db.scalars(
        select(Activity)
        .where(Activity.route_id.is_(None))
        .order_by(Activity.recorded_at.desc().nullslast(), Activity.created_at.desc())
        .limit(OVERLAY_LIST_LIMIT)
    ).all()
    return {
        "on_route": on_route,
        "unassigned": [_overlay_item(a) for a in unassigned_rows],
        "limit": OVERLAY_LIST_LIMIT,
    }
