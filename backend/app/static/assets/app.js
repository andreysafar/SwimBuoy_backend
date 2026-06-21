"use strict";

// ---------- Состояние / API ----------
const TOKEN_KEY = "swimbuoy_token";
const getToken = () => localStorage.getItem(TOKEN_KEY) || "";
const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
const clearToken = () => localStorage.removeItem(TOKEN_KEY);

async function api(path, opts = {}) {
  const headers = opts.headers || {};
  if (getToken()) headers["X-Athlete-Token"] = getToken();
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.json);
    delete opts.json;
  }
  const res = await fetch(path, { ...opts, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

// ---------- Админ (HTTP Basic) ----------
const ADMIN_KEY = "swimbuoy_admin";
const getAdmin = () => localStorage.getItem(ADMIN_KEY) || "";
const setAdmin = (b64) => localStorage.setItem(ADMIN_KEY, b64);
const clearAdmin = () => localStorage.removeItem(ADMIN_KEY);

async function adminApi(path, opts = {}) {
  const headers = opts.headers || {};
  headers["Authorization"] = "Basic " + getAdmin();
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.json);
    delete opts.json;
  }
  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401) { clearAdmin(); throw new Error("Нужен вход админа"); }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

const app = document.getElementById("app");
const nav = document.getElementById("nav");

function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2600);
}

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function fmtDist(m) {
  if (m == null) return "—";
  return m >= 1000 ? (m / 1000).toFixed(2) + " км" : Math.round(m) + " м";
}
function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const p1 = lat1 * Math.PI / 180, p2 = lat2 * Math.PI / 180;
  const dphi = (lat2 - lat1) * Math.PI / 180, dlmb = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dphi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dlmb / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
function fmtDur(s) {
  if (s == null) return "—";
  const m = Math.floor(s / 60), sec = Math.round(s % 60);
  return m + ":" + String(sec).padStart(2, "0");
}
function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short" });
}
function routeListMeta(r) {
  const parts = [`${r.points_count} буёв`];
  if (r.distance_m > 0) parts.push(fmtDist(r.distance_m));
  parts.push(`радиус ${r.arrivalRadiusM} м`);
  return parts.join(" · ");
}
function routeToLegData(route) {
  return {
    start: route.start || null,
    finish: route.finish || null,
    order: (route.session && route.session.order) || Object.keys(route.points || {}),
    points: route.points || {},
  };
}

// ---------- Роутер ----------
function navView() {
  if (getToken()) {
    nav.innerHTML = `<a href="#/">Тренировки</a><a href="#/routes">Маршруты</a>
      <a href="#/upload">Загрузить</a><a href="#/admin">Админ</a><a href="#" id="logout">Выйти</a>`;
    nav.querySelector("#logout").onclick = (e) => { e.preventDefault(); clearToken(); location.hash = "#/"; };
  } else {
    nav.innerHTML = `<a href="#/">Главная</a><a href="#/register">Регистрация</a>
      <a href="#/login">Войти</a><a href="#/admin">Админ</a>`;
  }
}

window.addEventListener("hashchange", route);
window.addEventListener("load", route);

async function route() {
  navView();
  const hash = location.hash || "#/";
  const parts = hash.slice(2).split("/"); // убираем "#/"

  // Публичные экраны — без токена спортсмена.
  if (parts[0] === "share" && parts[1]) return viewShare(parts[1]);
  if (parts[0] === "group" && parts[1]) return viewGroup(parts[1]);
  if (parts[0] === "register") return viewRegister();
  if (parts[0] === "r" && parts[1]) return viewPublicRoute(parts[1]);
  if (parts[0] === "login") return viewLogin();

  // Админка — отдельная авторизация (Basic).
  if (parts[0] === "admin") return viewAdmin(parts[1], parts[2], parts[3]);

  if (!getToken()) return viewLanding();

  try {
    if (parts[0] === "" ) return viewDashboard();
    if (parts[0] === "routes" && parts[1] === "new") return viewRouteEdit(null);
    if (parts[0] === "routes" && parts[1] && parts[2] === "edit") return viewRouteEdit(parts[1]);
    if (parts[0] === "routes" && parts[1]) return viewRoute(parts[1]);
    if (parts[0] === "routes") return viewRoutes();
    if (parts[0] === "upload") return viewUpload();
    if (parts[0] === "activities" && parts[1]) return viewActivity(parts[1]);
    viewDashboard();
  } catch (e) {
    app.innerHTML = `<div class="card"><h2>Ошибка</h2><p class="muted">${esc(e.message)}</p></div>`;
  }
}

// ---------- Вход ----------
function viewLogin() {
  app.innerHTML = `
    <div class="center-panel card">
      <h1>Вход</h1>
      <p class="subtitle">Введите токен спортсмена. Его выдаёт администратор
        (или возьмите из вывода <code>seed.py</code>).</p>
      <label>Токен</label>
      <input id="token" placeholder="напр. xQ8…" autofocus />
      <div class="btn-row"><button class="btn" id="go">Войти</button></div>
    </div>`;
  const submit = async () => {
    const t = app.querySelector("#token").value.trim();
    if (!t) return;
    setToken(t);
    try {
      await api("/api/athletes/me");
      location.hash = "#/";
    } catch (e) {
      clearToken();
      toast("Неверный токен");
    }
  };
  app.querySelector("#go").onclick = submit;
  app.querySelector("#token").onkeydown = (e) => { if (e.key === "Enter") submit(); };
}

// ---------- Публичный лендинг ----------
function activityCardPublic(a) {
  return `<a class="card clickable" style="display:block" href="#/share/${a.share_token}">
      <div style="display:flex;justify-content:space-between;gap:8px">
        <strong>${esc(a.athlete || a.name)}</strong>
        <span class="muted" style="font-size:12px">${fmtDate(a.recorded_at || a.created_at)}</span>
      </div>
      <div class="muted" style="font-size:13px;margin-top:4px">${esc(a.route_name || a.name)}</div>
      <div style="margin-top:12px;display:flex;gap:18px">
        <div><div style="font-weight:700">${fmtDist(a.distance_m)}</div><div class="muted" style="font-size:12px">дистанция</div></div>
        <div><div style="font-weight:700">${fmtDur(a.duration_s)}</div><div class="muted" style="font-size:12px">время</div></div>
        <div><div style="font-weight:700">${a.buoys_taken ?? "—"}/${a.buoys_total ?? "—"}</div><div class="muted" style="font-size:12px">буи</div></div>
      </div></a>`;
}

async function viewLanding() {
  app.innerHTML = `
    <section class="hero">
      <h1 class="hero-title">Плавай по виртуальным буям.<br/>Разбирай каждый заплыв.</h1>
      <p class="hero-sub">SwimBuoy — маршруты буёв для часов Garmin, треки заплывов
        и отчёты по коридору на открытой воде. Маршруты и тренировки открыты —
        смотрите без регистрации.</p>
      <div class="btn-row">
        <a class="btn" href="#/register">Запросить аккаунт</a>
        <a class="btn secondary" href="#/login">У меня есть токен</a>
      </div>
    </section>
    <div id="groups-wrap"></div>
    <h2>Последние заплывы</h2>
    <div id="acts" class="grid"><div class="empty">Загрузка…</div></div>
    <h2>Маршруты</h2>
    <div id="routes" class="grid"><div class="empty">Загрузка…</div></div>`;

  try {
    const groups = await fetch("/api/public/groups").then((r) => r.json());
    if (groups.length) {
      app.querySelector("#groups-wrap").innerHTML =
        `<h2>Совместные тренировки</h2><div id="groups" class="grid"></div>`;
      app.querySelector("#groups").innerHTML = groups.map((g) => `
        <a class="card clickable" style="display:block" href="#/group/${g.group_id}">
          <div style="display:flex;justify-content:space-between;gap:8px">
            <strong>${g.size} пловцов вместе</strong>
            <span class="muted" style="font-size:12px">${fmtDate(g.recorded_at)}</span>
          </div>
          <div class="muted" style="font-size:13px;margin-top:6px">${esc(g.route_name || "")}</div>
          <div style="font-size:13px;margin-top:8px">${g.swimmers.map(esc).join(" · ")}</div>
        </a>`).join("");
    }
  } catch (e) {}

  try {
    const acts = await fetch("/api/public/activities").then((r) => r.json());
    const ae = app.querySelector("#acts");
    ae.innerHTML = acts.length
      ? acts.map(activityCardPublic).join("")
      : `<div class="empty">Пока нет публичных заплывов.</div>`;
  } catch (e) {}

  try {
    const routes = await fetch("/api/public/routes").then((r) => r.json());
    const re = app.querySelector("#routes");
    re.innerHTML = routes.length ? routes.map((r) => `
      <a class="card clickable" style="display:block" href="#/r/${r.id}">
        <strong>${esc(r.name)}</strong>
        <div class="muted" style="font-size:13px;margin-top:8px">${routeListMeta(r)}</div>
        <div class="muted" style="font-size:12px;margin-top:6px">${esc(r.athlete || "")}</div>
      </a>`).join("") : `<div class="empty">Маршрутов пока нет.</div>`;
  } catch (e) {}
}

