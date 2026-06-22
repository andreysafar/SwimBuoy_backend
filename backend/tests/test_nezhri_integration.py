"""Тесты интеграции с ботом NeZhri: привязка, приём отчётов, открытость."""
from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

API_KEY = "test-nezhri-key"


@pytest.fixture()
def client(monkeypatch):
    # Isolated DB per test run + known integration key.
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("SWIMBUOY_DATA_DIR", tmp)
    monkeypatch.setenv("SWIMBUOY_NEZHRI_API_KEY", API_KEY)
    monkeypatch.setenv("SWIMBUOY_DEMO_BOOTSTRAP", "false")

    # Reset cached settings + engine so the new env is picked up.
    from app import config, db
    config.get_settings.cache_clear()
    settings = config.get_settings()
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    db.engine = create_engine(
        f"sqlite:///{settings.db_path}", connect_args={"check_same_thread": False}, future=True
    )
    db.SessionLocal = sessionmaker(bind=db.engine, autoflush=False,
                                   expire_on_commit=False, future=True)
    db.init_db()

    from app.main import app
    return TestClient(app)


def _h(key=API_KEY):
    return {"X-API-Key": key}


def test_requires_api_key(client):
    r = client.post("/api/integrations/nezhri/link",
                    json={"telegram_user_id": "1", "name": "X"})
    assert r.status_code == 401


def test_link_is_idempotent(client):
    r1 = client.post("/api/integrations/nezhri/link",
                     json={"telegram_user_id": "42", "name": "Коля"}, headers=_h())
    assert r1.status_code == 200
    a1 = r1.json()["athlete_id"]
    r2 = client.post("/api/integrations/nezhri/link",
                     json={"telegram_user_id": "42", "name": "Коля"}, headers=_h())
    assert r2.json()["athlete_id"] == a1


def test_ingest_summary_only_and_dedup(client):
    body = {
        "telegram_user_id": "7",
        "name": "Утренний бег",
        "sport": "run",
        "is_public": True,
        "external_id": "strava:999",
        "distance_m": 5000,
        "duration_s": 1500,
    }
    r1 = client.post("/api/integrations/nezhri/activity", json=body, headers=_h())
    assert r1.status_code == 200, r1.text
    j1 = r1.json()
    assert j1["sport"] == "run"
    assert j1["is_public"] is True
    assert j1["distance_m"] == 5000
    assert j1["duplicate"] is False

    # Re-push same external_id → dedup, no second activity.
    r2 = client.post("/api/integrations/nezhri/activity", json=body, headers=_h())
    assert r2.json()["duplicate"] is True

    lst = client.get("/api/integrations/nezhri/activities/7", headers=_h())
    assert len(lst.json()["activities"]) == 1


def test_ingest_with_track_builds_route_less_report(client):
    """A Strava import with a GPS track gets a renderable track-only report
    (ok=True, track geojson, empty legs) — no "привяжите трек к маршруту"."""
    body = {
        "telegram_user_id": "9",
        "name": "Заплыв",
        "sport": "swim",
        "external_id": "strava:track1",
        "track": [
            {"t": 0, "lat": 59.9, "lon": 30.3},
            {"t": 60, "lat": 59.901, "lon": 30.301},
            {"t": 120, "lat": 59.902, "lon": 30.302},
        ],
    }
    act = client.post("/api/integrations/nezhri/activity",
                      json={**body, "is_public": True}, headers=_h()).json()
    assert act["distance_m"] and act["distance_m"] > 0

    # Public report must be renderable: ok=True, a track geojson feature, no legs.
    pub = client.get(f"/api/public/activities/{act['share_token']}").json()
    report = pub["report"]
    assert report["ok"] is True
    assert report["legs"] == []
    kinds = [f["properties"]["kind"] for f in report["geojson"]["features"]]
    assert "track" in kinds


def test_visibility_toggle(client):
    body = {"telegram_user_id": "8", "name": "Заплыв", "sport": "swim",
            "external_id": "strava:1", "distance_m": 1000, "duration_s": 1200}
    act = client.post("/api/integrations/nezhri/activity", json=body, headers=_h()).json()
    assert act["is_public"] is False
    r = client.post(f"/api/integrations/nezhri/activity/{act['id']}/visibility",
                    json={"telegram_user_id": "8", "is_public": True}, headers=_h())
    assert r.status_code == 200
    assert r.json()["is_public"] is True
