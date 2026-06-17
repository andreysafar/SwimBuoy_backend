"""CRUD маршрутов + экспорт GPX/JSON для часов."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Athlete, Route
from ..schemas import RouteIn
from ..security import get_current_athlete
from ..services.tracks import build_route_gpx

router = APIRouter(prefix="/api/routes", tags=["routes"])


def _apply(route: Route, body: RouteIn) -> None:
    route.name = body.name
    route.guidance_mode = body.guidanceMode
    route.arrival_radius_m = body.arrivalRadiusM
    route.dwell_sec = body.dwellSec
    route.order_mode = body.orderMode
    route.points = {pid: p.model_dump() for pid, p in body.points.items()}
    route.order = body.order or list(body.points.keys())
    route.start = body.start.model_dump() if body.start else None
    route.finish = body.finish.model_dump() if body.finish else None
    route.is_public = body.is_public


def _get_owned(route_id: str, athlete: Athlete, db: Session) -> Route:
    route = db.get(Route, route_id)
    if not route or route.athlete_id != athlete.id:
        raise HTTPException(status_code=404, detail="Маршрут не найден")
    return route


def _get_readable(route_id: str, db: Session, athlete: Athlete | None) -> Route:
    route = db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Маршрут не найден")
    if not route.is_public and (athlete is None or route.athlete_id != athlete.id):
        raise HTTPException(status_code=403, detail="Маршрут закрыт")
    return route


@router.post("")
def create_route(body: RouteIn, athlete: Athlete = Depends(get_current_athlete),
                 db: Session = Depends(get_db)) -> dict:
    route = Route(athlete_id=athlete.id)
    _apply(route, body)
    db.add(route)
    db.commit()
    db.refresh(route)
    return route.to_summary()


@router.get("")
def list_routes(include_public: bool = True,
                athlete: Athlete = Depends(get_current_athlete),
                db: Session = Depends(get_db)) -> list[dict]:
    cond = Route.athlete_id == athlete.id
    if include_public:
        cond = or_(cond, Route.is_public.is_(True))
    rows = db.scalars(select(Route).where(cond).order_by(Route.updated_at.desc())).all()
    return [r.to_summary() for r in rows]


@router.get("/{route_id}.json")
def route_json(route_id: str, athlete: Athlete = Depends(get_current_athlete),
               db: Session = Depends(get_db)) -> JSONResponse:
    """buoy_route.json для скачивания/часов."""
    route = _get_readable(route_id, db, athlete)
    return JSONResponse(route.to_buoy_route())


@router.get("/{route_id}.gpx")
def route_gpx(route_id: str, athlete: Athlete = Depends(get_current_athlete),
              db: Session = Depends(get_db)) -> Response:
    """GPX маршрута (буи + rte) для импорта на часы / в карты."""
    route = _get_readable(route_id, db, athlete)
    gpx = build_route_gpx(route.to_buoy_route())
    return Response(
        content=gpx,
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="{route_id}.gpx"'},
    )


@router.get("/{route_id}")
def get_route(route_id: str, athlete: Athlete = Depends(get_current_athlete),
              db: Session = Depends(get_db)) -> dict:
    route = _get_readable(route_id, db, athlete)
    data = route.to_buoy_route()
    data["is_public"] = route.is_public
    data["owner"] = route.athlete_id == athlete.id
    return data


@router.put("/{route_id}")
def update_route(route_id: str, body: RouteIn,
                 athlete: Athlete = Depends(get_current_athlete),
                 db: Session = Depends(get_db)) -> dict:
    route = _get_owned(route_id, athlete, db)
    _apply(route, body)
    db.commit()
    db.refresh(route)
    return route.to_summary()


@router.delete("/{route_id}")
def delete_route(route_id: str, athlete: Athlete = Depends(get_current_athlete),
                 db: Session = Depends(get_db)) -> dict:
    route = _get_owned(route_id, athlete, db)
    db.delete(route)
    db.commit()
    return {"deleted": route_id}