// ---------- Регистрация (заявка) ----------
function viewRegister() {
  app.innerHTML = `
    <div class="center-panel card">
      <h1>Запрос аккаунта</h1>
      <p class="subtitle">Оставьте заявку — администратор создаст аккаунт и выдаст
        8-символьный токен для входа и часов.</p>
      <label>Имя (как показывать в заплывах)</label>
      <input id="name" placeholder="Например, Сафар" autofocus />
      <label>Контакт (email / telegram)</label>
      <input id="contact" placeholder="по нему пришлём токен" />
      <label>Комментарий (необязательно)</label>
      <textarea id="note" rows="3" placeholder="клуб, устройство, и т.п."></textarea>
      <div class="btn-row"><button class="btn" id="go">Отправить заявку</button>
        <a class="btn ghost" href="#/">На главную</a></div>
    </div>`;
  app.querySelector("#go").onclick = async () => {
    const name = app.querySelector("#name").value.trim();
    if (!name) return toast("Укажите имя");
    const body = {
      name,
      contact: app.querySelector("#contact").value.trim(),
      note: app.querySelector("#note").value.trim(),
    };
    try {
      await api("/api/public/register", { method: "POST", json: body });
      app.innerHTML = `<div class="center-panel card"><h1>Заявка отправлена ✅</h1>
        <p class="subtitle">Спасибо! Администратор свяжется с вами и выдаст токен.</p>
        <div class="btn-row"><a class="btn" href="#/">На главную</a></div></div>`;
    } catch (e) { toast(e.message); }
  };
}

// ---------- Карта маршрута (общая) ----------
function renderRouteMap(elId, route) {
  const order = (route.session && route.session.order) || Object.keys(route.points || {});
  const legs = buildRouteLegs(routeToLegData(route));
  const map = L.map(elId);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);
  const pts = [];
  if (route.start) {
    L.marker([route.start.lat, route.start.lon]).addTo(map).bindPopup("Старт");
    pts.push([route.start.lat, route.start.lon]);
  }
  order.forEach((pid, i) => {
    const p = route.points[pid]; if (!p) return;
    L.circleMarker([p.lat, p.lon], { radius: 8, color: "#fbbf24", fillColor: "#fbbf24", fillOpacity: .9 })
      .addTo(map).bindPopup(`${i + 1}. ${esc(p.name || pid)}`);
    pts.push([p.lat, p.lon]);
  });
  if (route.finish) {
    L.circleMarker([route.finish.lat, route.finish.lon],
      { radius: 7, color: "#34d399", fillColor: "#34d399", fillOpacity: .9 })
      .addTo(map).bindPopup("Финиш");
    pts.push([route.finish.lat, route.finish.lon]);
  }
  legs.forEach((leg) => {
    L.polygon(_legPolygon(leg.a, leg.b, leg.corridor_half_m), {
      color: "#2dd4bf", weight: 1, opacity: .5,
      fillColor: "#2dd4bf", fillOpacity: .22,
    }).addTo(map);
    L.polyline([leg.a, leg.b], { color: "#2dd4bf", weight: 3, opacity: .85 })
      .addTo(map).bindTooltip(`${esc(leg.fromLabel)} → ${esc(leg.toLabel)}: ${fmtDist(leg.length_m)}`);
  });
  if (!legs.length && pts.length >= 2) {
    L.polyline(pts, { color: "#2dd4bf", weight: 2, dashArray: "6 6" }).addTo(map);
  }
  if (pts.length) map.fitBounds(pts, { padding: [40, 40] });
  return { order, legs };
}

function routePointsTable(route, order) {
  return `<table><thead><tr><th>#</th><th>ID</th><th>Имя</th><th>Координаты</th></tr></thead>
    <tbody>${order.map((pid, i) => {
      const p = route.points[pid]; if (!p) return "";
      return `<tr><td>${i + 1}</td><td>${esc(pid)}</td><td>${esc(p.name || "")}</td>
        <td class="muted">${p.lat.toFixed(6)}, ${p.lon.toFixed(6)}</td></tr>`;
    }).join("")}</tbody></table>`;
}

// ---------- Публичный просмотр маршрута ----------
async function viewPublicRoute(id) {
  try {
    const r = await fetch(`/api/public/routes/${id}`).then((res) => {
      if (!res.ok) throw new Error("Маршрут недоступен");
      return res.json();
    });
    const order = (r.session && r.session.order) || Object.keys(r.points);
    const legs = buildRouteLegs(routeToLegData(r));
    const dist = r.distance_m || legs.reduce((s, l) => s + l.length_m, 0);
    app.innerHTML = `
      <h1>${esc(r.name)}</h1>
      <p class="subtitle">${order.length} буёв · ${fmtDist(dist)} · радиус ${r.arrivalRadiusM} м${r.athlete ? " · " + esc(r.athlete) : ""}</p>
      <div class="btn-row"><a class="btn" href="/api/public/routes/${id}.gpx">⬇ GPX (на часы / карты)</a>
        <a class="btn secondary" href="/api/public/routes/${id}.json">⬇ JSON</a>
        <a class="btn ghost" href="#/">На главную</a></div>
      <div id="map" class="map"></div>
      <div class="legend"><span class="l-buoy">буй</span><span class="l-corridor">коридор</span></div>
      <div id="rstats"></div>
      <h2>Точки</h2><div id="tbl"></div>`;
    renderRouteMap("map", r);
    renderRouteLegStats(app.querySelector("#rstats"), legs);
    app.querySelector("#tbl").innerHTML = routePointsTable(r, order);
  } catch (e) {
    app.innerHTML = `<div class="card center-panel"><h2>Маршрут недоступен</h2>
      <p class="muted">${esc(e.message)}</p></div>`;
  }
}

// ---------- Совместная тренировка ----------
const SWIMMER_COLORS = ["#38bdf8", "#f472b6", "#a3e635", "#fbbf24", "#c084fc", "#fb7185", "#22d3ee", "#facc15"];

function _destPoint(lat, lon, brgDeg, distM) {
  const R = 6371000, br = brgDeg * Math.PI / 180, p1 = lat * Math.PI / 180, l1 = lon * Math.PI / 180;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(distM / R) + Math.cos(p1) * Math.sin(distM / R) * Math.cos(br));
  const l2 = l1 + Math.atan2(Math.sin(br) * Math.sin(distM / R) * Math.cos(p1),
    Math.cos(distM / R) - Math.sin(p1) * Math.sin(p2));
  return [p2 * 180 / Math.PI, l2 * 180 / Math.PI];
}
function _bearingDeg(a, b) {
  const p1 = a[0] * Math.PI / 180, p2 = b[0] * Math.PI / 180, dl = (b[1] - a[1]) * Math.PI / 180;
  const y = Math.sin(dl) * Math.cos(p2);
  const x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}
function _legPolygon(a, b, half) {
  const brg = _bearingDeg(a, b);
  const left = (brg + 270) % 360, right = (brg + 90) % 360;
  return [
    _destPoint(a[0], a[1], left, half), _destPoint(b[0], b[1], left, half),
    _destPoint(b[0], b[1], right, half), _destPoint(a[0], a[1], right, half),
  ];
}

function legHalfWidthDefault(legLenM) {
  return Math.round(Math.max(20, Math.min(95, legLenM * 0.11 + 5)));
}

