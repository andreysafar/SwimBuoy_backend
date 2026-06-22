"""Создание тренировки из набора точек: построение отчёта и сохранение."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Activity, Athlete, Route
from .report import build_report
from .tracks import TrackPoint, points_to_dicts


def create_activity(
    db: Session,
    athlete: Athlete,
    points: list[TrackPoint],
    *,
    route: Optional[Route],
    name: str,
    source: str,
    sport: str = "swim",
    external_id: Optional[str] = None,
    recorded_at: Optional[datetime] = None,
    original_filename: Optional[str] = None,
    stored_file: Optional[str] = None,
    is_public: bool = False,
    report_override: Optional[dict] = None,
) -> Activity:
    report = report_override
    if report is None and route is not None:
        report = build_report(route.to_buoy_route(), points)

    if recorded_at is None and points and points[0][0] is not None:
        recorded_at = datetime.fromtimestamp(points[0][0], tz=timezone.utc)

    activity = Activity(
        athlete_id=athlete.id,
        route_id=route.id if route else None,
        name=name,
        source=source,
        sport=sport,
        external_id=external_id,
        recorded_at=recorded_at,
        track=points_to_dicts(points),
        report=report,
        original_filename=original_filename,
        stored_file=stored_file,
        is_public=is_public,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity
