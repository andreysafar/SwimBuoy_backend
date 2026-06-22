#!/usr/bin/env python3
"""Заполнение БД: создать спортсмена и импортировать маршруты из ../routes/*.buoy_route.json.

Запуск из каталога backend/:
    python -m scripts.seed --name "Сафар"
Печатает токен спортсмена — его вписывают в настройки watch-app и используют для входа на сайт.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db import SessionLocal, init_db
from app.models import Athlete, Route
from app.services.athletes import create_athlete

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTES_DIR = REPO_ROOT / "routes"


def import_route_file(db, athlete: Athlete, path: Path) -> Route:
    data = json.loads(path.read_text(encoding="utf-8"))
    session = data.get("session", {})
    route = Route(
        athlete_id=athlete.id,
        name=data.get("name", path.stem),
        guidance_mode=data.get("guidanceMode", "point_proximity"),
        arrival_radius_m=int(data.get("arrivalRadiusM", 20)),
        dwell_sec=int(data.get("dwellSec", 4)),
        order_mode=session.get("orderMode", "fixed"),
        points=data.get("points", {}),
        order=session.get("order") or list(data.get("points", {}).keys()),
        start=data.get("start"),
        is_public=True,
    )
    db.add(route)
    return route


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="Demo athlete", help="Имя спортсмена")
    parser.add_argument("--no-routes", action="store_true", help="Не импортировать маршруты")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        athlete = create_athlete(db, args.name)

        imported = []
        if not args.no_routes and ROUTES_DIR.exists():
            for path in sorted(ROUTES_DIR.glob("*.buoy_route.json")):
                route = import_route_file(db, athlete, path)
                imported.append((path.name, route))
            db.flush()

        db.commit()
        print(f"Спортсмен: {athlete.name}")
        print(f"  id:    {athlete.id}")
        print(f"  ТОКЕН: {athlete.token}")
        print("  (впишите токен в настройки watch-app и используйте для входа на сайт)")
        if imported:
            print(f"\nИмпортировано маршрутов: {len(imported)}")
            for name, route in imported:
                print(f"  {route.id}  <-  {name}  ({route.name})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