function buildRouteLegs(data) {
  const seq = [];
  if (data.start) {
    seq.push({ id: "start", label: data.start.name || "Старт", pt: data.start });
  }
  (data.order || []).forEach((pid) => {
    const p = data.points && data.points[pid];
    if (p) seq.push({ id: pid, label: p.name || pid, pt: p });
  });
  if (data.finish) {
    seq.push({ id: "finish", label: data.finish.name || "Финиш", pt: data.finish });
  }
  const legs = [];
  for (let i = 0; i < seq.length - 1; i++) {
    const a = seq[i], b = seq[i + 1];
    const aPt = [a.pt.lat, a.pt.lon], bPt = [b.pt.lat, b.pt.lon];
    const length_m = haversine(aPt[0], aPt[1], bPt[0], bPt[1]);
    legs.push({
      id: `${a.id}->${b.id}`,
      from: a.id, to: b.id,
      fromLabel: a.label, toLabel: b.label,
      a: aPt, b: bPt,
      length_m,
      corridor_half_m: legHalfWidthDefault(length_m),
    });
  }
  return legs;
}

function renderRouteLegStats(el, legs) {
  if (!el) return;
  if (!legs.length) {
    el.innerHTML = `<p class="muted">Задайте старт, буи и финиш — появятся плечи, коридор и дистанции.</p>`;
    return;
  }
  const total = legs.reduce((s, l) => s + l.length_m, 0);
  el.innerHTML = `
    <div class="stats">
      <div class="stat"><div class="v">${fmtDist(total)}</div><div class="k">итого по хордам</div></div>
      <div class="stat"><div class="v">${legs.length}</div><div class="k">плеч</div></div>
    </div>
    <div class="table-wrap" style="margin-top:12px">
      <table><thead><tr><th>Плечо</th><th>Дистанция</th><th>Коридор</th></tr></thead>
      <tbody>${legs.map((l) => `<tr>
        <td>${esc(l.fromLabel)} → ${esc(l.toLabel)}</td>
        <td>${fmtDist(l.length_m)}</td>
        <td class="muted">±${l.corridor_half_m} м</td>
      </tr>`).join("")}</tbody></table>
    </div>`;
}

function overlayItemMeta(a) {
  const bits = [];
  if (a.athlete) bits.push(a.athlete);
  if (a.recorded_at) bits.push(fmtDate(a.recorded_at));
  if (a.distance_m) bits.push(fmtDist(a.distance_m));
  return bits.join(" · ");
}

function mountOverlayGroup(title, items, container, selected, onToggle, filter) {
  const q = (filter || "").trim().toLowerCase();
  const filtered = items.filter((a) => {
    if (!q) return true;
    return [a.name, a.athlete, a.source, a.id].join(" ").toLowerCase().includes(q);
  });
  const group = document.createElement("div");
  group.className = "overlay-group";
  const countLabel = filtered.length === items.length
    ? String(items.length)
    : `${filtered.length} / ${items.length}`;
  group.innerHTML = `<h3>${esc(title)} (${countLabel})</h3>`;
  const list = document.createElement("div");
  list.className = "overlay-list";
  if (!filtered.length) {
    list.innerHTML = `<div class="overlay-empty">${items.length ? "Ничего не найдено" : "Пусто"}</div>`;
  } else {
    list.innerHTML = filtered.map((a) => `
      <label class="overlay-item">
        <input type="checkbox" data-oid="${a.id}" ${selected.has(a.id) ? "checked" : ""} />
        <div class="meta">
          <div class="title">${esc(a.name)}</div>
          <div class="sub">${esc(overlayItemMeta(a))}</div>
        </div>
      </label>`).join("");
  }
  group.appendChild(list);
  container.appendChild(group);
  list.querySelectorAll("input[data-oid]").forEach((cb) => {
    cb.onchange = () => onToggle(cb.dataset.oid, cb.checked);
  });
}

async function viewGroup(token) {
  let d;
  try {
    d = await fetch(`/api/public/groups/${token}`).then((r) => {
      if (!r.ok) throw new Error("Тренировка не найдена");
      return r.json();
    });
  } catch (e) {
    app.innerHTML = `<div class="card center-panel"><h2>Недоступно</h2>
      <p class="muted">${esc(e.message)}</p></div>`;
    return;
  }
  const route = d.route;
  const initialHalf = route ? (route.arrivalRadiusM || 20) : 20;

  app.innerHTML = `
    <h1>Совместная тренировка</h1>
    <p class="subtitle">${route ? esc(route.name) + " · " : ""}${fmtDate(d.recorded_at)} · ${d.swimmers.length} пловцов</p>
    <div class="btn-row" style="margin-bottom:4px">
      <button class="btn secondary small" id="copyGroup">🔗 Скопировать ссылку</button>
    </div>
    <div class="card" style="margin-bottom:14px">
      <div class="row" style="align-items:center">
        <div style="flex:1 1 260px">
          <label style="margin-top:0">Ширина коридора: <b id="halfval">±${initialHalf} м</b></label>
          <input id="half" type="range" min="5" max="120" step="1" value="${initialHalf}" />
        </div>
        <div style="flex:0 0 auto"><label style="margin-top:0">
          <input type="checkbox" id="corrToggle" checked style="width:auto" /> показывать коридор</label>
        </div>
      </div>
      <div id="toggles" style="display:flex;gap:14px;flex-wrap:wrap;margin-top:10px"></div>
    </div>
    <div id="gmap" class="map"></div>
    <h2>Пловцы</h2>
    <div class="table-wrap"><table><thead><tr><th>Пловец</th><th>Дист.</th><th>Время</th><th>Буи</th><th>XTE p95</th><th></th></tr></thead>
      <tbody id="gtbl"></tbody></table></div>`;

  const map = L.map("gmap");
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);
  const bounds = [];

  // Плечи + буи маршрута.
  const corridorLayer = L.layerGroup().addTo(map);
  if (route) {
    route.legs.forEach((l) => {
      L.polyline([l.a, l.b], { color: "#2dd4bf", weight: 1.5, dashArray: "5 6", opacity: .7 }).addTo(map);
    });
    if (route.start) L.marker([route.start.lat, route.start.lon]).addTo(map).bindPopup("Старт");
    const order = route.order || Object.keys(route.points);
    order.forEach((pid, i) => {
      const p = route.points[pid]; if (!p) return;
      L.circleMarker([p.lat, p.lon], { radius: 8, color: "#fbbf24", fillColor: "#fbbf24", fillOpacity: .9 })
        .addTo(map).bindPopup(`${i + 1}. ${esc(p.name || pid)}`);
      bounds.push([p.lat, p.lon]);
    });
    if (route.finish) {
      L.circleMarker([route.finish.lat, route.finish.lon],
        { radius: 7, color: "#34d399", fillColor: "#34d399", fillOpacity: .9 })
        .addTo(map).bindPopup("Финиш");
      bounds.push([route.finish.lat, route.finish.lon]);
    }
  }

  function drawCorridor(half) {
    corridorLayer.clearLayers();
    if (!route || !app.querySelector("#corrToggle").checked) return;
    route.legs.forEach((l) => {
      L.polygon(_legPolygon(l.a, l.b, half),
        { color: "#2dd4bf", weight: 1, opacity: .5, fillColor: "#2dd4bf", fillOpacity: .22 }).addTo(corridorLayer);
    });
  }

  // Треки пловцов.
  const trackLayers = {};
  d.swimmers.forEach((s, i) => {
    const color = SWIMMER_COLORS[i % SWIMMER_COLORS.length];
    const line = L.polyline(s.track, { color, weight: 3, opacity: .9 }).addTo(map);
    trackLayers[s.id] = line;
    s.track.forEach((p) => bounds.push(p));
  });

  if (bounds.length) map.fitBounds(bounds, { padding: [40, 40] });
  drawCorridor(initialHalf);

  // Переключатели пловцов.
  app.querySelector("#toggles").innerHTML = d.swimmers.map((s, i) => {
    const color = SWIMMER_COLORS[i % SWIMMER_COLORS.length];
    return `<label style="margin:0;color:var(--text)">
      <input type="checkbox" data-sw="${s.id}" checked style="width:auto" />
      <span style="display:inline-block;width:11px;height:11px;border-radius:3px;background:${color};vertical-align:-1px;margin:0 4px"></span>
      ${esc(s.name)}</label>`;
  }).join("");
  app.querySelectorAll("input[data-sw]").forEach((cb) => {
    cb.onchange = () => {
      const layer = trackLayers[cb.dataset.sw];
      if (cb.checked) layer.addTo(map); else map.removeLayer(layer);
    };
  });

  // Слайдер коридора.
  const half = app.querySelector("#half");
  half.oninput = () => {
    app.querySelector("#halfval").textContent = `±${half.value} м`;
    drawCorridor(parseFloat(half.value));
  };
  app.querySelector("#corrToggle").onchange = () => drawCorridor(parseFloat(half.value));

  app.querySelector("#copyGroup").onclick = () => {
    const url = location.origin + "/g/" + token;
    try { navigator.clipboard.writeText(url); } catch (e) {}
    toast("Ссылка скопирована: " + url);
  };

  // Таблица.
  app.querySelector("#gtbl").innerHTML = d.swimmers.map((s, i) => {
    const color = SWIMMER_COLORS[i % SWIMMER_COLORS.length];
    const sm = s.summary || {};
    return `<tr>
      <td><span style="display:inline-block;width:11px;height:11px;border-radius:3px;background:${color};margin-right:6px"></span>${esc(s.name)}</td>
      <td>${fmtDist(sm.distance_m)}</td><td>${fmtDur(sm.duration_s)}</td>
      <td>${sm.buoys_taken ?? "—"}/${sm.buoys_total ?? "—"}</td>
      <td>${sm.xte_overall ? sm.xte_overall.p95 + " м" : "—"}</td>
      <td><a class="btn ghost small" href="#/share/${s.share_token}">отчёт</a></td>
    </tr>`;
  }).join("");
}

