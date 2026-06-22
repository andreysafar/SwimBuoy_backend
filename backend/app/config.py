"""Настройки приложения (читаются из переменных окружения / .env)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SWIMBUOY_", extra="ignore")

    # Базовый публичный URL портала (для share-ссылок и подсказок watch-app).
    base_url: str = "https://swimbuy.iron-siber.ru"

    # Каталог для БД и загруженных файлов.
    data_dir: Path = Path("data")

    # Учётка веб-админки (HTTP Basic). По умолчанию admin / sw1mBu7.
    # В проде переопределить через SWIMBUOY_ADMIN_USER / SWIMBUOY_ADMIN_PASSWORD.
    admin_user: str = "admin"
    admin_password: str = "sw1mBu7"

    # Доп. способ доступа к админ-API: заголовок X-Admin-Token (для скриптов).
    admin_token: str = "change-me-admin-token"

    # Ключ для интеграции с ботом NeZhri: он сам грузит Strava-отчёты сюда от
    # имени пользователя (привязка по Telegram id). Передаётся в X-API-Key.
    # MONETIZATION NOTE: ingest can be metered per telegram_user_id here if
    # SwimBuoy wants to cap free vs. paid sync volume.
    nezhri_api_key: str = "change-me-nezhri-key"

    # CORS: список origin'ов через запятую, или "*".
    cors_origins: str = "*"

    # Авто-импорт демо-тренировки из backend/Архив.zip при первом запуске.
    demo_bootstrap: bool = True

    # API-ключ Яндекс.Карт для тайлов (https://developer.tech.yandex.ru/).
    yandex_maps_api_key: str = ""

    @property
    def db_path(self) -> Path:
        return self.data_dir / "swimbuoy.sqlite3"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def cors_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    return settings
