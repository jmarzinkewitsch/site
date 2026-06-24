const els = {
  time: document.querySelector("[data-time]"),
  date: document.querySelector("[data-date]"),
  connection: document.querySelector("[data-connection]"),
  windowCount: document.querySelector("[data-window-count]"),
  lightCount: document.querySelector("[data-light-count]"),
  weatherTemp: document.querySelector("[data-weather-temp]"),
  weatherState: document.querySelector("[data-weather-state]"),
  lightRooms: document.querySelector("[data-light-rooms]"),
  climates: document.querySelector("[data-climates]"),
  climateCount: document.querySelector("[data-climate-count]"),
  coffeeLabel: document.querySelector("[data-coffee-label]"),
  coffeeState: document.querySelector("[data-coffee-state]"),
  coffeeToggle: document.querySelector("[data-coffee-toggle]"),
  allOff: document.querySelector("[data-all-off]"),
  pages: document.querySelectorAll("[data-page]"),
  navButtons: document.querySelectorAll("[data-nav]"),
  zones: document.querySelector("[data-zones]"),
  albums: document.querySelector("[data-albums]"),
  albumCount: document.querySelector("[data-album-count]"),
  zoneName: document.querySelector("[data-zone-name]"),
  trackTitle: document.querySelector("[data-track-title]"),
  trackSubtitle: document.querySelector("[data-track-subtitle]"),
  nowArt: document.querySelector("[data-now-art]"),
  seekCurrent: document.querySelector("[data-seek-current]"),
  seekTotal: document.querySelector("[data-seek-total]"),
  seekFill: document.querySelector("[data-seek-fill]"),
  musicStage: document.querySelector("[data-music-stage]"),
  refreshMusic: document.querySelector("[data-refresh-music]"),
  volumeControl: document.querySelector("[data-volume-control]"),
  volumeValue: document.querySelector("[data-volume-value]"),
  volumeButtons: document.querySelectorAll("[data-volume-step]"),
  todayTitle: document.querySelector("[data-today-title]"),
  todaySummary: document.querySelector("[data-today-summary]"),
  todayStack: document.querySelector("[data-today-stack]"),
  todayEventCount: document.querySelector("[data-today-event-count]"),
  todayTodoCount: document.querySelector("[data-today-todo-count]"),
  todayEvents: document.querySelector("[data-today-events]"),
  todayTodos: document.querySelector("[data-today-todos]"),
  todayNews: document.querySelector("[data-today-news]"),
  podcastStage: document.querySelector("[data-podcast-stage]"),
  podcastArt: document.querySelector("[data-podcast-art]"),
  podcastTitle: document.querySelector("[data-podcast-title]"),
  podcastSubtitle: document.querySelector("[data-podcast-subtitle]"),
  podcastCount: document.querySelector("[data-podcast-count]"),
  podcastPlayers: document.querySelector("[data-podcast-players]"),
  podcastTransportButtons: document.querySelectorAll("[data-podcast-transport]"),
  podcastSearchForm: document.querySelector("[data-podcast-search-form]"),
  podcastSearchInput: document.querySelector("[data-podcast-search]"),
  podcastSearchClear: document.querySelector("[data-podcast-search-clear]"),
  podcastSearchStatus: document.querySelector("[data-podcast-search-status]"),
  podcastSearchResults: document.querySelector("[data-podcast-search-results]"),
  podcasts: document.querySelector("[data-podcasts]"),
  vaultStage: document.querySelector("[data-vault-stage]"),
  vaultTitle: document.querySelector("[data-vault-title]"),
  vaultSubtitle: document.querySelector("[data-vault-subtitle]"),
  vaultCount: document.querySelector("[data-vault-count]"),
  vaultShelves: document.querySelector("[data-vault-shelves]"),
  ambientCanvas: document.querySelector("[data-ambient-canvas]"),
  ambientTitle: document.querySelector("[data-ambient-title]"),
  ambientSubtitle: document.querySelector("[data-ambient-subtitle]"),
  mediaOverlay: document.querySelector("[data-media-overlay]"),
  closeMedia: document.querySelector("[data-close-media]"),
  mediaVideo: document.querySelector("[data-media-video]"),
  mediaType: document.querySelector("[data-media-type]"),
  mediaTitle: document.querySelector("[data-media-title]"),
  mediaSubtitle: document.querySelector("[data-media-subtitle]"),
  mediaOverviewText: document.querySelector("[data-media-overview]"),
  mediaTrailer: document.querySelector("[data-media-trailer]"),
  mediaCast: document.querySelector("[data-media-cast]"),
  castFeedback: document.querySelector("[data-cast-feedback]"),
};

let kioskToken = null;
let lastOverview = null;
let reconnectTimer = null;
let musicZones = [];
let selectedZoneId = null;
let selectedOutputId = null;
let mediaOverview = null;
let ambientTimer = null;
let currentMediaDetail = null;
let podcastOverview = null;
let selectedPodcastPlayerId = null;
let podcastSearchTimer = null;
let podcastSearchRequestId = 0;
let podcastSearchQuery = "";
let podcastSearchResults = [];
let idleTimer = null;
let ambientRotationTimer = null;
let ambientActive = false;
let ambientWakePage = "home";
let ambientFrameIndex = 0;
let currentVaultHeroId = null;

const IDLE_TIMEOUT_MS = 60000;
const AMBIENT_ROTATION_MS = 25000;

function tickClock() {
  const now = new Date();
  els.time.textContent = new Intl.DateTimeFormat("de-DE", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(now);
  els.date.textContent = new Intl.DateTimeFormat("de-DE", {
    weekday: "long",
    day: "2-digit",
    month: "long",
  }).format(now);
}

function tokenFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token");
  if (token) {
    window.localStorage.setItem("vaultKioskToken", token);
    params.delete("token");
    const clean = `${window.location.pathname}${params.toString() ? `?${params}` : ""}`;
    window.history.replaceState({}, "", clean);
    return token;
  }
  return window.localStorage.getItem("vaultKioskToken");
}

async function ensureToken(force = false) {
  if (force) {
    window.localStorage.removeItem("vaultKioskToken");
  }
  const existing = tokenFromLocation();
  if (existing) {
    return existing;
  }
  try {
    const response = await fetch("/kiosk/session", { method: "POST" });
    if (!response.ok) {
      return null;
    }
    const body = await response.json();
    if (body.token) {
      window.localStorage.setItem("vaultKioskToken", body.token);
      return body.token;
    }
  } catch {
    return null;
  }
  return null;
}

function clearToken() {
  kioskToken = null;
  window.localStorage.removeItem("vaultKioskToken");
}

function setConnection(label, online = false) {
  els.connection.textContent = label;
  els.connection.classList.toggle("online", online);
}

const PAGE_ORDER = Array.from(els.navButtons).map((button) => button.dataset.nav);
let currentPageIndex = 0;

function showPage(pageId, direction = null) {
  const index = PAGE_ORDER.indexOf(pageId);
  if (index !== -1) {
    currentPageIndex = index;
  }
  for (const page of els.pages) {
    const isActive = page.dataset.page === pageId;
    page.classList.remove("from-left", "from-right");
    page.classList.toggle("active", isActive);
    if (isActive && direction) {
      void page.offsetWidth; // restart the slide animation
      page.classList.add(direction === "next" ? "from-right" : "from-left");
    }
  }
  for (const button of els.navButtons) {
    button.classList.toggle("active", button.dataset.nav === pageId);
  }
  if (pageId === "music") {
    loadMusic();
  }
  if (pageId === "today") {
    loadToday();
  }
  if (pageId === "podcasts") {
    loadPodcasts();
  }
  if (pageId === "vault") {
    loadVault();
  }
  if (pageId === "ambient") {
    loadAmbient();
  }
}

function goToPage(delta) {
  const next = currentPageIndex + delta;
  if (next < 0 || next >= PAGE_ORDER.length) {
    return;
  }
  showPage(PAGE_ORDER[next], delta > 0 ? "next" : "prev");
}

function activePageId() {
  return PAGE_ORDER[currentPageIndex] || "home";
}

async function api(path, options = {}, retry = true) {
  if (!kioskToken) {
    throw new Error("Token fehlt");
  }
  const response = await fetch(path, {
    ...options,
    headers: {
      "Authorization": `Bearer ${kioskToken}`,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (response.status === 401 && retry) {
    clearToken();
    kioskToken = await ensureToken(true);
    if (kioskToken) {
      return api(path, options, false);
    }
  }
  if (!response.ok) {
    throw new Error(`${path}: ${response.status}`);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function imageUrl(url) {
  if (!url || !kioskToken) {
    return url;
  }
  const absolute = new URL(url, window.location.origin);
  if (absolute.origin !== window.location.origin) {
    return absolute.href;
  }
  absolute.searchParams.set("token", kioskToken);
  return `${absolute.pathname}${absolute.search}`;
}

function temperature(value) {
  if (value === null || value === undefined) {
    return "--";
  }
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 }).format(value);
}

function weatherLabel(state) {
  const labels = {
    cloudy: "wolkig",
    partlycloudy: "leicht bewölkt",
    sunny: "sonnig",
    rainy: "Regen",
    pouring: "Regen",
    clear: "klar",
  };
  return labels[state] || state || "Wetter";
}

function renderOverview(overview) {
  lastOverview = overview;
  els.windowCount.textContent = overview.windows_open;
  els.lightCount.textContent = overview.lights_on;
  els.weatherTemp.textContent = overview.weather.temperature === null ? "--" : `${temperature(overview.weather.temperature)} Grad`;
  els.weatherState.textContent = weatherLabel(overview.weather.state);

  els.lightRooms.innerHTML = "";
  if (!overview.lights.length) {
    els.lightRooms.innerHTML = '<div class="empty">Keine Licht-Räume konfiguriert</div>';
  }
  for (const room of overview.lights) {
    const row = document.createElement("div");
    row.className = "room-row";
    const active = room.state && !["unknown", "aus", "off"].includes(room.state.toLowerCase());
    row.innerHTML = `
      <div>
        <div class="room-name"></div>
        <div class="room-state ${active ? "active" : ""}"></div>
      </div>
      <div class="scene-set"></div>
    `;
    row.querySelector(".room-name").textContent = room.label;
    row.querySelector(".room-state").textContent = room.state === "unknown" ? "unbekannt" : room.state;
    const sceneSet = row.querySelector(".scene-set");
    for (const scene of room.scenes) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `scene ${scene.active ? "active" : ""}`;
      button.textContent = scene.label;
      button.addEventListener("click", () => activateScene(room.id, scene.id));
      sceneSet.append(button);
    }
    els.lightRooms.append(row);
  }

  els.climateCount.textContent = `${overview.climates.length} Thermostate`;
  els.climates.innerHTML = "";
  if (!overview.climates.length) {
    els.climates.innerHTML = '<div class="empty">Keine Thermostate konfiguriert</div>';
  }
  for (const climate of overview.climates) {
    const card = document.createElement("div");
    card.className = "climate-card";
    const target = climate.target_temperature ?? climate.current_temperature;
    card.innerHTML = `
      <div class="climate-name"></div>
      <div class="temp-line">
        <strong></strong>
        <div class="temp-controls">
          <button type="button" class="round" data-step="-0.5">-</button>
          <button type="button" class="round" data-step="0.5">+</button>
        </div>
      </div>
    `;
    card.querySelector(".climate-name").textContent = climate.label;
    card.querySelector("strong").textContent = temperature(target);
    for (const button of card.querySelectorAll("[data-step]")) {
      button.addEventListener("click", () => {
        const step = Number(button.dataset.step);
        const current = climate.target_temperature ?? climate.current_temperature ?? 20;
        setClimate(climate.id, current + step);
      });
    }
    els.climates.append(card);
  }

  els.coffeeLabel.textContent = overview.coffee.label;
  els.coffeeState.textContent = overview.coffee.on ? "An" : (overview.coffee.state === "unknown" ? "unbekannt" : "Aus");
  els.coffeeState.classList.toggle("on", overview.coffee.on);
  els.coffeeToggle.classList.toggle("on", overview.coffee.on);
}

function secondsLabel(value) {
  if (value === null || value === undefined) {
    return "--:--";
  }
  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function renderZones(zones) {
  musicZones = zones;
  if (!selectedZoneId && zones.length) {
    selectedZoneId = zones.find((zone) => zone.state === "playing")?.id || zones[0].id;
  }
  const selected = zones.find((zone) => zone.id === selectedZoneId) || zones[0];
  els.zones.innerHTML = "";
  if (!zones.length) {
    els.zones.innerHTML = '<div class="empty">Keine Roon-Zonen gefunden</div>';
  }
  for (const zone of zones) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `tag ${zone.id === selected?.id ? "active" : ""}`;
    button.textContent = zone.name;
    button.addEventListener("click", () => {
      selectedZoneId = zone.id;
      renderZones(musicZones);
    });
    els.zones.append(button);
  }

  if (!selected) {
    return;
  }
  const now = selected.now_playing || {};
  const output = selected.outputs.find((candidate) => candidate.id === selectedOutputId) || selected.outputs[0];
  selectedOutputId = output?.id || null;
  els.zoneName.textContent = selected.name;
  els.trackTitle.textContent = now.title || "Kein aktiver Titel";
  els.trackSubtitle.textContent = now.subtitle || selected.state;
  els.volumeControl.hidden = !output || output.volume === null || output.volume === undefined;
  els.volumeValue.textContent = output && output.volume !== null && output.volume !== undefined ? `${output.volume}%` : "--";
  els.nowArt.dataset.title = now.title || "Vault";
  if (now.image_url) {
    els.nowArt.style.backgroundImage = `linear-gradient(135deg, rgba(255,255,255,.16), transparent), url("${imageUrl(now.image_url)}")`;
  }
  const pos = now.seek_position || 0;
  const len = now.length || 0;
  els.seekCurrent.textContent = secondsLabel(pos);
  els.seekTotal.textContent = secondsLabel(len);
  els.seekFill.style.width = len ? `${Math.max(0, Math.min(100, pos / len * 100))}%` : "0";
}

function renderAlbums(shelf) {
  els.albumCount.textContent = `${shelf.total || shelf.albums.length} Alben`;
  els.albums.innerHTML = "";
  if (!shelf.albums.length) {
    els.albums.innerHTML = '<div class="empty">Keine Alben gefunden</div>';
  }
  for (const album of shelf.albums.slice(0, 9)) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "album-card";
    if (album.image_url) {
      button.style.backgroundImage = `linear-gradient(0deg, rgba(0,0,0,.58), transparent 56%), url("${imageUrl(album.image_url)}")`;
    }
    const title = document.createElement("span");
    title.textContent = album.title;
    button.append(title);
    button.addEventListener("click", () => playAlbum(album));
    els.albums.append(button);
  }
}

function mediaImage(item) {
  return item.backdrop_url || item.poster_url;
}

function setBackground(el, url, overlay = "linear-gradient(0deg, rgba(0,0,0,.72), transparent 58%)") {
  if (!el || !url) {
    return;
  }
  el.style.backgroundImage = `${overlay}, url("${imageUrl(url)}")`;
}

function makeMediaRow(item) {
  const row = document.createElement("div");
  row.className = "media-row";
  row.innerHTML = `
    <div class="media-thumb"></div>
    <div>
      <div class="media-title"></div>
      <div class="media-subtitle"></div>
    </div>
  `;
  row.querySelector(".media-title").textContent = item.title;
  row.querySelector(".media-subtitle").textContent = item.subtitle || item.type;
  setBackground(row.querySelector(".media-thumb"), item.poster_url || item.backdrop_url);
  row.addEventListener("click", () => openMediaItem(item.id));
  return row;
}

function makeShelfCard(item) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "shelf-card";
  setBackground(button, item.poster_url || item.backdrop_url);
  const title = document.createElement("span");
  title.textContent = item.title;
  button.append(title);
  button.addEventListener("click", () => openMediaItem(item.id));
  return button;
}

function closeMediaDetail() {
  els.mediaVideo.pause();
  els.mediaVideo.removeAttribute("src");
  els.mediaVideo.load();
  currentMediaDetail = null;
  els.mediaOverlay.hidden = true;
}

function renderMediaDetail(item) {
  currentMediaDetail = item;
  els.mediaType.textContent = item.type;
  els.mediaTitle.textContent = item.title;
  els.mediaSubtitle.textContent = item.subtitle || "";
  els.mediaOverviewText.textContent = item.overview || "";
  // No MKV direct-play in the browser. The kiosk plays the trailer on-device
  // and casts the full film to the Apple TV. Video starts hidden until a trailer.
  els.mediaVideo.pause();
  els.mediaVideo.removeAttribute("src");
  els.mediaVideo.hidden = true;
  els.castFeedback.textContent = "";
  els.mediaCast.hidden = !item.playable;
  setBackground(els.mediaOverlay, item.backdrop_url || item.poster_url, "linear-gradient(0deg, rgba(8,8,10,.92), rgba(8,8,10,.58))");
  els.mediaOverlay.hidden = false;
}

async function playTrailer() {
  if (!currentMediaDetail) {
    return;
  }
  els.castFeedback.textContent = "Trailer wird geladen …";
  try {
    const trailer = await api(`/kiosk/media/item/${encodeURIComponent(currentMediaDetail.id)}/trailer`);
    els.mediaVideo.hidden = false;
    els.mediaVideo.src = trailer.url; // public CDN MP4, cross-origin, no token
    els.castFeedback.textContent = "";
    await els.mediaVideo.play();
  } catch {
    els.mediaVideo.hidden = true;
    els.castFeedback.textContent = "Kein Trailer verfügbar";
  }
}

async function castToAppleTv() {
  if (!currentMediaDetail) {
    return;
  }
  els.castFeedback.textContent = "Starte am Apple TV …";
  try {
    await api("/cast/appletv", {
      method: "POST",
      body: JSON.stringify({ item_id: currentMediaDetail.id }),
    });
    els.castFeedback.textContent = "Am Apple TV gestartet";
  } catch {
    els.castFeedback.textContent = "Apple TV nicht erreichbar";
  }
}

async function openMediaItem(itemId) {
  try {
    const item = await api(`/kiosk/media/item/${encodeURIComponent(itemId)}`);
    renderMediaDetail(item);
  } catch {
    // Keep the kiosk calm; the next interaction can try again.
  }
}

async function loadMediaOverview() {
  if (mediaOverview) {
    return mediaOverview;
  }
  mediaOverview = await api("/kiosk/media/overview");
  return mediaOverview;
}

function timeOnly(value, allDay = false) {
  if (!value) {
    return "--";
  }
  if (allDay || /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return "ganztags";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("de-DE", { hour: "2-digit", minute: "2-digit" }).format(date);
}

function makeEventRow(event) {
  const row = document.createElement("div");
  row.className = "agenda-item";
  row.innerHTML = `
    <div class="agenda-time"></div>
    <div>
      <div class="media-title"></div>
      <div class="media-subtitle"></div>
    </div>
  `;
  const end = event.end ? timeOnly(event.end, event.all_day) : "offen";
  row.querySelector(".agenda-time").textContent = event.all_day ? "ganztags" : `${timeOnly(event.start)}-${end}`;
  row.querySelector(".media-title").textContent = event.summary;
  row.querySelector(".media-subtitle").textContent = event.location || event.calendar_label;
  return row;
}

function safeTodoEntity(entityId) {
  return entityId.replaceAll(".", "__");
}

function makeTodoRow(list, item) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "todo-row";
  button.innerHTML = `
    <span class="todo-check"></span>
    <span>
      <strong></strong>
      <small></small>
    </span>
  `;
  button.querySelector("strong").textContent = item.summary;
  button.querySelector("small").textContent = list.label;
  button.addEventListener("click", () => completeTodo(list.entity_id, item.uid || item.summary));
  return button;
}

function renderToday(today, overview) {
  const hour = new Date().getHours();
  els.todayTitle.textContent = hour < 12 ? "Guten Morgen" : hour < 18 ? "Guten Tag" : "Guten Abend";
  const openTodos = today.todos.reduce((sum, list) => sum + list.items.length, 0);
  els.todaySummary.textContent = `${today.events.length} Termine · ${openTodos} offene Punkte · ${overview.windows_open} Fenster offen`;
  els.todayStack.innerHTML = "";
  [
    ["Termine", today.events.length],
    ["Listen", openTodos],
    ["Fenster", overview.windows_open],
    ["Licht", overview.lights_on],
  ].forEach(([label, value]) => {
    const card = document.createElement("div");
    card.className = "stat-card";
    card.innerHTML = "<span></span><strong></strong>";
    card.querySelector("span").textContent = label;
    card.querySelector("strong").textContent = value;
    els.todayStack.append(card);
  });

  els.todayEventCount.textContent = `${today.events.length} Termine`;
  els.todayEvents.innerHTML = "";
  if (!today.events.length) {
    els.todayEvents.innerHTML = '<div class="empty">Heute keine Termine</div>';
  }
  today.events.slice(0, 6).forEach((event) => els.todayEvents.append(makeEventRow(event)));

  els.todayTodoCount.textContent = `${openTodos} offen`;
  els.todayTodos.innerHTML = "";
  const todoItems = today.todos.flatMap((list) => list.items.slice(0, 4).map((item) => ({ list, item })));
  if (!todoItems.length) {
    els.todayTodos.innerHTML = '<div class="empty">Alle Listen sind leer</div>';
  }
  todoItems.slice(0, 8).forEach(({ list, item }) => els.todayTodos.append(makeTodoRow(list, item)));

  els.todayNews.innerHTML = "";
  const headline = document.createElement("strong");
  headline.textContent = today.news.headline || "Kein Briefing";
  const summary = document.createElement("p");
  summary.textContent = today.news.summary || "Noch keine Zusammenfassung vorhanden.";
  els.todayNews.append(headline, summary);
}