// ---------- Дашборд (тренировки) ----------
async function viewDashboard() {
  app.innerHTML = `<h1>Тренировки</h1><p class="subtitle">Заплывы с часов и загруженные вручную.</p>
    <div class="btn-row">
      <a class="btn" href="#/upload">⬆ Загрузить трек</a>
      <a class="btn secondary" href="#/routes">Маршруты</a>
    </div>
    <div id="list" class="empty">Загрузка…</div>`;
  const items = await api("/api/activities");
  const el = app.querySelector("#list");
  if (!items.length) { el.innerHTML = `<div class="empty">Пока нет тренировок. Загрузите GPX или отправьте заплыв с часов.</div>`; return; }
  el.className = "grid";
  el.innerHTML = items.map((a) => `
    <div class="card clickable" onclick="location.hash='#/activities/${a.id}'">
      <div style="display:flex;justify-content:space-between;align-items:start;gap:8px">
        <strong>${esc(a.name)}</strong>
        ${a.is_public ? '<span class="pill info">share</span>' : ""}
      </div>
      <div class="muted" style="font-size:13px;margin-top:6px">${fmtDate(a.recorded_at || a.created_at)}</div>
      <div style="margin-top:12px;display:flex;gap:18px">
        <div><div style="font-weight:700">${fmtDist(a.distance_m)}</div><div class="muted" style="font-size:12px">дистанция</div></div>
        <div><div style="font-weight:700">${fmtDur(a.duration_s)}</div><div class="muted" style="font-size:12px">время</div></div>
        <div><div style="font-weight:700">${a.buoys_taken ?? "—"}/${a.buoys_total ?? "—"}</div><div class="muted" style="font-size:12px">буи</div></div>
      </div>
      <div class="muted" style="font-size:12px;margin-top:10px">источник: ${esc(a.source)}</div>
    </div>`).join("");
}

// ---------- Маршруты ----------
async function viewRoutes() {
  app.innerHTML = `<h1>Маршруты</h1><p class="subtitle">Точки буёв для часов и отчётов.</p>
    <div class="btn-row"><a class="btn" href="#/routes/new">＋ Новый маршрут</a></div>
    <div id="list" class="empty">Загрузка…</div>`;
  const items = await api("/api/routes");
  const el = app.querySelector("#list");
  if (!items.length) { el.innerHTML = `<div class="empty">Маршрутов нет. Создайте первый.</div>`; return; }
  el.className = "grid";
  el.innerHTML = items.map((r) => `
    <div class="card clickable" onclick="location.hash='#/routes/${r.id}'">
      <div style="display:flex;justify-content:space-between;gap:8px">
        <strong>${esc(r.name)}</strong>
        ${r.is_public ? '<span class="pill info">public</span>' : ""}
      </div>
      <div class="muted" style="font-size:13px;margin-top:8px">${routeListMeta(r)}</div>
      <div class="muted" style="font-size:12px;margin-top:6px">обновлён ${fmtDate(r.updated_at)}</div>
    </div>`).join("");
}

async function viewRoute(id) {
  const r = await api(`/api/routes/${id}`);
  const order = (r.session && r.session.order) || Object.keys(r.points);
  const legs = buildRouteLegs(routeToLegData(r));
  const dist = r.distance_m || legs.reduce((s, l) => s + l.length_m, 0);
  app.innerHTML = `
    <h1>${esc(r.name)}</h1>
    <p class="subtitle">${order.length} буёв · ${fmtDist(dist)} · радиус ${r.arrivalRadiusM} м · dwell ${r.dwellSec} с</p>
    <div class="btn-row">
      <a class="btn" href="/api/routes/${id}.gpx">⬇ GPX (на часы / карты)</a>
      <a class="btn secondary" href="/api/routes/${id}.json">⬇ JSON</a>
      ${r.owner ? `<a class="btn ghost" href="#/routes/${id}/edit">✎ Изменить</a>
      <button class="btn danger" id="del">Удалить</button>` : ""}
    </div>
    <div id="map" class="map"></div>
    <div class="legend"><span class="l-buoy">буй</span><span class="l-corridor">коридор</span></div>
    <div id="rstats"></div>
    <h2>Точки</h2><div id="tbl"></div>`;

  renderRouteMap("map", r);
  renderRouteLegStats(app.querySelector("#rstats"), legs);
  app.querySelector("#tbl").innerHTML = routePointsTable(r, order);

  const del = app.querySelector("#del");
  if (del) del.onclick = async () => {
    if (!confirm("Удалить маршрут?")) return;
    await api(`/api/routes/${id}`, { method: "DELETE" });
    location.hash = "#/routes";
  };
}

