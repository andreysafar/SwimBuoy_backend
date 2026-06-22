"""Авторизация: токен спортсмена (Bearer / X-Athlete-Token) и админка (Basic)."""
from __future__ import annotations

import base64
import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Athlete


def _extract_token(authorization: Optional[str], x_athlete_token: Optional[str]) -> Optional[str]:
    if x_athlete_token:
        return x_athlete_token.strip()
    if authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return authorization.strip()
    return None


def get_current_athlete(
    authorization: Optional[str] = Header(default=None),
    x_athlete_token: Optional[str] = Header(default=None, alias="X-Athlete-Token"),
    db: Session = Depends(get_db),
) -> Athlete:
    token = _extract_token(authorization, x_athlete_token)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Нужен токен спортсмена")
    athlete = db.scalar(select(Athlete).where(Athlete.token == token))
    if not athlete:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Неверный токен")
    return athlete


def _check_basic(authorization: Optional[str]) -> bool:
    settings = get_settings()
    if not authorization:
        return False
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "basic":
        return False
    try:
        decoded = base64.b64decode(parts[1]).decode("utf-8")
    except Exception:
        return False
    user, _, password = decoded.partition(":")
    return (secrets.compare_digest(user, settings.admin_user)
            and secrets.compare_digest(password, settings.admin_password))


def require_nezhri(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> None:
    """Trusted server-to-server auth for the NeZhri bot's Strava-report ingest."""
    settings = get_settings()
    if x_api_key and secrets.compare_digest(x_api_key, settings.nezhri_api_key):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Нужен ключ интеграции NeZhri (X-API-Key)",
    )


def require_admin(
    authorization: Optional[str] = Header(default=None),
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> None:
    """Админ-доступ: HTTP Basic (admin:sw1mBu7) или заголовок X-Admin-Token."""
    settings = get_settings()
    if _check_basic(authorization):
        return
    if x_admin_token and secrets.compare_digest(x_admin_token, settings.admin_token):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Нужна авторизация админа",
        headers={"WWW-Authenticate": "Basic"},
    )
