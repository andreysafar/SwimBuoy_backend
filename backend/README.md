# SwimBuoy Backend

Бэкенд и сайт портала **swimbuy.iron-siber.ru** для тренировок на открытой воде
с виртуальными буями. Связан с watch-app (Garmin Connect IQ) из этого же репозитория.

## Возможности

- **Публичный лендинг**: маршруты и тренировки открыты и видны **без токена**
  (галерея заплывов и маршрутов на главной).
- **Маршруты буёв**: создание/редактирование на сайте, отдача на часы по сети и
  как **GPX** (буи + `rte`) для импорта в карты/Garmin Connect.
- **Треки заплывов**: ручная загрузка **GPX / TCX / FIT** на сайте **и**
  автоматическая отправка прямо с часов (`POST /api/watch/activities`).
- **Отчёт по тренировке** (обобщение `scripts/analyze_corridor_shuchye.py`):
  отклонение от коридора (cross-track) по плечам, перцентили, дистанция/темп,
  взятые буи, карта (трек + коридор + буи) на сайте + публичная share-ссылка.
- **Совместные тренировки**: заплывы автоматически объединяются, если совпадает
  время и область координат (радиус 2 км). На общей карте видны все треки сразу
  с переключателями пловцов и **онлайн-слайдером ширины коридора**.
- **Заявки на регистрацию**: посетитель оставляет заявку (`/#/register`), админ
  одобряет вручную и выдаёт 8-символьный токен.
- **Веб-админка** (логин `admin` / `sw1mBu7`): заявки, спортсмены, маршруты, тренировки.

## Демо-данные

При первом запуске (флаг `SWIMBUOY_DEMO_BOOTSTRAP=true`, по умолчанию) бэкенд
импортирует пример из `backend/Архив.zip` — заплыв «Щучье 2026-06-14» четырёх
пловцов (Коля, Рома, Сафар, Тюки) на публичном маршруте. Доступно на лендинге
без регистрации. Импорт идемпотентный (повторно не дублируется).

## Стек

FastAPI + SQLAlchemy (SQLite) + статический SPA (vanilla JS + Leaflet). Без внешних БД.

## Быстрый старт (локально)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Импортировать существующие маршруты из ../routes и создать спортсмена:
python -m scripts.seed --name "Сафар"     # напечатает 8-символьный токен

uvicorn app.main:app --reload --port 8000
# Сайт:    http://localhost:8000/
# Админка: http://localhost:8000/#/admin   (admin / sw1mBu7)
```

## Docker

```bash
cd backend
SWIMBUOY_ADMIN_PASSWORD=sw1mBu7 docker compose up -d --build
```

Данные (SQLite + загрузки) — в томе `swimbuoy-data` (`/data` в контейнере).
За reverse-proxy (nginx/Caddy) на `swimbuy.iron-siber.ru` проксируйте на `:8000`.

## Переменные окружения (`SWIMBUOY_*`, см. `.env.example`)

| Переменная | Назначение | По умолчанию |
|------------|------------|--------------|
| `SWIMBUOY_BASE_URL` | Публичный URL (share-ссылки) | `https://swimbuy.iron-siber.ru` |
| `SWIMBUOY_ADMIN_USER` / `SWIMBUOY_ADMIN_PASSWORD` | Логин админки | `admin` / `sw1mBu7` |
| `SWIMBUOY_ADMIN_TOKEN` | Альтернативный доступ к админ-API (`X-Admin-Token`) | `change-me-admin-token` |
| `SWIMBUOY_DATA_DIR` | Каталог БД и загрузок | `data` |
| `SWIMBUOY_CORS_ORIGINS` | CORS origin'ы | `*` |

## Авторизация

- **Спортсмен** — 8-символьный токен (буквы обоих регистров + цифры, без
  спецсимволов; на часах вводится как пароль). Заголовок `X-Athlete-Token`
  (или `Authorization: Bearer <token>`). Выдаётся в админке / `seed.py`.
- **Админ** — HTTP Basic `admin:sw1mBu7` (заголовок `Authorization: Basic …`).
- **Публичные отчёты** — без авторизации по share-токену.

## API (основное)

### Спортсмен (`X-Athlete-Token`)
- `GET  /api/athletes/me` — проверка токена.
- `GET/POST/PUT/DELETE /api/routes[/{id}]` — маршруты.
- `GET  /api/routes/{id}.gpx` / `.json` — экспорт маршрута.
- `POST /api/activities/upload` — загрузка трека (multipart: `file`, `route_id`, `name`).
- `GET  /api/activities[/{id}]` — список / отчёт тренировки.
- `POST /api/activities/{id}/share` — публичная ссылка.
- `POST /api/activities/{id}/recompute?route_id=…` — пересчитать отчёт.

### Часы (`X-Athlete-Token`)
- `GET  /api/watch/routes` — компактный список маршрутов.
- `GET  /api/watch/routes/{id}` — маршрут в формате `buoy_route.json`.
- `POST /api/watch/activities` — `{route_id, name, recorded_at, points:[{t,lat,lon}]}`.

### Админ (Basic)
- `GET  /api/admin/login` — проверка учётки.
- `GET/POST/DELETE /api/athletes[/{id}]` — спортсмены (POST возвращает токен).
- `GET/DELETE /api/admin/routes[/{id}]`, `GET/DELETE /api/admin/activities[/{id}]`.

### Публичное (без авторизации)
- `GET  /api/public/activities` — лента публичных тренировок.
- `GET  /api/public/routes` / `GET /api/public/routes/{id}` — публичные маршруты.
- `GET  /api/public/groups` — совместные тренировки (2+ пловца).
- `GET  /api/public/groups/{token}` — данные совместной тренировки (маршрут,
  плечи, треки пловцов) для общей карты со слайдером коридора.
- `GET  /api/public/activities/{share_token}` — отчёт по share-ссылке.
- `POST /api/public/register` — заявка на регистрацию (`{name, contact, note}`).

### Админ — заявки
- `GET  /api/admin/registrations` — список заявок.
- `POST /api/admin/registrations/{id}/approve` — создать спортсмена (вернёт токен).
- `POST /api/admin/registrations/{id}/reject`, `DELETE /api/admin/registrations/{id}`.

Интерактивная схема: `http://localhost:8000/docs`.

## Связь с watch-app

Настройки приложения на часах (Garmin Connect → SwimBuoy → Settings):
`Portal URL`, `Athlete token`, `Route ID to sync`, `Auto-upload`, `Track sample`.
Часы тянут маршрут по `Route ID` при запуске и шлют буфер GPS-точек заплыва по
завершении. Подробно — `../docs/portal-sync.md`.