async function viewRouteEdit(id, opts = {}) {
  const adminMode = !!opts.admin;
  const apiFn = adminMode ? adminApi : api;
  const basePath = adminMode ? "/api/admin/routes" : "/api/routes";
  const backHash = adminMode ? "#/admin/routes" : "#/routes";
  let data = { name: "", arrivalRadiusM: 20, dwellSec: 4, orderMode: "fixed",
    points: { P1: { lat: 60.0, lon: 30.0, name: "Буй 1" } }, order: ["P1"],
    start: null, finish: null, is_public: false };
  if (id) {
    const r = await apiFn(`${basePath}/${id}`);
    data = {
      name: r.name, arrivalRadiusM: r.arrivalRadiusM, dwellSec: r.dwellSec,
      orderMode: (r.session && r.session.orderMode) || "fixed",
      points: r.points, order: (r.session && r.session.order) || Object.keys(r.points),
      start: r.start || null, finish: r.finish || null, is_public: !!r.is_public,
    };
  }
  let clickMode = "buoy"; // buoy | start | finish

  app.innerHTML = `
    <h1>${id ? "Изменить маршрут" : "Новый маршрут"}</h1>
    <p class="subtitle">Клик по карте добавляет точку выбранного типа. Коридор строится
      от старта через буи к финишу.</p>
    <div class="row">
      <div><label>Название</label><input id="name" value="${esc(data.name)}" /></div>
      <div style="flex:0 0 120px"><label>Радиус, м</label><input id="rad" type="number" value="${data.arrivalRadiusM}" /></div>
      <div style="flex:0 0 120px"><label>Dwell, с</label><input id="dwell" type="number" value="${data.dwellSec}" /></div>
    </div>
    <label><input type="checkbox" id="pub" style="width:auto" ${data.is_public ? "checked" : ""}/> Публичный (виден другим и часам)</label>
    <div class="row" style="align-items:end;margin-top:10px">
      <div style="flex:0 0 auto"><label style="margin-top:0">Клик по карте добавляет</label>
        <select id="clickmode" style="width:auto">
          <option value="buoy">🟡 буй</option>
          <option value="start">📍 старт</option>
          <option value="finish">🟢 финиш</option>
        </select></div>
      <div style="flex:0 0 auto"><button class="btn ghost small" id="loop">финиш = старт</button></div>
    </div>

    <details class="overlay-panel" id="overlayPanel">
      <summary>Подложка: треки тренировок</summary>
      <div class="overlay-body">
        <div class="overlay-toolbar">
          <input type="search" id="overlaySearch" placeholder="Поиск по названию, спортсмену…" autocomplete="off" />
          <button type="button" class="btn ghost small" id="overlayClear">Снять все</button>
        </div>
        <div id="overlayGroups" class="overlay-groups"><div class="overlay-empty">Загрузка…</div></div>
        <div id="overlayChips" class="overlay-chips"></div>
        <p class="overlay-hint muted" id="overlayHint"></p>
      </div>
    </details>

    <div id="map" class="map" style="margin-top:12px"></div>
    <div class="legend"><span class="l-buoy">буй</span><span class="l-corridor">коридор</span><span class="l-track" id="trackLegend" style="display:none">трек</span></div>

    <div class="card" style="margin-top:14px">
      <div class="row" style="align-items:center;margin-bottom:8px">
        <div style="flex:1 1 260px">
          <label style="margin-top:0">Ширина коридора: <b id="halfval">авто</b></label>
          <input id="half" type="range" min="0" max="120" step="1" value="0" />
          <p class="muted" style="font-size:12px;margin:4px 0 0">0 = авто по длине плеча (как в отчёте)</p>
        </div>
        <div style="flex:0 0 auto"><label style="margin-top:0">
          <input type="checkbox" id="corrToggle" checked style="width:auto" /> показывать коридор</label>
        </div>
      </div>
      <div id="rstats"></div>
    </div>

    <h2>Старт и финиш</h2>
    <div id="ends"></div>

    <h2>Буи (по порядку)</h2>
    <div id="pts"></div>
    <div class="btn-row">
      <button class="btn secondary small" id="add">＋ Добавить буй (центр карты)</button>
    </div>

    <details style="margin-top:18px">
      <summary class="muted" style="cursor:pointer">JSON-редактор (для продвинутых)</summary>
      <p class="muted" style="font-size:13px;margin:8px 0">Отредактируйте JSON и нажмите
        «Применить» — карта и поля обновятся. Затем «Сохранить».</p>
      <textarea id="json" rows="14" spellcheck="false"
        style="font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px"></textarea>
      <div class="btn-row">
        <button class="btn secondary small" id="applyjson">Применить JSON к карте</button>
        <span id="jsonerr" class="muted" style="align-self:center;font-size:13px"></span>
      </div>
    </details>

    <div class="btn-row"><button class="btn" id="save">Сохранить</button>
      <a class="btn ghost" href="${backHash}">Отмена</a></div>`;

  const firstPid = data.order[0];
  const map = L.map("map").setView(
    [data.points[firstPid]?.lat || data.start?.lat || 60,
     data.points[firstPid]?.lon || data.start?.lon || 30], 14);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);
  let markers = [];
  const trackLayer = L.layerGroup().addTo(map);
  const corridorLayer = L.layerGroup().addTo(map);
  let corridorHalfOverride = 0;
  let showCorridor = true;
  let overlayCandidates = { on_route: [], unassigned: [], limit: 150 };
  const selectedOverlays = new Map();
  const trackLinePath = adminMode ? "/api/admin/activities" : "/api/activities";
  const overlayListPath = adminMode ? "/api/admin/routes/editor-overlays" : "/api/routes/editor-overlays";

  function corridorHalfForLeg(leg) {
    return corridorHalfOverride > 0 ? corridorHalfOverride : leg.corridor_half_m;
  }

  function updateHalfLabel() {
    const el = app.querySelector("#halfval");
    if (!el) return;
    el.textContent = corridorHalfOverride > 0 ? `±${corridorHalfOverride} м` : "авто";
  }

  app.querySelector("#half").oninput = (e) => {
    corridorHalfOverride = parseInt(e.target.value, 10) || 0;
    updateHalfLabel();
    renderMap();
  };
  app.querySelector("#corrToggle").onchange = (e) => {
    showCorridor = e.target.checked;
    renderMap();
  };

  app.querySelector("#clickmode").onchange = (e) => { clickMode = e.target.value; };

  function nextId() {
    let n = 1;
    while (data.order.includes("P" + n)) n++;
    return "P" + n;
  }

  // --- Старт / финиш ---
  function endRow(kind, label, pt) {
    if (!pt) {
      return `<div class="card" style="margin-bottom:8px;display:flex;justify-content:space-between;align-items:center;gap:8px">
        <span class="muted">${label}: не задан</span>
        <button class="btn ghost small" data-setend="${kind}">Задать (центр карты)</button></div>`;
    }
    return `<div class="card" style="margin-bottom:8px"><div class="row" style="align-items:end">
      <div style="flex:0 0 90px"><label>${label}</label><input value="${kind}" disabled /></div>
      <div style="flex:0 0 130px"><label>Lat</label><input data-end="${kind}" data-f="lat" value="${pt.lat}" /></div>
      <div style="flex:0 0 130px"><label>Lon</label><input data-end="${kind}" data-f="lon" value="${pt.lon}" /></div>
      <div style="flex:0 0 auto"><button class="btn danger small" data-delend="${kind}">убрать</button></div>
    </div></div>`;
  }
  function renderEnds() {
    const box = app.querySelector("#ends");
    box.innerHTML = endRow("start", "📍 Старт", data.start) + endRow("finish", "🟢 Финиш", data.finish);
    box.querySelectorAll("input[data-end]").forEach((inp) => {
      inp.onchange = () => {
        const kind = inp.dataset.end, f = inp.dataset.f;
        if (data[kind]) { data[kind][f] = parseFloat(inp.value); renderMap(); syncJson(); }
      };
    });
    box.querySelectorAll("button[data-setend]").forEach((b) => {
      b.onclick = () => {
        const c = map.getCenter();
        data[b.dataset.setend] = { lat: +c.lat.toFixed(6), lon: +c.lng.toFixed(6),
          name: b.dataset.setend === "start" ? "Старт" : "Финиш" };
        renderEnds(); renderMap(); syncJson();
      };
    });
    box.querySelectorAll("button[data-delend]").forEach((b) => {
      b.onclick = () => { data[b.dataset.delend] = null; renderEnds(); renderMap(); syncJson(); };
    });
  }

  function renderPts() {
    const box = app.querySelector("#pts");
    if (!data.order.length) {
      box.innerHTML = `<p class="muted">Буёв нет — кликните по карте или добавьте вручную.</p>`;
      return;
    }
    box.innerHTML = `<div class="table-wrap buoy-table-wrap"><table>
      <thead><tr><th>#</th><th>ID</th><th>Имя</th><th>Lat</th><th>Lon</th><th></th></tr></thead>
      <tbody>${data.order.map((pid, i) => {
        const p = data.points[pid];
        return `<tr>
          <td>${i + 1}</td>
          <td class="muted">${esc(pid)}</td>
          <td><input data-f="name" data-id="${pid}" value="${esc(p.name || "")}" /></td>
          <td><input data-f="lat" data-id="${pid}" value="${p.lat}" /></td>
          <td><input data-f="lon" data-id="${pid}" value="${p.lon}" /></td>
          <td><button class="btn danger small" data-del="${pid}">✕</button></td>
        </tr>`;
      }).join("")}</tbody></table></div>`;
    box.querySelectorAll("input[data-f]").forEach((inp) => {
      inp.onchange = () => {
        const pid = inp.dataset.id, f = inp.dataset.f;
        data.points[pid][f] = f === "name" ? inp.value : parseFloat(inp.value);
        renderMap(); syncJson();
      };
    });
    box.querySelectorAll("button[data-del]").forEach((b) => {
      b.onclick = () => {
        const pid = b.dataset.del;
        delete data.points[pid];
        data.order = data.order.filter((x) => x !== pid);
        renderPts(); renderMap(); syncJson();
      };
    });
  }

  function renderMap() {
    markers.forEach((m) => map.removeLayer(m));
    markers = [];
    corridorLayer.clearLayers();
    const legs = buildRouteLegs(data);
    const line = [];
    if (data.start) {
      markers.push(L.marker([data.start.lat, data.start.lon]).addTo(map).bindTooltip("Старт"));
      line.push([data.start.lat, data.start.lon]);
    }
    data.order.forEach((pid, i) => {
      const p = data.points[pid];
      const m = L.circleMarker([p.lat, p.lon], { radius: 8, color: "#fbbf24", fillColor: "#fbbf24", fillOpacity: .9 })
        .addTo(map).bindTooltip(`${i + 1}`);
      markers.push(m); line.push([p.lat, p.lon]);
    });
    if (data.finish) {
      markers.push(L.circleMarker([data.finish.lat, data.finish.lon],
        { radius: 7, color: "#34d399", fillColor: "#34d399", fillOpacity: .9 }).addTo(map).bindTooltip("Финиш"));
      line.push([data.finish.lat, data.finish.lon]);
    }
    if (showCorridor) {
      legs.forEach((leg) => {
        const half = corridorHalfForLeg(leg);
        L.polygon(_legPolygon(leg.a, leg.b, half), {
          color: "#2dd4bf", weight: 1, opacity: .5,
          fillColor: "#2dd4bf", fillOpacity: .22,
        }).addTo(corridorLayer);
      });
    }
    legs.forEach((leg) => {
      markers.push(L.polyline([leg.a, leg.b], {
        color: "#2dd4bf", weight: 3, opacity: .85,
      }).addTo(map).bindTooltip(`${esc(leg.fromLabel)} → ${esc(leg.toLabel)}: ${fmtDist(leg.length_m)}`));
    });
    if (line.length >= 2 && !legs.length) {
      markers.push(L.polyline(line, { color: "#2dd4bf", weight: 2, dashArray: "6 6" }).addTo(map));
    }
    renderRouteLegStats(app.querySelector("#rstats"), legs);
    updateHalfLabel();
  }

  function renderOverlayChips() {
    const chips = app.querySelector("#overlayChips");
    const legend = app.querySelector("#trackLegend");
    if (!chips) return;
    if (!selectedOverlays.size) {
      chips.innerHTML = "";
      if (legend) legend.style.display = "none";
      return;
    }
    if (legend) legend.style.display = "";
    chips.innerHTML = [...selectedOverlays.values()].map((o) =>
      `<span class="overlay-chip" style="border-color:${o.color};color:${o.color}">${esc(o.name)}</span>`
    ).join("");
  }

  function renderOverlayGroups(filter = "") {
    const box = app.querySelector("#overlayGroups");
    const hint = app.querySelector("#overlayHint");
    if (!box) return;
    box.innerHTML = "";
    if (id) {
      mountOverlayGroup("На этом маршруте", overlayCandidates.on_route, box,
        selectedOverlays, toggleOverlay, filter);
    }
    mountOverlayGroup("Без маршрута", overlayCandidates.unassigned, box,
      selectedOverlays, toggleOverlay, filter);
    const total = overlayCandidates.on_route.length + overlayCandidates.unassigned.length;
    const lim = overlayCandidates.limit || 150;
    if (hint) {
      hint.textContent = total >= lim
        ? `Показаны последние ${lim} тренировок в каждой группе. Уточните поиск, если нужной нет.`
        : "Отметьте тренировки — их треки появятся на карте под коридором.";
    }
  }

  async function toggleOverlay(activityId, on) {
    if (!on) {
      const entry = selectedOverlays.get(activityId);
      if (entry) {
        trackLayer.removeLayer(entry.layer);
        selectedOverlays.delete(activityId);
      }
      renderOverlayChips();
      return;
    }
    if (selectedOverlays.has(activityId)) return;
    try {
      const line = await apiFn(`${trackLinePath}/${activityId}/track-line`);
      if (!line.line || line.line.length < 2) {
        toast("В тренировке нет трека");
        renderOverlayGroups(app.querySelector("#overlaySearch")?.value || "");
        return;
      }
      const color = SWIMMER_COLORS[selectedOverlays.size % SWIMMER_COLORS.length];
      const layer = L.polyline(line.line, { color, weight: 3, opacity: .78 })
        .bindTooltip(esc(line.name));
      trackLayer.addLayer(layer);
      selectedOverlays.set(activityId, { layer, color, name: line.name });
      renderOverlayChips();
    } catch (e) {
      toast(e.message);
      renderOverlayGroups(app.querySelector("#overlaySearch")?.value || "");
    }
  }

  async function loadOverlayCandidates() {
    try {
      const url = id ? `${overlayListPath}?route_id=${encodeURIComponent(id)}` : overlayListPath;
      overlayCandidates = await apiFn(url);
      renderOverlayGroups();
    } catch (e) {
      const box = app.querySelector("#overlayGroups");
      if (box) box.innerHTML = `<div class="overlay-empty">${esc(e.message)}</div>`;
    }
  }

  const overlaySearch = app.querySelector("#overlaySearch");
  if (overlaySearch) {
    overlaySearch.addEventListener("input", (e) => {
      renderOverlayGroups(e.target.value);
    });
  }
  const overlayClear = app.querySelector("#overlayClear");
  if (overlayClear) {
    overlayClear.onclick = () => {
      trackLayer.clearLayers();
      selectedOverlays.clear();
      renderOverlayChips();
      renderOverlayGroups(overlaySearch ? overlaySearch.value : "");
    };
  }

  // --- Синхронизация JSON-редактора ---
  function currentJson() {
    return {
      name: data.name, arrivalRadiusM: data.arrivalRadiusM, dwellSec: data.dwellSec,
      orderMode: data.orderMode, points: data.points, order: data.order,
      start: data.start, finish: data.finish, is_public: data.is_public,
    };
  }
  function syncJson() {
    const ta = app.querySelector("#json");
    // не затираем, пока пользователь редактирует JSON вручную
    if (document.activeElement !== ta) ta.value = JSON.stringify(currentJson(), null, 2);
  }
  app.querySelector("#applyjson").onclick = () => {
    const err = app.querySelector("#jsonerr");
    try {
      const j = JSON.parse(app.querySelector("#json").value);
      if (!j.points || typeof j.points !== "object") throw new Error("нет points");
      data.name = j.name ?? data.name;
      data.arrivalRadiusM = parseInt(j.arrivalRadiusM) || data.arrivalRadiusM;
      data.dwellSec = parseInt(j.dwellSec) || data.dwellSec;
      data.orderMode = j.orderMode || data.orderMode;
      data.points = j.points;
      data.order = (Array.isArray(j.order) && j.order.length ? j.order : Object.keys(j.points))
        .filter((pid) => pid in j.points);
      data.start = j.start || null;
      data.finish = j.finish || null;
      data.is_public = !!j.is_public;
      app.querySelector("#name").value = data.name;
      app.querySelector("#rad").value = data.arrivalRadiusM;
      app.querySelector("#dwell").value = data.dwellSec;
      app.querySelector("#pub").checked = data.is_public;
      err.textContent = "✓ применено";
      err.style.color = "var(--good)";
      renderEnds(); renderPts(); renderMap();
    } catch (e) {
      err.textContent = "Ошибка JSON: " + e.message;
      err.style.color = "var(--danger)";
    }
  };

  map.on("click", (e) => {
    const lat = +e.latlng.lat.toFixed(6), lon = +e.latlng.lng.toFixed(6);
    if (clickMode === "start") {
      data.start = { lat, lon, name: "Старт" };
    } else if (clickMode === "finish") {
      data.finish = { lat, lon, name: "Финиш" };
    } else {
      const pid = nextId();
      data.points[pid] = { lat, lon, name: "" };
      data.order.push(pid);
    }
    renderEnds(); renderPts(); renderMap(); syncJson();
  });
  app.querySelector("#add").onclick = () => {
    const c = map.getCenter(); const pid = nextId();
    data.points[pid] = { lat: +c.lat.toFixed(6), lon: +c.lng.toFixed(6), name: "" };
    data.order.push(pid); renderPts(); renderMap(); syncJson();
  };
  app.querySelector("#loop").onclick = () => {
    if (!data.start) return toast("Сначала задайте старт");
    data.finish = { lat: data.start.lat, lon: data.start.lon, name: "Финиш" };
    renderEnds(); renderMap(); syncJson();
  };

  // Текущие значения name/rad/dwell держим в data для JSON-редактора.
  app.querySelector("#name").oninput = (e) => { data.name = e.target.value; syncJson(); };
  app.querySelector("#rad").oninput = (e) => { data.arrivalRadiusM = parseInt(e.target.value) || 20; syncJson(); };
  app.querySelector("#dwell").oninput = (e) => { data.dwellSec = parseInt(e.target.value) || 4; syncJson(); };
  app.querySelector("#pub").onchange = (e) => { data.is_public = e.target.checked; syncJson(); };

  app.querySelector("#save").onclick = async () => {
    const body = {
      name: (data.name || "").trim() || "Маршрут",
      arrivalRadiusM: data.arrivalRadiusM,
      dwellSec: data.dwellSec,
      orderMode: data.orderMode,
      points: data.points, order: data.order,
      start: data.start, finish: data.finish,
      is_public: data.is_public,
    };
    if (!data.order.length) return toast("Добавьте хотя бы один буй");
    try {
      const saved = id
        ? await apiFn(`${basePath}/${id}`, { method: "PUT", json: body })
        : await apiFn(basePath, { method: "POST", json: body });
      toast("Маршрут сохранён");
      location.hash = adminMode ? "#/admin/routes" : `#/routes/${saved.id}`;
    } catch (e) { toast(e.message); }
  };

  renderEnds(); renderPts(); renderMap(); syncJson();
  loadOverlayCandidates();
}