async function loadToday() {
  try {
    const [overview, today] = await Promise.all([
      lastOverview ? Promise.resolve(lastOverview) : api("/home/overview"),
      api("/today/overview"),
    ]);
    renderOverview(overview);
    renderToday(today, overview);
  } catch {
    els.todayEvents.innerHTML = '<div class="empty">Heute kann gerade nicht geladen werden</div>';
  }
}

async function completeTodo(entityId, item) {
  const today = await api(`/today/todo/${encodeURIComponent(safeTodoEntity(entityId))}/item`, {
    method: "POST",
    body: JSON.stringify({ item, status: "completed" }),
  });
  const overview = lastOverview || await api("/home/overview");
  renderToday(today, overview);
}

async function loadVault() {
  try {
    const media = await loadMediaOverview();
    const items = [
      ...media.continue_watching,
      ...media.next_up,
      ...media.latest_movies,
      ...media.latest_series,
      ...media.spotlight,
    ];
    const hero = items.find((item) => item.backdrop_url) || items[0];
    currentVaultHeroId = hero?.id || null;
    if (hero) {
      els.vaultStage.disabled = false;
      els.vaultTitle.textContent = hero.title;
      els.vaultSubtitle.textContent = hero.subtitle || "Vault Mediathek";
      setBackground(els.vaultStage, mediaImage(hero), "linear-gradient(0deg, rgba(8,8,10,.84), rgba(8,8,10,.22) 60%)");
    } else {
      els.vaultStage.disabled = true;
      els.vaultTitle.textContent = "Mediathek";
      els.vaultSubtitle.textContent = "Filme und Serien aus Jellyfin";
      els.vaultStage.style.backgroundImage = "";
    }
    const shelf = items.slice(0, 8);
    els.vaultCount.textContent = `${shelf.length} Titel`;
    els.vaultShelves.innerHTML = "";
    if (!shelf.length) {
      els.vaultShelves.innerHTML = '<div class="empty">Keine Vault-Titel gefunden</div>';
    }
    shelf.forEach((item) => els.vaultShelves.append(makeShelfCard(item)));
  } catch {
    currentVaultHeroId = null;
    els.vaultStage.disabled = true;
    els.vaultTitle.textContent = "Mediathek";
    els.vaultSubtitle.textContent = "Filme und Serien aus Jellyfin";
    els.vaultStage.style.backgroundImage = "";
    els.vaultShelves.innerHTML = '<div class="empty">Vault ist gerade nicht erreichbar</div>';
  }
}

async function openVaultHero() {
  if (!currentVaultHeroId) {
    return;
  }
  await openMediaItem(currentVaultHeroId);
}

async function loadPodcasts() {
  try {
    podcastOverview = await api("/podcasts/overview");
    const episodes = podcastOverview.episodes || [];
    const players = podcastOverview.players || [];
    selectedPodcastPlayerId = selectedPodcastPlayerId || podcastOverview.default_player_id || players[0]?.id || null;
    renderPodcastPlayers(players);
    els.podcastCount.textContent = `${episodes.length} Episoden`;
    els.podcasts.innerHTML = "";
    if (!episodes.length) {
      els.podcastTitle.textContent = "Podcasts";
      els.podcastSubtitle.textContent = "Noch keine Feeds konfiguriert";
      els.podcasts.innerHTML = '<div class="empty">Keine Podcast-Feeds eingerichtet</div>';
      return;
    }
    const hero = episodes[0];
    els.podcastTitle.textContent = hero.title;
    els.podcastSubtitle.textContent = hero.feed_title || "Podcast";
    els.podcastArt.dataset.title = hero.title;
    setBackground(els.podcastArt, hero.image_url, "linear-gradient(135deg, rgba(255,255,255,.16), transparent)");
    setBackground(els.podcastStage, hero.image_url, "linear-gradient(75deg, rgba(0,0,0,.82), rgba(0,0,0,.34))");
    episodes.slice(0, 12).forEach((episode) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "album-card";
      setBackground(card, episode.image_url);
      const title = document.createElement("span");
      title.textContent = episode.title;
      card.append(title);
      card.addEventListener("click", () => playPodcastEpisode(episode));
      els.podcasts.append(card);
    });
    if (podcastSearchQuery.trim().length >= 2 && podcastSearchResults.length) {
      renderPodcastSearchResults();
    }
  } catch {
    els.podcasts.innerHTML = '<div class="empty">Podcasts warten auf Music Assistant</div>';
  }
}

function renderPodcastPlayers(players) {
  els.podcastPlayers.innerHTML = "";
  if (!players.length) {
    const empty = document.createElement("div");
    empty.className = "empty small";
    empty.textContent = "Kein Podcast-Player";
    els.podcastPlayers.append(empty);
    return;
  }
  players.forEach((player) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `tag ${player.id === selectedPodcastPlayerId ? "active" : ""}`;
    button.textContent = player.label;
    button.addEventListener("click", () => {
      selectedPodcastPlayerId = player.id;
      renderPodcastPlayers(players);
    });
    els.podcastPlayers.append(button);
  });
}

