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


# ── NeZhri integration (Strava-report ingest) ──────────────────────────────

SPORTS = {"swim", "run", "ride"}


class NeZhriLinkIn(BaseModel):
    """Bind a NeZhri Telegram user to a SwimBuoy athlete (created if absent)."""
    telegram_user_id: str
    name: str


class NeZhriActivityIn(BaseModel):
    """A Strava report pushed by NeZhri on behalf of a linked Telegram user.

    NeZhri does the upload; the user only chose the sport and whether it's public.
    `track` is optional — when Strava only yields a summary we still record the
    activity with its distance/duration so it shows on the portal.
    """
    telegram_user_id: str
    name: str = "Тренировка"
    sport: str = "swim"  # swim | run | ride
    is_public: bool = False
    external_id: Optional[str] = None  # e.g. "strava:1234567890" — idempotency key
    recorded_at: Optional[float] = Field(default=None, description="epoch seconds")
    track: list[TrackPointIn] = Field(default_factory=list)
    # Summary metrics when there's no GPS track to compute them from.
    distance_m: Optional[float] = None
    duration_s: Optional[float] = None
    # Optional fallback display name for the athlete if a new one is created.
    athlete_name: Optional[str] = None


class NeZhriVisibilityIn(BaseModel):
    """Open/close a specific imported activity after the fact."""
    telegram_user_id: str
    is_public: bool
