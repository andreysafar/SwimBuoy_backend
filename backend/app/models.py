"""Модели данных: спортсмен, маршрут, тренировка."""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .db import Base

# Токен спортсмена: ровно 8 символов A-Z a-z 0-9 (вводится на часах как пароль).
TOKEN_LENGTH = 8
_TOKEN_ALPHABET = string.ascii_letters + string.digits


def gen_athlete_token() -> str:
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(TOKEN_LENGTH))


def _uid(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Athlete(Base):
    __tablename__ = "athletes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uid("ath"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    token: Mapped[str] = mapped_column(String, unique=True, index=True,
                                       default=gen_athlete_token)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    routes: Mapped[list["Route"]] = relationship(back_populates="athlete",
                                                  cascade="all, delete-orphan")
    activities: Mapped[list["Activity"]] = relationship(back_populates="athlete",
                                                        cascade="all, delete-orphan")


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uid("rt"))
    athlete_id: Mapped[str] = mapped_column(ForeignKey("athletes.id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)

    guidance_mode: Mapped[str] = mapped_column(String, default="point_proximity")
    arrival_radius_m: Mapped[int] = mapped_column(Integer, default=20)
    dwell_sec: Mapped[int] = mapped_column(Integer, default=4)
    order_mode: Mapped[str] = mapped_column(String, default="fixed")

    points: Mapped[dict] = mapped_column(JSON, default=dict)   # {P1:{lat,lon,name},...}
    order: Mapped[list] = mapped_column(JSON, default=list)    # ["P1","P2",...]
    start: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # {lat,lon,name}
    finish: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {lat,lon,name}

    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    athlete: Mapped[Athlete] = relationship(back_populates="routes")

    def to_buoy_route(self) -> dict:
        """Формат buoy_route.json для часов."""
        data: dict = {
            "routeId": self.id,
            "name": self.name,
            "guidanceMode": self.guidance_mode,
            "arrivalRadiusM": self.arrival_radius_m,
            "dwellSec": self.dwell_sec,
            "points": self.points or {},
            "session": {
                "orderMode": self.order_mode,
                "order": self.order or list((self.points or {}).keys()),
                "activeIndex": 0,
                "taken": [],
            },
        }
        if self.start:
            data["start"] = self.start
        if self.finish:
            data["finish"] = self.finish
        return data

    def to_summary(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "points_count": len(self.points or {}),
            "arrivalRadiusM": self.arrival_radius_m,
            "is_public": self.is_public,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uid("act"))
    athlete_id: Mapped[str] = mapped_column(ForeignKey("athletes.id"), index=True)
    route_id: Mapped[str | None] = mapped_column(ForeignKey("routes.id"), nullable=True, index=True)

    name: Mapped[str] = mapped_column(String, default="Тренировка")
    source: Mapped[str] = mapped_column(String, default="manual")  # watch | manual_gpx | manual_fit | manual_tcx
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    track: Mapped[list] = mapped_column(JSON, default=list)   # [{t,lat,lon},...]
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    stored_file: Mapped[str | None] = mapped_column(String, nullable=True)

    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    share_token: Mapped[str] = mapped_column(String, unique=True, index=True,
                                             default=lambda: secrets.token_urlsafe(12))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    athlete: Mapped[Athlete] = relationship(back_populates="activities")

    def to_summary(self) -> dict:
        s = (self.report or {}).get("summary", {}) if self.report else {}
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "route_id": self.route_id,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
            "created_at": self.created_at.isoformat(),
            "is_public": self.is_public,
            "share_token": self.share_token,
            "distance_m": s.get("distance_m"),
            "duration_s": s.get("duration_s"),
            "buoys_taken": s.get("buoys_taken"),
            "buoys_total": s.get("buoys_total"),
        }


class RegistrationRequest(Base):
    """Заявка на регистрацию спортсмена (обрабатывает админ вручную)."""
    __tablename__ = "registration_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uid("reg"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    contact: Mapped[str] = mapped_column(String, default="")  # email / telegram / телефон
    note: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|approved|rejected
    athlete_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "contact": self.contact,
            "note": self.note,
            "status": self.status,
            "athlete_id": self.athlete_id,
            "created_at": self.created_at.isoformat(),
        }
