"""Точка входа FastAPI: API + статический фронтенд SPA."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db, init_db
from .models import Activity, Route
from .routers import activities, admin, athletes, public, routes, watch

settings = get_settings()
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="SwimBuoy", version="0.1.0",
              description="Маршруты буёв, треки заплывов и отчёты для открытой воды.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    if settings.demo_bootstrap:
        from .db import SessionLocal
        from .services.demo import bootstrap_demo
        db = SessionLocal()
        try:
            bootstrap_demo(db)
        except Exception:
            db.rollback()
        finally:
            db.close()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "base_url": settings.base_url}


# Saint Petersburg — default map center for new routes when geo lookup fails.
_DEFAULT_LAT, _DEFAULT_LON = 59.9386, 30.3141


@app.get("/api/geo/hint")
def geo_hint(request: Request) -> dict:
    """Approximate map center from client IP (fallback: Saint Petersburg)."""
    lat, lon = _DEFAULT_LAT, _DEFAULT_LON
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = (forwarded.split(",")[0].strip() if forwarded else None) or (
        request.client.host if request.client else ""
    )
    if ip and ip not in ("127.0.0.1", "::1", "localhost"):
        try:
            with urlopen(
                f"http://ip-api.com/json/{ip}?fields=status,lat,lon",
                timeout=2,
            ) as resp:
                data = json.loads(resp.read().decode())
            if data.get("status") == "success":
                lat, lon = float(data["lat"]), float(data["lon"])
        except (URLError, OSError, ValueError, KeyError, TypeError):
            pass
    return {
        "lat": lat,
        "lon": lon,
        "default": lat == _DEFAULT_LAT and lon == _DEFAULT_LON,
    }


@app.get("/api/map-config")
def map_config() -> dict:
    """Публичные настройки карт (API-ключ Яндекса для тайлов)."""
    return {"yandexApiKey": settings.yandex_maps_api_key}


app.include_router(athletes.router)
app.include_router(admin.router)
app.include_router(routes.router)
app.include_router(activities.router)
app.include_router(watch.router)
app.include_router(public.router)


# --- OG-редиректы для превью в мессенджерах ---

def _he(s: str) -> str:
    """HTML-escape для подстановки в атрибуты."""
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _og_page(title: str, desc: str, url: str, image: str, redirect: str) -> str:
    r = _he(redirect)
    return f"""<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="UTF-8"/>
<title>{title}</title>
<meta property="og:type" content="article"/>
<meta property="og:site_name" content="SwimBuoy"/>
<meta property="og:title" content="{title}"/>
<meta property="og:description" content="{desc}"/>
<meta property="og:url" content="{url}"/>
<meta property="og:image" content="{image}"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{title}"/>
<meta name="twitter:description" content="{desc}"/>
<meta http-equiv="refresh" content="0;url={r}"/>
</head><body>
<script>location.replace({json.dumps(redirect)})</script>
</body></html>"""


@app.get("/s/{token}", response_class=HTMLResponse, include_in_schema=False)
def share_og(token: str, db: Session = Depends(get_db)) -> HTMLResponse:
    """Страница-редирект с Open Graph метатегами для превью в мессенджерах."""
    redirect = f"/#/share/{token}"
    activity = db.scalar(select(Activity).where(Activity.share_token == token))
    if not activity or not activity.is_public:
        return HTMLResponse(f'<meta http-equiv="refresh" content="0;url={_he(redirect)}"/>'
                            f'<script>location.replace({json.dumps(redirect)})</script>')
    athlete = activity.athlete.name if activity.athlete else ""
    title = _he(f"{athlete} — {activity.name}" if athlete else activity.name)
    parts: list[str] = []
    if activity.recorded_at:
        parts.append(activity.recorded_at.strftime("%d.%m.%Y"))
    if activity.report and activity.report.get("summary"):
        s = activity.report["summary"]
        if s.get("distance_m"):
            parts.append(f"{s['distance_m'] / 1000:.2f} км")
        if s.get("buoys_taken") is not None:
            parts.append(f"{s['buoys_taken']}/{s['buoys_total']} буёв")
        if s.get("pace_min_100m"):
            parts.append(f"темп {s['pace_min_100m']} мин/100м")
    base = settings.base_url.rstrip("/")
    desc = _he("Заплыв · " + " · ".join(parts) if parts else "Заплыв на открытой воде")
    return HTMLResponse(_og_page(title, desc, _he(f"{base}/s/{token}"),
                                 _he(f"{base}/assets/og-cover.png"), redirect))


@app.get("/g/{token}", response_class=HTMLResponse, include_in_schema=False)
def group_og(token: str, db: Session = Depends(get_db)) -> HTMLResponse:
    """OG-редирект для совместной тренировки."""
    from .services.groups import group_public_activities
    redirect = f"/#/group/{token}"
    activity = db.scalar(select(Activity).where(Activity.share_token == token))
    if not activity or not activity.is_public:
        return HTMLResponse(f'<meta http-equiv="refresh" content="0;url={_he(redirect)}"/>'
                            f'<script>location.replace({json.dumps(redirect)})</script>')
    members: list[Activity] = []
    for g in group_public_activities(db):
        if any(a.id == activity.id for a in g):
            members = g
            break
    if not members:
        members = [activity]
    names = [a.athlete.name if a.athlete else a.name for a in members]
    title = _he("Совместный заплыв: " + ", ".join(names[:3]) + (" и др." if len(names) > 3 else ""))
    route_name = ""
    for a in members:
        if a.route_id:
            r = db.get(Route, a.route_id)
            if r:
                route_name = r.name
                break
    parts = []
    if activity.recorded_at:
        parts.append(activity.recorded_at.strftime("%d.%m.%Y"))
    parts.append(f"{len(members)} пловцов")
    if route_name:
        parts.append(route_name)
    base = settings.base_url.rstrip("/")
    desc = _he("Совместная тренировка · " + " · ".join(parts))
    return HTMLResponse(_og_page(title, desc, _he(f"{base}/g/{token}"),
                                 _he(f"{base}/assets/og-cover.png"), redirect))


# --- Статический фронтенд (SPA) ---
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    # SPA-фолбэк: любые не-API пути отдают index.html (роутинг через hash).
    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        candidate = STATIC_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
