"""Админ-API: сводный просмотр и администрирование всех данных (Basic auth)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Activity, Athlete, RegistrationRequest, Route
from ..schemas import RouteIn
from ..security import require_admin
from ..services.athletes import create_athlete
from .routes import _apply as _apply_route_body

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])


def _system_owner(db: Session) -> Athlete:
    """Системный владелец маршрутов, создаваемых из админки."""
    owner = db.scalar(select(Athlete).where(Athlete.name == "SwimBuoy"))
    if owner is None:
        owner = create_athlete(db, "SwimBuoy")
    return owner


@router.get("/login")
def login() -> dict:
    """Проверка учётки админа (вызов с Basic-заголовком)."""
    return {"ok": True}


@router.get("/routes")
def all_routes(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Route).order_by(Route.updated_at.desc())).all()
    out = []
    for r in rows:
        out.append({
            **r.to_summary(),
            "athlete_id": r.athlete_id,
            "athlete": r.athlete.name if r.athlete else None,
        })
    return out


@router.post("/routes")
def create_route(body: RouteIn, db: Session = Depends(get_db)) -> dict:
    """Создать маршрут от имени системного владельца (SwimBuoy)."""
    route = Route(athlete_id=_system_owner(db).id)
    _apply_route_body(route, body)
    db.add(route)
    db.commit()
    db.refresh(route)
    return route.to_summary()


@router.get("/routes/{route_id}")
def get_route(route_id: str, db: Session = Depends(get_db)) -> dict:
    """Маршрут в формате buoy_route.json для редактирования в админке."""
    route = db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Маршрут не найден")
    data = route.to_buoy_route()
    data["is_public"] = route.is_public
    data["owner"] = True  # админ может редактировать любой маршрут
    data["athlete"] = route.athlete.name if route.athlete else None
    return data


@router.put("/routes/{route_id}")
def update_route(route_id: str, body: RouteIn, db: Session = Depends(get_db)) -> dict:
    route = db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Маршрут не найден")
    _apply_route_body(route, body)
    db.commit()
    db.refresh(route)
    return route.to_summary()


@router.delete("/routes/{route_id}")
def delete_route(route_id: str, db: Session = Depends(get_db)) -> dict:
    route = db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Маршрут не найден")
    db.delete(route)
    db.commit()
    return {"deleted": route_id}


@router.get("/activities")
def all_activities(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Activity).order_by(Activity.created_at.desc())).all()
    out = []
    for a in rows:
        out.append({
            **a.to_summary(),
            "athlete_id": a.athlete_id,
            "athlete": a.athlete.name if a.athlete else None,
        })
    return out


@router.delete("/activities/{activity_id}")
def delete_activity(activity_id: str, db: Session = Depends(get_db)) -> dict:
    activity = db.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    db.delete(activity)
    db.commit()
    return {"deleted": activity_id}


# --- Заявки на регистрацию ---

@router.get("/registrations")
def list_registrations(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(RegistrationRequest).order_by(RegistrationRequest.created_at.desc())
    ).all()
    return [r.to_dict() for r in rows]


@router.post("/registrations/{req_id}/approve")
def approve_registration(req_id: str, db: Session = Depends(get_db)) -> dict:
    req = db.get(RegistrationRequest, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    athlete = create_athlete(db, req.name)
    req.status = "approved"
    req.athlete_id = athlete.id
    db.commit()
    return {"athlete_id": athlete.id, "name": athlete.name, "token": athlete.token}


@router.post("/registrations/{req_id}/reject")
def reject_registration(req_id: str, db: Session = Depends(get_db)) -> dict:
    req = db.get(RegistrationRequest, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    req.status = "rejected"
    db.commit()
    return {"ok": True}


@router.delete("/registrations/{req_id}")
def delete_registration(req_id: str, db: Session = Depends(get_db)) -> dict:
    req = db.get(RegistrationRequest, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    db.delete(req)
    db.commit()
    return {"deleted": req_id}
