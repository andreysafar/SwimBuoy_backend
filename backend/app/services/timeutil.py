"""UTC storage + Moscow display helpers for API responses."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")


def utc_naive_from_epoch(ts: float | None) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)


def api_datetime_iso(dt: datetime | None) -> str | None:
    """Serialize DB datetime as UTC ISO with Z (always interpreted as Moscow on UI)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def format_msk(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(MSK).strftime("%d.%m.%Y %H:%M")