// ---------- Загрузка трека ----------
async function viewUpload() {
  const routes = await api("/api/routes");
  app.innerHTML = `
    <h1>Загрузить трек</h1>
    <p class="subtitle">GPX, TCX или FIT. Привяжите к маршруту, чтобы построить отчёт по коридору.</p>
    <div class="card center-panel" style="margin-top:10px">
      <label>Файл трека</label>
      <input id="file" type="file" accept=".gpx,.tcx,.fit" />
      <label>Маршрут (для отчёта)</label>
      <select id="route"><option value="">— без маршрута —</option>
        ${routes.map((r) => `<option value="${r.id}">${esc(r.name)}</option>`).join("")}</select>
      <label>Название (необязательно)</label>
      <input id="name" placeholder="Заплыв 14.06" />
      <div class="btn-row"><button class="btn" id="go">Загрузить</button></div>
    </div>`;
  app.querySelector("#go").onclick = async () => {
    const f = app.querySelector("#file").files[0];
    if (!f) return toast("Выберите файл");
    const fd = new FormData();
    fd.append("file", f);
    const rid = app.querySelector("#route").value;
    if (rid) fd.append("route_id", rid);
    const nm = app.querySelector("#name").value.trim();
    if (nm) fd.append("name", nm);
    try {
      const a = await api("/api/activities/upload", { method: "POST", body: fd });
      location.hash = `#/activities/${a.id}`;
    } catch (e) { toast(e.message); }
  };
}

