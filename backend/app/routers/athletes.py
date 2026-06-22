"""Управление спортсменами. Создание/список/удаление — только админ (Basic)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Activity, Athlete, Route
from ..schemas import AthleteCreate, AthleteOut
from ..security import get_current_athlete, require_admin
from ..services.athletes import create_athlete

router = APIRouter(prefix="/api/athletes", tags=["athletes"])


@router.post("", response_model=AthleteOut, dependencies=[Depends(require_admin)])
def create(body: AthleteCreate, db: Session = Depends(get_db)) -> Athlete:
    return create_athlete(db, body.name.strip() or "Спортсмен")


@router.get("", dependencies=[Depends(require_admin)])
def list_athletes(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Athlete).order_by(Athlete.created_at.desc())).all()
    out = []
    for a in rows:
        routes = db.scalar(select(func.count()).select_from(Route).where(Route.athlete_id == a.id))
        acts = db.scalar(select(func.count()).select_from(Activity).where(Activity.athlete_id == a.id))
        out.append({
            "id": a.id, "name": a.name, "token": a.token,
            "created_at": a.created_at.isoformat(),
            "routes": routes, "activities": acts,
        })
    return out


@router.delete("/{athlete_id}", dependencies=[Depends(require_admin)])
def delete_athlete(athlete_id: str, db: Session = Depends(get_db)) -> dict:
    athlete = db.get(Athlete, athlete_id)
    if not athlete:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")
    db.delete(athlete)  # каскадом удалит маршруты и тренировки
    db.commit()
    return {"deleted": athlete_id}


@router.get("/me")
def me(athlete: Athlete = Depends(get_current_athlete)) -> dict:
    """Проверка токена спортсмена для входа на сайт."""
    return {"id": athlete.id, "name": athlete.name}
