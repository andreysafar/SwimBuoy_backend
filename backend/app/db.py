"""Подключение к SQLite через SQLAlchemy."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
engine = create_engine(
    f"sqlite:///{_settings.db_path}",
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    from . import models  # noqa: F401 — регистрируем таблицы

    Base.metadata.create_all(engine)
    _migrate(engine)


def _migrate(engine) -> None:
    """Лёгкие миграции для новых колонок в уже созданных таблицах (SQLite)."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "routes" in tables:
        cols = {c["name"] for c in inspector.get_columns("routes")}
        if "finish" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE routes ADD COLUMN finish JSON"))

    if "athletes" in tables:
        cols = {c["name"] for c in inspector.get_columns("athletes")}
        if "telegram_user_id" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE athletes ADD COLUMN telegram_user_id VARCHAR"))
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_athletes_telegram_user_id "
                    "ON athletes (telegram_user_id)"
                ))

    if "activities" in tables:
        cols = {c["name"] for c in inspector.get_columns("activities")}
        with engine.begin() as conn:
            if "sport" not in cols:
                conn.execute(text("ALTER TABLE activities ADD COLUMN sport VARCHAR DEFAULT 'swim'"))
            if "external_id" not in cols:
                conn.execute(text("ALTER TABLE activities ADD COLUMN external_id VARCHAR"))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_activities_external_id "
                    "ON activities (external_id)"
                ))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