function subscribedPodcastUrls() {
  return new Set((podcastOverview?.feeds || []).map((feed) => feed.url));
}

function renderPodcastSearchResults() {
  els.podcastSearchResults.innerHTML = "";
  const query = podcastSearchQuery.trim();
  if (query.length < 2) {
    els.podcastSearchStatus.textContent = "Tippe einen Namen";
    els.podcastSearchResults.innerHTML = '<div class="empty">Suche startet ab 2 Zeichen</div>';
    return;
  }
  if (!podcastSearchResults.length) {
    els.podcastSearchStatus.textContent = "Keine Treffer";
    els.podcastSearchResults.innerHTML = '<div class="empty">Keine Podcasts gefunden</div>';
    return;
  }

  const subscribed = subscribedPodcastUrls();
  els.podcastSearchStatus.textContent = `${podcastSearchResults.length} Treffer`;
  for (const result of podcastSearchResults) {
    const row = document.createElement("div");
    row.className = "podcast-result";

    const cover = document.createElement("div");
    cover.className = "podcast-cover";
    cover.dataset.title = result.title;
    if (result.image_url) {
      setBackground(cover, result.image_url, "linear-gradient(135deg, rgba(255,255,255,.16), transparent)");
    }

    const copy = document.createElement("div");
    copy.className = "podcast-result-copy";
    const title = document.createElement("strong");
    title.textContent = result.title;
    const author = document.createElement("span");
    author.textContent = result.author || "Unbekannter Autor";
    const status = document.createElement("small");
    const alreadySubscribed = subscribed.has(result.feed_url);
    status.textContent = alreadySubscribed ? "Bereits abonniert" : result.feed_url;
    copy.append(title, author, status);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "subscribe-action";
    button.textContent = alreadySubscribed ? "Abonniert" : "Abonnieren";
    button.disabled = alreadySubscribed;
    button.addEventListener("click", () => subscribePodcast(result, button));

    row.append(cover, copy, button);
    els.podcastSearchResults.append(row);
  }
}

function queuePodcastSearch(query) {
  podcastSearchQuery = query;
  window.clearTimeout(podcastSearchTimer);
  const trimmed = query.trim();
  if (trimmed.length < 2) {
    podcastSearchResults = [];
    renderPodcastSearchResults();
    return;
  }
  els.podcastSearchStatus.textContent = "Suche läuft …";
  podcastSearchTimer = window.setTimeout(() => runPodcastSearch(trimmed), 250);
}

async function runPodcastSearch(query) {
  const requestId = ++podcastSearchRequestId;
  try {
    const response = await api(`/podcasts/search?q=${encodeURIComponent(query)}`);
    if (requestId !== podcastSearchRequestId) {
      return;
    }
    podcastSearchResults = response.results || [];
    renderPodcastSearchResults();
  } catch {
    if (requestId !== podcastSearchRequestId) {
      return;
    }
    podcastSearchResults = [];
    els.podcastSearchStatus.textContent = "Suche fehlgeschlagen";
    els.podcastSearchResults.innerHTML = '<div class="empty">Podcast-Suche ist gerade nicht erreichbar</div>';
  }
}

async function subscribePodcast(result, button) {
  if (!result?.feed_url) {
    return;
  }
  if (button) {
    button.disabled = true;
    button.textContent = "Abonniere …";
  }
  els.podcastSearchStatus.textContent = "Abonniere …";
  try {
    await api("/podcasts/subscribe", {
      method: "POST",
      body: JSON.stringify({ feed_url: result.feed_url, title: result.title }),
    });
    await loadPodcasts();
    renderPodcastSearchResults();
    els.podcastSearchStatus.textContent = "Abonniert";
  } catch {
    els.podcastSearchStatus.textContent = "Abonnieren fehlgeschlagen";
    renderPodcastSearchResults();
  }
}

async function playPodcastEpisode(episode) {
  if (!selectedPodcastPlayerId) {
    return;
  }
  await api("/podcasts/play", {
    method: "POST",
    body: JSON.stringify({ episode_id: episode.id, player_id: selectedPodcastPlayerId }),
  });
  els.podcastTitle.textContent = episode.title;
  els.podcastSubtitle.textContent = episode.feed_title || "Podcast";
}

async function podcastTransport(action) {
  if (!selectedPodcastPlayerId) {
    return;
  }
  await api("/podcasts/transport", {
    method: "POST",
    body: JSON.stringify({ player_id: selectedPodcastPlayerId, action }),
  });
}

async function loadAmbient() {
  window.clearInterval(ambientRotationTimer);
  try {
    const frames = await ambientFrames();
    if (!frames.length) return;
    ambientFrameIndex = ambientFrameIndex % frames.length;
    const render = () => renderAmbientFrame(frames[ambientFrameIndex++ % frames.length]);
    render();
    ambientTimer = window.setInterval(render, AMBIENT_ROTATION_MS);
  } catch {
    els.ambientSubtitle.textContent = "Ambient wartet auf Vault";
  }
}

