"""Pydantic-схемы запросов/ответов API."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PointIn(BaseModel):
    lat: float
    lon: float
    name: str = ""


class RouteIn(BaseModel):
    name: str
    guidanceMode: str = "point_proximity"
    arrivalRadiusM: int = 20
    dwellSec: int = 4
    orderMode: str = "fixed"
    points: dict[str, PointIn]
    order: Optional[list[str]] = None
    start: Optional[PointIn] = None
    finish: Optional[PointIn] = None
    is_public: bool = False


class AthleteCreate(BaseModel):
    name: str


class AthleteOut(BaseModel):
    id: str
    name: str
    token: str
    created_at: datetime


class TrackPointIn(BaseModel):
    t: Optional[float] = None
    lat: float
    lon: float


class WatchActivityIn(BaseModel):
    """Тело POST с часов: маршрут + буфер GPS-точек."""
    route_id: Optional[str] = None
    name: str = "Тренировка"
    recorded_at: Optional[float] = Field(default=None, description="epoch seconds начала")
    points: list[TrackPointIn]


class ShareToggle(BaseModel):
    is_public: bool


class RegistrationIn(BaseModel):
    name: str
    contact: str = ""
    note: str = ""
