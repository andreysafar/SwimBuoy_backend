"""Создание спортсмена с гарантированно уникальным 8-символьным токеном."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Athlete, gen_athlete_token


def create_athlete(db: Session, name: str) -> Athlete:
    token = gen_athlete_token()
    # Маловероятная коллизия 8-символьного токена — перегенерируем.
    while db.scalar(select(Athlete).where(Athlete.token == token)) is not None:
        token = gen_athlete_token()
    athlete = Athlete(name=name, token=token)
    db.add(athlete)
    db.commit()
    db.refresh(athlete)
    return athlete