async function ambientFrames() {
  const frames = [];
  const [overviewResult, todayResult, musicResult, mediaResult, photosResult] = await Promise.allSettled([
    lastOverview ? Promise.resolve(lastOverview) : api("/home/overview"),
    api("/today/overview"),
    api("/music/zones"),
    loadMediaOverview(),
    api("/photos/overview"),
  ]);

  if (musicResult.status === "fulfilled") {
    const playing = (musicResult.value || []).find((zone) => zone.state === "playing" && zone.now_playing);
    if (playing) {
      frames.push({
        eyebrow: playing.name,
        title: playing.now_playing.title || "Now Playing",
        subtitle: playing.now_playing.subtitle || "Musik",
        image: playing.now_playing.image_url,
      });
      return frames;
    }
  }

  if (overviewResult.status === "fulfilled") {
    const overview = overviewResult.value;
    frames.push({
      eyebrow: "Wohnung",
      title: `${overview.lights_on || 0} Lampen · ${overview.windows_open || 0} Fenster`,
      subtitle: `${overview.weather?.temperature ?? "--"}° · ${overview.weather?.state || "Wetter"}`,
    });
  }

  if (todayResult.status === "fulfilled") {
    const today = todayResult.value;
    frames.push({
      eyebrow: "Heute",
      title: today.news?.headline || `${(today.events || []).length} Termine`,
      subtitle: today.news?.summary || `${(today.todos || []).reduce((sum, list) => sum + (list.items || []).length, 0)} offene Todos`,
    });
  }

  if (photosResult.status === "fulfilled") {
    const photos = photosResult.value.photos || [];
    const photo = photos[ambientFrameIndex % Math.max(photos.length, 1)];
    if (photo) {
      frames.push({
        eyebrow: "Foto",
        title: photo.title || "Immich",
        subtitle: photo.taken_at ? new Date(photo.taken_at).toLocaleDateString("de-DE") : "Immich",
        image: photo.image_url,
      });
    }
  }

  if (mediaResult.status === "fulfilled") {
    const media = mediaResult.value;
    const items = [...media.spotlight, ...media.latest_movies, ...media.latest_series].filter((item) => mediaImage(item));
    const item = items[ambientFrameIndex % Math.max(items.length, 1)];
    if (item) {
      frames.push({
        eyebrow: "Vault",
        title: item.title,
        subtitle: item.subtitle || "Cover-Art im Wandmodus",
        image: mediaImage(item),
      });
    }
  }
  return frames;
}

function renderAmbientFrame(frame) {
  const eyebrow = els.ambientCanvas.querySelector(".eyebrow");
  if (eyebrow) eyebrow.textContent = frame.eyebrow || "Ambient";
  els.ambientTitle.textContent = frame.title || "Ambient";
  els.ambientSubtitle.textContent = frame.subtitle || "";
  const fallback = frame.image
    ? "linear-gradient(0deg, rgba(8,8,10,.86), rgba(8,8,10,.2) 62%)"
    : "linear-gradient(145deg, rgba(22,25,31,.98), rgba(36,34,29,.94))";
  setBackground(els.ambientCanvas, frame.image, fallback);
}

function resetIdleTimer() {
  window.clearTimeout(idleTimer);
  if (ambientActive) {
    return;
  }
  idleTimer = window.setTimeout(beginAmbientMode, IDLE_TIMEOUT_MS);
}

function beginAmbientMode() {
  if (ambientActive || !els.mediaOverlay.hasAttribute("hidden")) {
    resetIdleTimer();
    return;
  }
  ambientActive = true;
  ambientWakePage = activePageId() === "ambient" ? "home" : activePageId();
  showPage("ambient", "next");
}

function endAmbientMode() {
  if (!ambientActive) {
    resetIdleTimer();
    return;
  }
  ambientActive = false;
  window.clearInterval(ambientTimer);
  window.clearInterval(ambientRotationTimer);
  showPage(ambientWakePage || "home", "prev");
  resetIdleTimer();
}

function noteInteraction(event) {
  if (ambientActive) {
    event.preventDefault();
    event.stopImmediatePropagation();
    endAmbientMode();
    return;
  }
  resetIdleTimer();
}

async function loadMusic() {
  const [zonesResult, albumsResult] = await Promise.allSettled([
    api("/music/zones"),
    api("/music/albums?limit=24"),
  ]);
  if (zonesResult.status === "fulfilled") {
    renderZones(zonesResult.value);
  } else {
    els.zones.innerHTML = '<div class="empty">Roon-Zonen warten auf Verbindung</div>';
  }
  if (albumsResult.status === "fulfilled") {
    renderAlbums(albumsResult.value);
  } else {
    els.albums.innerHTML = '<div class="empty">Plattenregal wartet auf Roon</div>';
  }
}

async function loadOverview() {
  try {
    const overview = await api("/home/overview");
    renderOverview(overview);
  } catch (error) {
    setConnection("Degradiert");
    els.lightRooms.innerHTML = '<div class="empty">Home Assistant ist noch nicht verbunden</div>';
    els.climates.innerHTML = '<div class="empty">Klima wartet auf Home Assistant</div>';
  }
}

async function activateScene(roomId, sceneId) {
  await api(`/home/lights/${encodeURIComponent(roomId)}/scenes/${encodeURIComponent(sceneId)}`, {
    method: "POST",
  });
  await loadOverview();
}

async function setClimate(climateId, targetTemperature) {
  const overview = await api(`/home/climate/${encodeURIComponent(climateId)}`, {
    method: "POST",
    body: JSON.stringify({ target_temperature: targetTemperature }),
  });
  renderOverview(overview);
}

async function setCoffee(on) {
  const overview = await api("/home/coffee", {
    method: "POST",
    body: JSON.stringify({ on }),
  });
  renderOverview(overview);
}

async function transport(action) {
  if (!selectedZoneId) {
    return;
  }
  await api("/music/transport", {
    method: "POST",
    body: JSON.stringify({ zone_id: selectedZoneId, action }),
  });
  await loadMusic();
}

