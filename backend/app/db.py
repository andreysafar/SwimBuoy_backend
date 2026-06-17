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
    if "routes" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("routes")}
    if "finish" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE routes ADD COLUMN finish JSON"))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