// ---------- Отчёт по тренировке ----------
function renderReportMap(elId, geojson) {
  const map = L.map(elId);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);
  const bounds = [];
  const ll = (c) => [c[1], c[0]]; // geojson [lon,lat] -> leaflet [lat,lon]
  (geojson.features || []).forEach((f) => {
    const k = f.properties.kind, g = f.geometry;
    if (k === "corridor" && g.type === "Polygon") {
      L.polygon(g.coordinates[0].map(ll), { color: "#2dd4bf", weight: 1, opacity: .5, fillColor: "#2dd4bf", fillOpacity: .25 }).addTo(map);
    } else if (k === "leg") {
      L.polyline(g.coordinates.map(ll), { color: "#2dd4bf", weight: 1.5, dashArray: "5 6", opacity: .7 }).addTo(map);
    } else if (k === "track") {
      const pts = g.coordinates.map(ll);
      L.polyline(pts, { color: "#38bdf8", weight: 3 }).addTo(map);
      pts.forEach((p) => bounds.push(p));
    } else if (k === "buoy") {
      const taken = f.properties.taken;
      L.circleMarker(ll(g.coordinates), { radius: 8, color: taken ? "#fbbf24" : "#f87171",
        fillColor: taken ? "#fbbf24" : "#f87171", fillOpacity: .9 })
        .addTo(map).bindPopup(`${esc(f.properties.name)}<br>ближе всего: ${f.properties.closest_m} м<br>${taken ? "взят" : "не взят"}`);
    } else if (k === "start") {
      L.marker(ll(g.coordinates)).addTo(map).bindPopup("Старт");
    } else if (k === "finish") {
      L.circleMarker(ll(g.coordinates), { radius: 7, color: "#34d399", fillColor: "#34d399", fillOpacity: .9 })
        .addTo(map).bindPopup("Финиш");
    }
  });
  if (bounds.length) map.fitBounds(bounds, { padding: [40, 40] });
}

function reportBody(report, container) {
  if (!report || !report.ok) {
    container.innerHTML += `<div class="card"><p class="muted">${esc((report && report.error) || "Отчёт не построен. Привяжите трек к маршруту.")}</p></div>`;
    return;
  }
  const s = report.summary;
  container.innerHTML += `
    <div class="stats">
      <div class="stat"><div class="v">${fmtDist(s.distance_m)}</div><div class="k">проплыто</div></div>
      <div class="stat"><div class="v">${fmtDur(s.duration_s)}</div><div class="k">время</div></div>
      <div class="stat"><div class="v">${s.pace_min_100m ?? "—"}</div><div class="k">мин/100м</div></div>
      <div class="stat"><div class="v">${s.buoys_taken}/${s.buoys_total}</div><div class="k">буёв взято</div></div>
      <div class="stat"><div class="v">${s.efficiency_pct != null ? s.efficiency_pct + "%" : "—"}</div><div class="k">эффективность</div></div>
      <div class="stat"><div class="v">${s.xte_overall ? s.xte_overall.p95 + " м" : "—"}</div><div class="k">XTE p95</div></div>
    </div>
    <div id="rmap" class="map"></div>
    <div class="legend"><span class="l-track">трек</span><span class="l-corridor">коридор</span>
      <span class="l-buoy">взят</span><span class="l-miss">не взят</span></div>
    <h2>Отклонение по плечам (cross-track)</h2>
    <div class="table-wrap"><table><thead><tr><th>Плечо</th><th>Длина</th><th>Медиана</th><th>p90</th><th>p95</th><th>макс</th><th>коридор ±</th></tr></thead>
      <tbody>${report.legs.map((l) => `<tr>
        <td>${esc(l.from)}→${esc(l.to)}</td>
        <td>${fmtDist(l.length_m)}</td>
        <td>${l.xte && l.xte.median != null ? l.xte.median + " м" : "—"}</td>
        <td>${l.xte && l.xte.p90 != null ? l.xte.p90 + " м" : "—"}</td>
        <td>${l.xte && l.xte.p95 != null ? l.xte.p95 + " м" : "—"}</td>
        <td>${l.xte && l.xte.max != null ? l.xte.max + " м" : "—"}</td>
        <td>${l.corridor_half_m} м</td></tr>`).join("")}</tbody></table></div>`;
  renderReportMap("rmap", report.geojson);
}

async function viewActivity(id) {
  const a = await api(`/api/activities/${id}`);
  app.innerHTML = `
    <h1>${esc(a.name)}</h1>
    <p class="subtitle">${fmtDate(a.recorded_at || a.created_at)} · источник: ${esc(a.source)}</p>
    <div class="btn-row">
      <button class="btn ${a.is_public ? "secondary" : ""}" id="share">${a.is_public ? "🔗 Ссылка скопирована" : "Поделиться"}</button>
      <button class="btn danger" id="del">Удалить</button>
    </div>
    <div id="report"></div>`;
  reportBody(a.report, app.querySelector("#report"));

  app.querySelector("#share").onclick = async () => {
    const res = await api(`/api/activities/${id}/share`, { method: "POST", json: { is_public: true } });
    const url = location.origin + "/s/" + res.share_token;
    try { await navigator.clipboard.writeText(url); } catch (e) {}
    toast("Ссылка скопирована: " + url);
  };
  app.querySelector("#del").onclick = async () => {
    if (!confirm("Удалить тренировку?")) return;
    await api(`/api/activities/${id}`, { method: "DELETE" });
    location.hash = "#/";
  };
}

// ---------- Публичный отчёт ----------
async function viewShare(token) {
  app.innerHTML = `<div class="empty">Загрузка отчёта…</div>`;
  try {
    const d = await api(`/api/public/activities/${token}`);
    app.innerHTML = `
      <h1>${esc(d.name)}</h1>
      <p class="subtitle">${esc(d.athlete)}${d.route_name ? " · " + esc(d.route_name) : ""}
        · ${fmtDate(d.recorded_at)}</p>
      <div id="report"></div>`;
    reportBody(d.report, app.querySelector("#report"));
  } catch (e) {
    app.innerHTML = `<div class="card center-panel"><h2>Отчёт недоступен</h2>
      <p class="muted">${esc(e.message)}</p></div>`;
  }
}