async function setVolume(step) {
  const zone = musicZones.find((candidate) => candidate.id === selectedZoneId);
  const output = zone?.outputs.find((candidate) => candidate.id === selectedOutputId) || zone?.outputs[0];
  if (!zone || !output || output.volume === null || output.volume === undefined) {
    return;
  }
  const volume = Math.max(0, Math.min(100, output.volume + step));
  await api("/music/transport", {
    method: "POST",
    body: JSON.stringify({
      zone_id: zone.id,
      action: "volume",
      output_id: output.id,
      volume,
    }),
  });
  await loadMusic();
}

async function playAlbum(album) {
  const zoneId = selectedZoneId || musicZones[0]?.id;
  if (!zoneId) {
    return;
  }
  await api("/music/play", {
    method: "POST",
    body: JSON.stringify({
      zone_id: zoneId,
      item_key: album.item_key,
      album_index: album.album_index,
    }),
  });
  await loadMusic();
}

function connectRealtime() {
  if (!kioskToken) {
    setConnection("Token fehlt");
    return;
  }
  window.clearTimeout(reconnectTimer);
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${window.location.host}/realtime?token=${encodeURIComponent(kioskToken)}`);
  socket.addEventListener("open", () => setConnection("Live", true));
  socket.addEventListener("message", (event) => {
    try {
      const message = JSON.parse(event.data);
      if (message.type && message.type.startsWith("home.")) {
        loadOverview();
      }
    } catch {
      // Ignore malformed realtime frames; the next poll will repair state.
    }
  });
  socket.addEventListener("close", () => {
    setConnection("Offline");
    reconnectTimer = window.setTimeout(connectRealtime, 3000);
  });
}

els.coffeeToggle.addEventListener("click", () => setCoffee(!(lastOverview && lastOverview.coffee.on)));
els.refreshMusic.addEventListener("click", loadMusic);
els.closeMedia.addEventListener("click", closeMediaDetail);
els.mediaTrailer.addEventListener("click", playTrailer);
els.mediaCast.addEventListener("click", castToAppleTv);
els.vaultStage.addEventListener("click", openVaultHero);
els.mediaOverlay.addEventListener("click", (event) => {
  if (event.target === els.mediaOverlay) {
    closeMediaDetail();
  }
});
for (const button of els.navButtons) {
  button.addEventListener("click", () => showPage(button.dataset.nav));
}
for (const eventName of ["pointerdown", "touchstart", "keydown"]) {
  document.addEventListener(eventName, noteInteraction, { capture: true });
}

// Horizontal swipe to move between pages — primary navigation on the Pi touch
// panel; the dots stay as an indicator. Ignore drags that start on interactive
// controls (sliders, buttons, video) or while the media overlay is open.
const swipeSurface = document.querySelector(".shell");
let swipeStartX = null;
let swipeStartY = null;
swipeSurface.addEventListener(
  "touchstart",
  (event) => {
    swipeStartX = null;
    if (event.touches.length !== 1) {
      return;
    }
    if (!els.mediaOverlay.hasAttribute("hidden")) {
      return;
    }
    if (event.target.closest("button, input, video, .bar, .switch, .album-grid, .shelf-grid")) {
      return;
    }
    swipeStartX = event.touches[0].clientX;
    swipeStartY = event.touches[0].clientY;
  },
  { passive: true },
);
swipeSurface.addEventListener(
  "touchend",
  (event) => {
    if (swipeStartX === null) {
      return;
    }
    const touch = event.changedTouches[0];
    const dx = touch.clientX - swipeStartX;
    const dy = touch.clientY - swipeStartY;
    swipeStartX = null;
    if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.4) {
      goToPage(dx < 0 ? 1 : -1);
    }
  },
  { passive: true },
);
for (const button of document.querySelectorAll("[data-transport]")) {
  button.addEventListener("click", () => transport(button.dataset.transport));
}
for (const button of els.volumeButtons) {
  button.addEventListener("click", () => setVolume(Number(button.dataset.volumeStep)));
}
for (const button of els.podcastTransportButtons) {
  button.addEventListener("click", () => podcastTransport(button.dataset.podcastTransport));
}
if (els.podcastSearchInput) {
  els.podcastSearchInput.addEventListener("input", () => queuePodcastSearch(els.podcastSearchInput.value));
}
if (els.podcastSearchForm) {
  els.podcastSearchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    queuePodcastSearch(els.podcastSearchInput?.value || "");
  });
}
if (els.podcastSearchClear) {
  els.podcastSearchClear.addEventListener("click", () => {
    if (els.podcastSearchInput) {
      els.podcastSearchInput.value = "";
      els.podcastSearchInput.focus();
    }
    podcastSearchQuery = "";
    podcastSearchResults = [];
    window.clearTimeout(podcastSearchTimer);
    renderPodcastSearchResults();
  });
}
els.allOff.addEventListener("click", async () => {
  if (!lastOverview) {
    return;
  }
  const offCalls = [];
  for (const room of lastOverview.lights) {
    const offScene = room.scenes.find((scene) => scene.label.toLowerCase() === "aus" || scene.id === "aus");
    if (offScene) {
      offCalls.push(activateScene(room.id, offScene.id));
    }
  }
  await Promise.all(offCalls);
});

async function boot() {
  kioskToken = await ensureToken();
  tickClock();
  window.setInterval(tickClock, 1000);
  connectRealtime();
  loadOverview();
  window.setInterval(loadOverview, 30000);
  resetIdleTimer();
}

boot();
