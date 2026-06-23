"""Публичные эндпоинты без авторизации: галерея, share-ссылки, регистрация."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Activity, RegistrationRequest, Route
from ..schemas import RegistrationIn
from ..services.groups import build_group_payload, group_public_activities
from ..services.timeutil import api_datetime_iso
from ..services.tracks import build_route_gpx

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/activities")
def public_activities(limit: int = 60, db: Session = Depends(get_db)) -> list[dict]:
    """Лента публичных тренировок (без токена)."""
    rows = db.scalars(
        select(Activity).where(Activity.is_public.is_(True))
        .order_by(Activity.recorded_at.desc().nullslast(), Activity.created_at.desc())
        .limit(limit)
    ).all()
    out = []
    for a in rows:
        route = db.get(Route, a.route_id) if a.route_id else None
        out.append({
            **a.to_summary(),
            "athlete": a.athlete.name if a.athlete else None,
            "route_name": route.name if route else None,
        })
    return out


@router.get("/routes")
def public_routes(db: Session = Depends(get_db)) -> list[dict]:
    """Публичные маршруты (без токена)."""
    rows = db.scalars(
        select(Route).where(Route.is_public.is_(True)).order_by(Route.updated_at.desc())
    ).all()
    out = []
    for r in rows:
        out.append({**r.to_summary(), "athlete": r.athlete.name if r.athlete else None})
    return out


@router.get("/routes/{route_id}.json")
def public_route_json(route_id: str, db: Session = Depends(get_db)) -> JSONResponse:
    """buoy_route.json публичного маршрута для скачивания."""
    route = db.get(Route, route_id)
    if not route or not route.is_public:
        raise HTTPException(status_code=404, detail="Маршрут недоступен")
    return JSONResponse(
        route.to_buoy_route(),
        headers={"Content-Disposition": f'attachment; filename="{route_id}.json"'},
    )


@router.get("/routes/{route_id}.gpx")
def public_route_gpx(route_id: str, db: Session = Depends(get_db)) -> Response:
    """GPX публичного маршрута (буи + старт/финиш + rte) для часов/карт."""
    route = db.get(Route, route_id)
    if not route or not route.is_public:
        raise HTTPException(status_code=404, detail="Маршрут недоступен")
    gpx = build_route_gpx(route.to_buoy_route())
    return Response(
        content=gpx,
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="{route_id}.gpx"'},
    )


@router.get("/routes/{route_id}")
def public_route(route_id: str, db: Session = Depends(get_db)) -> dict:
    route = db.get(Route, route_id)
    if not route or not route.is_public:
        raise HTTPException(status_code=404, detail="Маршрут недоступен")
    data = route.to_buoy_route()
    data["athlete"] = route.athlete.name if route.athlete else None
    return data


@router.get("/groups")
def public_groups(db: Session = Depends(get_db)) -> list[dict]:
    """Совместные тренировки (2+ пловца, совпадение времени и области ≤2 км)."""
    groups = group_public_activities(db)
    out = []
    for g in groups:
        if len(g) < 2:
            continue
        route = None
        for a in g:
            if a.route_id:
                route = db.get(Route, a.route_id)
                if route:
                    break
        start = g[0].recorded_at
        out.append({
            "group_id": g[0].share_token,
            "route_name": route.name if route else None,
            "recorded_at": api_datetime_iso(start),
            "size": len(g),
            "swimmers": [a.athlete.name if a.athlete else a.name for a in g],
        })
    return out


@router.get("/groups/{token}")
def public_group(token: str, db: Session = Depends(get_db)) -> dict:
    """Данные совместной тренировки по share-токену любого участника."""
    activity = db.scalar(select(Activity).where(Activity.share_token == token))
    if not activity or not activity.is_public:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    for g in group_public_activities(db):
        if any(a.id == activity.id for a in g):
            return build_group_payload(db, g)
    return build_group_payload(db, [activity])


@router.get("/activities/{share_token}")
def public_activity(share_token: str, db: Session = Depends(get_db)) -> dict:
    activity = db.scalar(select(Activity).where(Activity.share_token == share_token))
    if not activity or not activity.is_public:
        raise HTTPException(status_code=404, detail="Отчёт недоступен")
    route_name = None
    if activity.route_id:
        route = db.get(Route, activity.route_id)
        route_name = route.name if route else None
    return {
        "id": activity.id,
        "name": activity.name,
        "athlete": activity.athlete.name,
        "route_name": route_name,
        "recorded_at": api_datetime_iso(activity.recorded_at),
        "report": activity.report,
    }


@router.post("/register")
def register(body: RegistrationIn, db: Session = Depends(get_db)) -> dict:
    """Заявка на регистрацию — админ обработает вручную."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Укажите имя")
    req = RegistrationRequest(
        name=name,
        contact=body.contact.strip(),
        note=body.note.strip(),
    )
    db.add(req)
    db.commit()
    return {"ok": True, "id": req.id}