// ---------- Админка ----------
function adminLoginView() {
  app.innerHTML = `
    <div class="center-panel card">
      <h1>Админ-панель</h1>
      <p class="subtitle">Вход для администратора.</p>
      <label>Логин</label><input id="u" value="admin" />
      <label>Пароль</label><input id="p" type="password" placeholder="••••••" />
      <div class="btn-row"><button class="btn" id="go">Войти</button></div>
    </div>`;
  const submit = async () => {
    const u = app.querySelector("#u").value.trim();
    const p = app.querySelector("#p").value;
    setAdmin(btoa(u + ":" + p));
    try { await adminApi("/api/admin/login"); location.hash = "#/admin"; route(); }
    catch (e) { clearAdmin(); toast("Неверный логин или пароль"); }
  };
  app.querySelector("#go").onclick = submit;
  app.querySelector("#p").onkeydown = (e) => { if (e.key === "Enter") submit(); };
}

async function viewAdmin(tab, sub, sub2) {
  if (!getAdmin()) return adminLoginView();
  try { await adminApi("/api/admin/login"); }
  catch (e) { return adminLoginView(); }

  // Редактирование маршрута прямо из админки (полноэкранный редактор).
  if (tab === "routes" && sub === "new") return viewRouteEdit(null, { admin: true });
  if (tab === "routes" && sub && sub2 === "edit") return viewRouteEdit(sub, { admin: true });

  tab = tab || "registrations";
  const tabLink = (id, label) =>
    `<a class="btn ${tab === id ? "" : "ghost"} small" href="#/admin/${id}">${label}</a>`;
  app.innerHTML = `
    <h1>Админ-панель</h1>
    <div class="btn-row">
      ${tabLink("registrations", "Заявки")}
      ${tabLink("athletes", "Спортсмены")}
      ${tabLink("routes", "Маршруты")}
      ${tabLink("activities", "Тренировки")}
      <a class="btn ghost small" href="#" id="alogout" style="margin-left:auto">Выйти</a>
    </div>
    <div id="atab" class="empty">Загрузка…</div>`;
  app.querySelector("#alogout").onclick = (e) => { e.preventDefault(); clearAdmin(); location.hash = "#/admin"; route(); };

  if (tab === "registrations") return adminRegistrations();
  if (tab === "athletes") return adminAthletes();
  if (tab === "routes") return adminRoutes();
  if (tab === "activities") return adminActivities();
}

async function adminRegistrations() {
  const box = app.querySelector("#atab");
  box.className = "";
  const list = await adminApi("/api/admin/registrations");
  if (!list.length) { box.innerHTML = `<div class="empty">Заявок нет.</div>`; return; }
  box.innerHTML = `<table><thead><tr><th>Имя</th><th>Контакт</th><th>Комментарий</th><th>Статус</th><th></th></tr></thead>
    <tbody>${list.map((r) => `<tr>
      <td>${esc(r.name)}</td><td class="muted">${esc(r.contact)}</td>
      <td class="muted">${esc(r.note)}</td>
      <td>${r.status === "pending" ? '<span class="pill info">новая</span>'
        : r.status === "approved" ? '<span class="pill good">принята</span>'
        : '<span class="pill bad">отклонена</span>'}</td>
      <td>${r.status === "pending"
        ? `<button class="btn small" data-ok="${r.id}">Одобрить</button>
           <button class="btn danger small" data-no="${r.id}">Отклонить</button>`
        : `<button class="btn ghost small" data-del="${r.id}">Удалить</button>`}</td>
    </tr>`).join("")}</tbody></table>`;
  box.querySelectorAll("button[data-ok]").forEach((b) => {
    b.onclick = async () => {
      const res = await adminApi(`/api/admin/registrations/${b.dataset.ok}/approve`, { method: "POST" });
      try { await navigator.clipboard.writeText(res.token); } catch (e) {}
      toast(`Аккаунт создан. Токен: ${res.token} (скопирован)`);
      adminRegistrations();
    };
  });
  box.querySelectorAll("button[data-no]").forEach((b) => {
    b.onclick = async () => {
      await adminApi(`/api/admin/registrations/${b.dataset.no}/reject`, { method: "POST" });
      adminRegistrations();
    };
  });
  box.querySelectorAll("button[data-del]").forEach((b) => {
    b.onclick = async () => {
      await adminApi(`/api/admin/registrations/${b.dataset.del}`, { method: "DELETE" });
      adminRegistrations();
    };
  });
}

async function adminAthletes() {
  const box = app.querySelector("#atab");
  box.className = "";
  const list = await adminApi("/api/athletes");
  box.innerHTML = `
    <div class="card" style="margin-bottom:16px">
      <h2 style="margin-top:0">Новый спортсмен</h2>
      <div class="row" style="align-items:end">
        <div><label>Имя</label><input id="nm" placeholder="Имя спортсмена" /></div>
        <div style="flex:0 0 auto"><button class="btn" id="add">Создать токен</button></div>
      </div>
    </div>
    <table><thead><tr><th>Имя</th><th>Токен</th><th>Маршруты</th><th>Тренировки</th><th></th></tr></thead>
      <tbody>${list.map((a) => `<tr>
        <td>${esc(a.name)}</td>
        <td><code style="font-size:15px;letter-spacing:1px">${esc(a.token)}</code></td>
        <td>${a.routes}</td><td>${a.activities}</td>
        <td><button class="btn danger small" data-del="${a.id}">Удалить</button></td>
      </tr>`).join("")}</tbody></table>`;
  box.querySelector("#add").onclick = async () => {
    const nm = box.querySelector("#nm").value.trim();
    if (!nm) return toast("Введите имя");
    const a = await adminApi("/api/athletes", { method: "POST", json: { name: nm } });
    toast("Токен: " + a.token);
    adminAthletes();
  };
  box.querySelectorAll("button[data-del]").forEach((b) => {
    b.onclick = async () => {
      if (!confirm("Удалить спортсмена со всеми его маршрутами и тренировками?")) return;
      await adminApi(`/api/athletes/${b.dataset.del}`, { method: "DELETE" });
      adminAthletes();
    };
  });
}

async function adminRoutes() {
  const box = app.querySelector("#atab");
  box.className = "";
  const list = await adminApi("/api/admin/routes");
  const head = `<div class="btn-row"><a class="btn small" href="#/admin/routes/new">＋ Новый маршрут</a></div>`;
  if (!list.length) { box.innerHTML = head + `<div class="empty">Маршрутов нет.</div>`; return; }
  box.innerHTML = head + `<div class="table-wrap"><table><thead><tr><th>Название</th><th>Спортсмен</th><th>Буи</th><th>Дистанция</th><th>Публичный</th><th></th></tr></thead>
    <tbody>${list.map((r) => `<tr>
      <td>${esc(r.name)}</td><td class="muted">${esc(r.athlete || "")}</td>
      <td>${r.points_count}</td><td>${fmtDist(r.distance_m)}</td><td>${r.is_public ? "да" : "нет"}</td>
      <td style="white-space:nowrap">
        <a class="btn ghost small" href="#/admin/routes/${r.id}/edit">✎ Изменить</a>
        ${r.is_public ? `<a class="btn ghost small" href="/api/public/routes/${r.id}.gpx">GPX</a>` : ""}
        <button class="btn danger small" data-del="${r.id}">Удалить</button></td>
    </tr>`).join("")}</tbody></table></div>`;
  box.querySelectorAll("button[data-del]").forEach((b) => {
    b.onclick = async () => {
      if (!confirm("Удалить маршрут?")) return;
      await adminApi(`/api/admin/routes/${b.dataset.del}`, { method: "DELETE" });
      adminRoutes();
    };
  });
}

async function adminActivities() {
  const box = app.querySelector("#atab");
  box.className = "";
  const list = await adminApi("/api/admin/activities");
  if (!list.length) { box.innerHTML = `<div class="empty">Тренировок нет.</div>`; return; }
  box.innerHTML = `<table><thead><tr><th>Название</th><th>Спортсмен</th><th>Дист.</th><th>Буи</th><th>Источник</th><th></th></tr></thead>
    <tbody>${list.map((a) => `<tr>
      <td>${esc(a.name)}</td><td class="muted">${esc(a.athlete || "")}</td>
      <td>${fmtDist(a.distance_m)}</td>
      <td>${a.buoys_taken ?? "—"}/${a.buoys_total ?? "—"}</td>
      <td class="muted">${esc(a.source)}</td>
      <td><button class="btn danger small" data-del="${a.id}">Удалить</button></td>
    </tr>`).join("")}</tbody></table>`;
  box.querySelectorAll("button[data-del]").forEach((b) => {
    b.onclick = async () => {
      if (!confirm("Удалить тренировку?")) return;
      await adminApi(`/api/admin/activities/${b.dataset.del}`, { method: "DELETE" });
      adminActivities();
    };
  });
}
