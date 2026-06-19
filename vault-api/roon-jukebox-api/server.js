"use strict";

const RoonApi          = require("node-roon-api");
const RoonApiTransport = require("node-roon-api-transport");
const RoonApiBrowse    = require("node-roon-api-browse");
const RoonApiImage     = require("node-roon-api-image");
const RoonApiStatus    = require("node-roon-api-status");
const express          = require("express");
const cors             = require("cors");
const fs               = require("fs");
const path             = require("path");

const PORT      = process.env.PORT      || 3085;
const ROON_HOST = process.env.ROON_HOST || null;
const ROON_PORT = process.env.ROON_PORT || 9100;
const ROON_STATE_FILE = process.env.ROON_STATE_FILE || path.join(process.cwd(), "config.json");
const DEFAULT_LIMIT = 50;
const MAX_LIMIT     = 200;
const SEARCH_SCAN_LIMIT = 1000;

let transport = null;
let browse    = null;
let image     = null;
let connected = false;
let core      = null;
let zones     = {};
let queueSubscriptions = {};
let queueCache = {};

// svcStatus wird nach roon initialisiert (zirkuläre Abhängigkeit vermeiden)
let svcStatus = null;

function readRoonState() {
  try {
    return JSON.parse(fs.readFileSync(ROON_STATE_FILE, "utf8")) || {};
  } catch (err) {
    return {};
  }
}

function writeRoonState(state) {
  try {
    fs.mkdirSync(path.dirname(ROON_STATE_FILE), { recursive: true });
    fs.writeFileSync(ROON_STATE_FILE, JSON.stringify(state || {}, null, 2));
  } catch (err) {
    console.error("[roon] Persistenz konnte nicht geschrieben werden:", err.message);
  }
}

function rememberQueue(zoneId, data) {
  const current = queueCache[zoneId] || { items: [], last_update: null, raw: null };
  const items = Array.isArray(data.items)
    ? data.items
    : Array.isArray(data.queue_items)
      ? data.queue_items
      : current.items;
  queueCache[zoneId] = {
    ...current,
    ...data,
    items,
    zone_id: zoneId,
    last_update: new Date().toISOString(),
    raw: data,
  };
}

function ensureQueueSubscription(zoneId) {
  if (!transport || !zoneId || queueSubscriptions[zoneId]) return;
  queueSubscriptions[zoneId] = true;
  try {
    transport.subscribe_queue(zoneId, 80, (cmd, data = {}) => {
      rememberQueue(zoneId, { command: cmd, ...data });
    });
  } catch (err) {
    delete queueSubscriptions[zoneId];
    console.error("[queue]", err.message);
  }
}

const roon = new RoonApi({
  extension_id:    "de.jancloud.jukebox",
  display_name:    "Jukebox",
  display_version: "1.0.0",
  publisher:       "Jan",
  email:           "",
  website:         "",
  get_persisted_state: readRoonState,
  set_persisted_state: writeRoonState,

  core_paired(c) {
    console.log("[roon] Paired:", c.display_name);
    core      = c;
    transport = c.services.RoonApiTransport;
    browse    = c.services.RoonApiBrowse;
    image     = c.services.RoonApiImage;
    connected = true;
    if (svcStatus) svcStatus.set_status("Verbunden", false);

    transport.subscribe_zones((cmd, data) => {
      if (cmd === "Subscribed") {
        data.zones.forEach(z => {
          zones[z.zone_id] = z;
          ensureQueueSubscription(z.zone_id);
        });
      } else if (cmd === "Changed") {
        (data.zones_changed || []).forEach(z => {
          zones[z.zone_id] = z;
          ensureQueueSubscription(z.zone_id);
        });
        (data.zones_added || []).forEach(z => {
          zones[z.zone_id] = z;
          ensureQueueSubscription(z.zone_id);
        });
        (data.zones_removed || []).forEach(z => {
          const zoneId = typeof z === "string" ? z : z.zone_id;
          delete zones[zoneId];
          delete queueCache[zoneId];
          delete queueSubscriptions[zoneId];
        });
      }
    });
  },

  core_unpaired(c) {
    console.log("[roon] Unpaired:", c.display_name);
    connected = false;
    core = null; transport = null; browse = null; image = null; zones = {};
    queueSubscriptions = {};
    queueCache = {};
    if (svcStatus) svcStatus.set_status("Nicht verbunden", true);
  },
});

svcStatus = new RoonApiStatus(roon);

roon.init_services({
  required_services: [RoonApiTransport, RoonApiBrowse, RoonApiImage],
  provided_services: [svcStatus],
});

if (ROON_HOST) {
  console.log("[roon] Verbinde mit", ROON_HOST + ":" + ROON_PORT);
  roon.ws_connect({ host: ROON_HOST, port: parseInt(ROON_PORT) });
} else {
  console.log("[roon] Starte Autodiscovery ...");
  roon.start_discovery();
}

// ── Helpers ────────────────────────────────────────────────────────────────

function requireConnected(res) {
  if (!connected) {
    res.status(503).json({ error: "Keine Verbindung zur Roon Core" });
    return false;
  }
  return true;
}

function createSessionKey(prefix) {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

function normalizeText(value) {
  return String(value || "").trim().toLowerCase();
}

function parsePositiveInt(value, fallback, max = Number.MAX_SAFE_INTEGER) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 0) return fallback;
  return Math.min(parsed, max);
}

function browseAsync(options) {
  return new Promise((resolve, reject) => {
    browse.browse(options, (err, result) => {
      if (err) return reject(err);
      resolve(result || {});
    });
  });
}

function loadAsync(options) {
  return new Promise((resolve, reject) => {
    browse.load(options, (err, result) => {
      if (err) return reject(err);
      resolve(result || {});
    });
  });
}

function transportControlAsync(zoneId, action) {
  return new Promise((resolve, reject) => {
    transport.control(zoneId, action, (err) => {
      if (err) return reject(err);
      resolve();
    });
  });
}

function transportPauseAllAsync() {
  return new Promise((resolve, reject) => {
    transport.pause_all((err) => {
      if (err) return reject(err);
      resolve();
    });
  });
}

function transportMuteAllAsync(how) {
  return new Promise((resolve, reject) => {
    transport.mute_all(how, (err) => {
      if (err) return reject(err);
      resolve();
    });
  });
}

function transportChangeVolumeAsync(outputId, how, value) {
  return new Promise((resolve, reject) => {
    transport.change_volume(outputId, how, value, (err) => {
      if (err) return reject(err);
      resolve();
    });
  });
}

function transportMuteAsync(outputId, how) {
  return new Promise((resolve, reject) => {
    transport.mute(outputId, how, (err) => {
      if (err) return reject(err);
      resolve();
    });
  });
}

function transportGroupOutputsAsync(outputIds) {
  return new Promise((resolve, reject) => {
    transport.group_outputs(outputIds, (err) => {
      if (err) return reject(err);
      resolve();
    });
  });
}

function transportUngroupOutputsAsync(outputIds) {
  return new Promise((resolve, reject) => {
    transport.ungroup_outputs(outputIds, (err) => {
      if (err) return reject(err);
      resolve();
    });
  });
}

function transportTransferZoneAsync(fromZoneId, toZoneId) {
  return new Promise((resolve, reject) => {
    transport.transfer_zone(fromZoneId, toZoneId, (err) => {
      if (err) return reject(err);
      resolve();
    });
  });
}

function transportChangeSettingsAsync(zoneId, settings) {
  return new Promise((resolve, reject) => {
    transport.change_settings(zoneId, settings, (err) => {
      if (err) return reject(err);
      resolve();
    });
  });
}

function transportOutputPowerAsync(outputId, action, controlKey = null) {
  return new Promise((resolve, reject) => {
    const opts = controlKey ? { control_key: controlKey } : {};
    const callback = (err) => {
      if (err) return reject(err);
      resolve();
    };
    if (action === "standby") return transport.standby(outputId, opts, callback);
    if (action === "toggle_standby") return transport.toggle_standby(outputId, opts, callback);
    if (action === "convenience_switch") return transport.convenience_switch(outputId, opts, callback);
    reject(new Error("Unbekannte Output-Aktion: " + action));
  });
}

function transportPlayFromHereAsync(zoneId, queueItemId) {
  return new Promise((resolve, reject) => {
    transport.play_from_here(zoneId, queueItemId, (msg, body) => {
      if (msg && msg.name === "Success") return resolve(body || {});
      reject(new Error(msg ? msg.name : "NetworkError"));
    });
  });
}

function getListCount(result, fallback = 20) {
  return result && result.list && Number.isFinite(Number(result.list.count))
    ? Number(result.list.count)
    : fallback;
}

function scoreMenuItem(item, keywords) {
  const title = normalizeText(item.title);
  const subtitle = normalizeText(item.subtitle);
  return keywords.reduce((score, keyword) => {
    const normalized = normalizeText(keyword);
    if (title === normalized) return score + 10;
    if (title.includes(normalized)) return score + 5;
    if (subtitle.includes(normalized)) return score + 1;
    return score;
  }, 0);
}

function findBestMenuItem(items, keywords) {
  return (items || [])
    .map(item => ({ item, score: scoreMenuItem(item, keywords) }))
    .filter(entry => entry.score > 0)
    .sort((a, b) => b.score - a.score)[0]?.item || null;
}

function albumToDto(item, albumIndex = null) {
  return {
    item_key:  item.item_key,
    album_index: albumIndex,
    title:     item.title || "",
    subtitle:  item.subtitle || "",
    image_key: item.image_key || null,
    hint:      item.hint || null,
    is_playable: Boolean(item.item_key),
  };
}

function itemToDto(item) {
  return {
    item_key:  item.item_key,
    title:     item.title || "",
    subtitle:  item.subtitle || "",
    image_key: item.image_key || null,
    hint:      item.hint || null,
    input_prompt: item.input_prompt || null,
    parent_title: item.parent_title || null,
  };
}

function searchItemToDto(item, sessionKey) {
  return {
    ...itemToDto(item),
    hierarchy: "search",
    browser_session_key: item.browser_session_key || sessionKey,
    image_url: item.image_key ? `/api/image/${encodeURIComponent(item.image_key)}?width=500&height=500` : null,
  };
}

function albumSearchResultToDto(item, albumIndex) {
  return {
    ...albumToDto(item, item.album_index ?? albumIndex),
    image_url: item.image_key ? `/api/image/${encodeURIComponent(item.image_key)}?width=500&height=500` : null,
  };
}

function queueItemToDto(item) {
  const lines = item.three_line || item.two_line || item.one_line || {};
  return {
    queue_item_id: item.queue_item_id || item.queue_id || item.id || null,
    title: item.title || lines.line1 || "",
    subtitle: item.subtitle || lines.line2 || "",
    detail: lines.line3 || "",
    image_key: item.image_key || null,
    length: item.length || 0,
    raw: item,
  };
}

function filterAlbums(items, query) {
  const normalizedQuery = normalizeText(query);
  if (!normalizedQuery) return items;

  const terms = normalizedQuery.split(/\s+/).filter(Boolean);
  return items.filter(item => {
    const haystack = normalizeText(`${item.title || ""} ${item.subtitle || ""}`);
    return terms.every(term => haystack.includes(term));
  });
}

async function loadItems(hierarchy, multiSessionKey, result, offset = 0, count = DEFAULT_LIMIT) {
  const requestedCount = Math.max(0, Math.min(Number(count), getListCount(result, count)));
  if (requestedCount === 0) return [];
  const loaded = await loadAsync({
    hierarchy,
    multi_session_key: multiSessionKey,
    offset: Number(offset),
    count: requestedCount,
  });
  return loaded.items || [];
}

async function findAlbumBrowser(multiSessionKey) {
  return browseAsync({
    hierarchy: "albums",
    multi_session_key: multiSessionKey,
    pop_all: true,
  });
}

async function fetchAlbums({ query = "", offset = 0, limit = DEFAULT_LIMIT } = {}) {
  const sessionKey = createSessionKey("albums");
  const safeOffset = parsePositiveInt(offset, 0);
  const safeLimit = parsePositiveInt(limit, DEFAULT_LIMIT, MAX_LIMIT);
  const albumsResult = await findAlbumBrowser(sessionKey);
  const total = getListCount(albumsResult, 0);

  if (normalizeText(query)) {
    const scanCount = Math.min(total, SEARCH_SCAN_LIMIT);
    const scannedItems = await loadItems("albums", sessionKey, albumsResult, 0, scanCount);
    const indexedItems = scannedItems.map((item, index) => ({ ...item, album_index: index }));
    const filteredItems = filterAlbums(indexedItems, query);
    return {
      items: filteredItems.slice(safeOffset, safeOffset + safeLimit),
      total: filteredItems.length,
      offset: safeOffset,
      limit: safeLimit,
      scanned: scanCount,
      complete: scanCount >= total,
    };
  }

  const items = (await loadItems("albums", sessionKey, albumsResult, safeOffset, safeLimit))
    .map((item, index) => ({ ...item, album_index: safeOffset + index }));
  return {
    items,
    total,
    offset: safeOffset,
    limit: safeLimit,
    scanned: items.length,
    complete: true,
  };
}

async function searchRoon({ query, offset = 0, limit = DEFAULT_LIMIT } = {}) {
  const normalizedQuery = String(query || "").trim();
  if (!normalizedQuery) {
    throw new Error("query erforderlich");
  }

  const sessionKey = createSessionKey("search");
  const safeOffset = parsePositiveInt(offset, 0);
  const safeLimit = parsePositiveInt(limit, DEFAULT_LIMIT, MAX_LIMIT);
  const result = await browseAsync({
    hierarchy: "search",
    multi_session_key: sessionKey,
    pop_all: true,
    input: normalizedQuery,
  });

  if (result.action !== "list") {
    return {
      source: "roon",
      title: result.title || null,
      subtitle: result.subtitle || null,
      items: [],
      total: 0,
      offset: safeOffset,
      limit: safeLimit,
      action: result.action || null,
    };
  }

  const total = getListCount(result, 0);
  const rootItems = await loadItems("search", sessionKey, result, 0, Math.min(total, 12));
  const expandedItems = await expandRoonSearchCategories(normalizedQuery, rootItems, safeLimit);
  const items = expandedItems.length
    ? expandedItems.slice(safeOffset, safeOffset + safeLimit)
    : rootItems.slice(safeOffset, safeOffset + safeLimit);
  return {
    source: "roon",
    session_key: sessionKey,
    title: result.list ? result.list.title || null : null,
    subtitle: result.list ? result.list.subtitle || null : null,
    hint: result.list ? result.list.hint || null : null,
    items,
    total: expandedItems.length || total,
    offset: safeOffset,
    limit: safeLimit,
    action: result.action || null,
    expanded: Boolean(expandedItems.length),
  };
}

function isExpandableSearchCategory(item) {
  const hint = normalizeText(item && item.hint);
  const title = normalizeText(item && item.title);
  if (!item || !item.item_key) return false;
  if (hint && !hint.includes("list")) return false;
  return [
    "albums",
    "album",
    "tracks",
    "songs",
    "artists",
    "performers",
    "composers",
    "playlists",
  ].some(term => title.includes(term));
}

function searchCategoryPriority(item) {
  const title = normalizeText(item && item.title);
  if (title.includes("album")) return 0;
  if (title.includes("track") || title.includes("song")) return 1;
  if (title.includes("playlist")) return 2;
  if (title.includes("artist") || title.includes("performer")) return 3;
  return 4;
}

async function expandOneRoonSearchCategory(query, category, categoryIndex, childLimit) {
  const childSessionKey = createSessionKey("search");
  const root = await browseAsync({
    hierarchy: "search",
    multi_session_key: childSessionKey,
    pop_all: true,
    input: query,
  });
  if (root.action !== "list") return [];

  const rootItems = await loadItems("search", childSessionKey, root, 0, Math.min(getListCount(root, 0), 12));
  const matching = rootItems.find(item => item.title === category.title)
    || rootItems[categoryIndex]
    || null;
  if (!matching || !matching.item_key) return [];

  const branch = await browseAsync({
    hierarchy: "search",
    multi_session_key: childSessionKey,
    item_key: matching.item_key,
  });
  if (branch.action !== "list") return [];

  const items = await loadItems("search", childSessionKey, branch, 0, childLimit);
  return items.map(item => ({
    ...item,
    parent_title: matching.title || category.title || "Roon",
    browser_session_key: childSessionKey,
  }));
}

async function expandRoonSearchCategories(query, rootItems, limit) {
  const categories = rootItems
    .map((item, index) => ({ item, index }))
    .filter(entry => isExpandableSearchCategory(entry.item))
    .sort((a, b) => searchCategoryPriority(a.item) - searchCategoryPriority(b.item))
    .slice(0, 4);
  if (!categories.length) return [];

  const childLimit = Math.max(8, Math.ceil(limit / categories.length));
  const expanded = [];
  for (const entry of categories) {
    try {
      const items = await expandOneRoonSearchCategory(query, entry.item, entry.index, childLimit);
      expanded.push(...items);
    } catch (err) {
      console.error("[search expand]", entry.item.title || entry.index, err.message);
    }
  }

  return expanded.filter(item => item && item.item_key);
}

async function searchAlbumsFallback({ query, offset = 0, limit = DEFAULT_LIMIT } = {}) {
  const result = await fetchAlbums({ query, offset, limit });
  return {
    source: "albums",
    title: "Albums",
    subtitle: null,
    hint: null,
    items: result.items,
    total: result.total,
    offset: result.offset,
    limit: result.limit,
    action: "list",
    scanned: result.scanned,
    complete: result.complete,
  };
}

function albumIndexFromItemKey(itemKey) {
  const match = String(itemKey || "").match(/^\d+:(\d+)$/);
  return match ? Number.parseInt(match[1], 10) : null;
}

async function resolveAlbumItem(sessionKey, itemKey, albumIndex) {
  const parsedIndex = albumIndex != null ? Number.parseInt(albumIndex, 10) : albumIndexFromItemKey(itemKey);
  if (!Number.isFinite(parsedIndex) || parsedIndex < 0) {
    return { item_key: itemKey };
  }

  const albumsResult = await findAlbumBrowser(sessionKey);
  const items = await loadItems("albums", sessionKey, albumsResult, parsedIndex, 1);
  if (!items[0] || !items[0].item_key) {
    throw new Error("Album nicht gefunden");
  }
  return items[0];
}

async function fetchAlbumDetails(itemKey, albumIndex = null) {
  const sessionKey = createSessionKey("album");
  const albumItem = await resolveAlbumItem(sessionKey, itemKey, albumIndex);
  const result = await browseAsync({
    hierarchy: "albums",
    multi_session_key: sessionKey,
    item_key: albumItem.item_key,
  });
  const items = result.action === "list"
    ? await loadItems("albums", sessionKey, result, 0, getListCount(result))
    : [];

  return {
    action: result.action || null,
    title: result.title || albumItem.title || null,
    subtitle: result.subtitle || albumItem.subtitle || null,
    items,
  };
}

function findPlayAction(items) {
  const actionItems = (items || []).filter(item => String(item.hint || "").startsWith("action"));
  const explicitPlayTerms = [
    "play album",
    "play now",
    "jetzt spielen",
    "abspielen",
    "wiedergabe starten",
  ];

  const explicitMatch = findBestMenuItem(actionItems, explicitPlayTerms);
  if (explicitMatch) return explicitMatch;

  return actionItems.find(item => {
    const title = normalizeText(item.title);
    return title === "play" || title === "spielen";
  }) || null;
}

function findPlayableChild(items) {
  const list = items || [];
  return list.find(item => String(item.hint || "").startsWith("action"))
    || (list.length === 1 && list[0].item_key ? list[0] : null)
    || list.find(item => item.item_key && String(item.hint || "").includes("list"))
    || null;
}

function isFinalPlayAction(item) {
  const title = normalizeText(item && item.title);
  return title === "play now"
    || title === "jetzt spielen"
    || title === "spielen"
    || title === "play";
}

function requireZone(zoneId, res) {
  if (!zones[zoneId]) {
    res.status(404).json({ error: "Zone nicht gefunden" });
    return false;
  }
  return true;
}

function outputById(outputId) {
  for (const zone of Object.values(zones)) {
    const output = (zone.outputs || []).find(o => o.output_id === outputId);
    if (output) return output;
  }
  return null;
}

function requireOutput(outputId, res) {
  if (!outputById(outputId)) {
    res.status(404).json({ error: "Output nicht gefunden" });
    return false;
  }
  return true;
}

async function playItem(zoneId, itemKey, albumIndex = null) {
  const sessionKey = createSessionKey("play");
  const albumItem = await resolveAlbumItem(sessionKey, itemKey, albumIndex);
  let result = await browseAsync({
    hierarchy: "albums",
    multi_session_key: sessionKey,
    item_key: albumItem.item_key,
    zone_or_output_id: zoneId,
  });

  if (result.action !== "list") {
    return { ok: true, action: result.action || null };
  }

  for (let depth = 0; depth < 3; depth += 1) {
    const items = await loadItems("albums", sessionKey, result, 0, getListCount(result));
    const playNow = findPlayAction(items);
    if (!playNow) {
      throw new Error("Play-Aktion nicht gefunden");
    }

    result = await browseAsync({
      hierarchy: "albums",
      multi_session_key: sessionKey,
      item_key: playNow.item_key,
      zone_or_output_id: zoneId,
    });

    if (isFinalPlayAction(playNow)) {
      await transportControlAsync(zoneId, "play");
      return { ok: true, action: "play", play_action: playNow.title || null };
    }

    if (result.action !== "list") {
      return { ok: true, action: result.action || "play", play_action: playNow.title || null };
    }
  }

  throw new Error("Play-Aktion nicht eindeutig auflösbar");
}

async function playBrowserItem(zoneId, hierarchy, sessionKey, itemKey) {
  if (!hierarchy || !sessionKey || !itemKey) {
    throw new Error("hierarchy, browserSessionKey und itemKey erforderlich");
  }

  let result = await browseAsync({
    hierarchy,
    multi_session_key: sessionKey,
    item_key: itemKey,
    zone_or_output_id: zoneId,
  });

  if (result.action !== "list") {
    await transportControlAsync(zoneId, "play");
    return { ok: true, action: result.action || "play" };
  }

  for (let depth = 0; depth < 3; depth += 1) {
    const items = await loadItems(hierarchy, sessionKey, result, 0, getListCount(result));
    const playNow = findPlayAction(items) || findPlayableChild(items);
    if (!playNow || !playNow.item_key) {
      throw new Error("Dieser Roon-Treffer ist keine direkt abspielbare Platte");
    }

    result = await browseAsync({
      hierarchy,
      multi_session_key: sessionKey,
      item_key: playNow.item_key,
      zone_or_output_id: zoneId,
    });

    if (isFinalPlayAction(playNow)) {
      await transportControlAsync(zoneId, "play");
      return { ok: true, action: "play", play_action: playNow.title || null };
    }

    if (result.action !== "list") {
      await transportControlAsync(zoneId, "play");
      return { ok: true, action: result.action || "play", play_action: playNow.title || null };
    }
  }

  throw new Error("Roon-Treffer nicht eindeutig abspielbar");
}

// ── Express ────────────────────────────────────────────────────────────────

const app = express();
app.use(cors());
app.use(express.json());

app.use(express.static("public"));

app.get("/api", (req, res) => {
  res.json({
    name: "Roon Jukebox API",
    status_url: "/api/status",
    albums_url: "/api/albums?offset=0&limit=50",
    zones_url: "/api/zones",
    queue_url: "/api/queue/:zoneId",
    system_url: "/api/system",
  });
});

app.get("/api/status", (req, res) => {
  res.json({ connected, core_name: core ? core.display_name : null, zone_count: Object.keys(zones).length });
});

app.get("/api/zones", (req, res) => {
  if (!requireConnected(res)) return;
  const list = Object.values(zones).map(z => ({
    zone_id:      z.zone_id,
    display_name: z.display_name,
    state:        z.state,
    now_playing:  z.now_playing ? {
      title:         (z.now_playing.two_line || {}).line1 || "",
      subtitle:      (z.now_playing.two_line || {}).line2 || "",
      image_key:     z.now_playing.image_key || null,
      seek_position: z.now_playing.seek_position || 0,
      length:        z.now_playing.length || 0,
    } : null,
    queue_items_remaining: z.queue_items_remaining || 0,
    queue_time_remaining: z.queue_time_remaining || 0,
    settings: z.settings || {},
    outputs: (z.outputs || []).map(o => ({
      output_id: o.output_id,
      zone_id: o.zone_id,
      display_name: o.display_name,
      volume: o.volume || null,
      can_group_with_output_ids: o.can_group_with_output_ids || [],
      source_controls: o.source_controls || [],
    })),
  }));
  res.json({ zones: list });
});

app.get("/api/queue/:zoneId", (req, res) => {
  if (!requireConnected(res)) return;
  const { zoneId } = req.params;
  if (!requireZone(zoneId, res)) return;
  ensureQueueSubscription(zoneId);

  const cached = queueCache[zoneId] || {};
  const items = Array.isArray(cached.items) ? cached.items.map(queueItemToDto) : [];
  res.json({
    zone_id: zoneId,
    items,
    count: items.length,
    last_update: cached.last_update || null,
    command: cached.command || null,
  });
});

app.get("/api/nowplaying/:zoneId", (req, res) => {
  if (!requireConnected(res)) return;
  const zone = zones[req.params.zoneId];
  if (!zone) return res.status(404).json({ error: "Zone nicht gefunden" });
  const np = zone.now_playing;
  res.json({
    zone_id: zone.zone_id,
    state:   zone.state,
    now_playing: np ? {
      title:         (np.two_line || {}).line1 || "",
      subtitle:      (np.two_line || {}).line2 || "",
      image_key:     np.image_key || null,
      seek_position: np.seek_position || 0,
      length:        np.length || 0,
    } : null,
  });
});

app.get("/api/albums", async (req, res) => {
  if (!requireConnected(res)) return;
  const { query = "", offset = 0, limit = 50 } = req.query;
  try {
    const result = await fetchAlbums({ query, offset, limit });
    res.json({
      albums: result.items.map(item => ({
        ...albumToDto(item, item.album_index ?? result.offset + result.items.indexOf(item)),
        image_url: item.image_key ? `/api/image/${encodeURIComponent(item.image_key)}?width=500&height=500` : null,
      })),
      total: result.total,
      offset: result.offset,
      limit: result.limit,
      query,
      scanned: result.scanned,
      complete: result.complete,
    });
  } catch (err) {
    console.error("[albums]", err.message);
    res.status(500).json({ error: err.message });
  }
});

app.get("/api/search", async (req, res) => {
  if (!requireConnected(res)) return;
  const { query = "", offset = 0, limit = 50, source = "roon" } = req.query;
  if (!String(query || "").trim()) return res.status(400).json({ error: "query erforderlich" });

  try {
    const result = source === "albums"
      ? await searchAlbumsFallback({ query, offset, limit })
      : await searchRoon({ query, offset, limit });
    const results = result.source === "albums"
      ? result.items.map((item, index) => albumSearchResultToDto(item, result.offset + index))
      : result.items.map(item => searchItemToDto(item, result.session_key));

    res.json({
      source: result.source,
      title: result.title,
      subtitle: result.subtitle,
      hint: result.hint || null,
      query,
      results,
      total: result.total,
      offset: result.offset,
      limit: result.limit,
      action: result.action,
      scanned: result.scanned,
      complete: result.complete,
      expanded: result.expanded || false,
    });
  } catch (err) {
    console.error("[search]", err.message);

    try {
      const fallback = await searchAlbumsFallback({ query, offset, limit });
      const results = fallback.items.map((item, index) => albumSearchResultToDto(item, fallback.offset + index));
      res.json({
        source: "albums",
        fallback_from: "roon",
        title: fallback.title,
        subtitle: fallback.subtitle,
        hint: fallback.hint,
        query,
        results,
        total: fallback.total,
        offset: fallback.offset,
        limit: fallback.limit,
        action: fallback.action,
        scanned: fallback.scanned,
        complete: fallback.complete,
        warning: err.message,
      });
    } catch (fallbackErr) {
      res.status(500).json({ error: fallbackErr.message });
    }
  }
});

app.get("/api/album", async (req, res) => {
  if (!requireConnected(res)) return;
  const { itemKey, albumIndex } = req.query;
  if (!itemKey && albumIndex == null) return res.status(400).json({ error: "itemKey oder albumIndex erforderlich" });

  try {
    const details = await fetchAlbumDetails(itemKey, albumIndex);
    res.json({
      action: details.action,
      title: details.title,
      subtitle: details.subtitle,
      items: details.items.map(itemToDto),
    });
  } catch (err) {
    console.error("[album]", err.message);
    res.status(500).json({ error: err.message });
  }
});

app.get("/api/browse-item", async (req, res) => {
  if (!requireConnected(res)) return;
  const { hierarchy = "search", browserSessionKey, itemKey, zoneId } = req.query;
  if (!browserSessionKey || !itemKey) {
    return res.status(400).json({ error: "browserSessionKey und itemKey erforderlich" });
  }

  try {
    const options = {
      hierarchy,
      multi_session_key: browserSessionKey,
      item_key: itemKey,
    };
    if (zoneId) options.zone_or_output_id = zoneId;
    const result = await browseAsync(options);
    const items = result.action === "list"
      ? await loadItems(hierarchy, browserSessionKey, result, 0, getListCount(result))
      : [];
    res.json({
      action: result.action || null,
      title: result.title || null,
      subtitle: result.subtitle || null,
      list: result.list || null,
      items: items.map(itemToDto),
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get("/api/image/:imageKey", (req, res) => {
  if (!requireConnected(res)) return;
  image.get_image(
    req.params.imageKey,
    { scale: req.query.scale || "fit", width: Number(req.query.width) || 300, height: Number(req.query.height) || 300, format: "image/jpeg" },
    (err, contentType, buffer) => {
      if (err) return res.status(500).json({ error: String(err) });
      res.set("Content-Type", contentType);
      res.set("Cache-Control", "public, max-age=86400");
      res.send(buffer);
    }
  );
});

app.post("/api/play", (req, res) => {
  if (!requireConnected(res)) return;
  const { zoneId, itemKey, albumIndex, hierarchy, browserSessionKey } = req.body;
  if (!zoneId || (!itemKey && albumIndex == null)) return res.status(400).json({ error: "zoneId und itemKey oder albumIndex erforderlich" });
  if (!requireZone(zoneId, res)) return;

  const playPromise = hierarchy && browserSessionKey
    ? playBrowserItem(zoneId, hierarchy, browserSessionKey, itemKey)
    : playItem(zoneId, itemKey, albumIndex);

  playPromise
    .then(result => res.json(result))
    .catch(err => {
      console.error("[play]", err.message);
      res.status(500).json({ error: err.message });
    });
});

app.post("/api/transport", (req, res) => {
  if (!requireConnected(res)) return;
  const { zoneId, action, outputId, volume } = req.body;
  if (!zoneId || !action) return res.status(400).json({ error: "zoneId und action erforderlich" });
  if (!requireZone(zoneId, res)) return;

  if (action === "volume" && outputId != null && volume != null) {
    if (!requireOutput(outputId, res)) return;
    return transportChangeVolumeAsync(outputId, "absolute", Number(volume))
      .then(() => res.json({ ok: true }))
      .catch(err => res.status(500).json({ error: String(err) }));
  }

  const valid = { play: 1, pause: 1, playpause: 1, stop: 1, next: 1, previous: 1 };
  if (!valid[action]) return res.status(400).json({ error: "Unbekannte Aktion: " + action });

  transport.control(zoneId, action, (err) => {
    if (err) return res.status(500).json({ error: String(err) });
    res.json({ ok: true });
  });
});

app.post("/api/system", (req, res) => {
  if (!requireConnected(res)) return;
  const { action } = req.body;
  if (!action) return res.status(400).json({ error: "action erforderlich" });

  let op;
  if (action === "pause_all") {
    op = transportPauseAllAsync();
  } else if (action === "mute_all") {
    op = transportMuteAllAsync("mute");
  } else if (action === "unmute_all") {
    op = transportMuteAllAsync("unmute");
  } else {
    return res.status(400).json({ error: "Unbekannte Aktion: " + action });
  }

  op.then(() => res.json({ ok: true }))
    .catch(err => res.status(500).json({ error: String(err) }));
});

app.post("/api/queue", (req, res) => {
  if (!requireConnected(res)) return;
  const { zoneId, action, queueItemId } = req.body;
  if (!zoneId || !action) return res.status(400).json({ error: "zoneId und action erforderlich" });
  if (!requireZone(zoneId, res)) return;

  if (action !== "play_from_here") {
    return res.status(400).json({ error: "Unbekannte Queue-Aktion: " + action });
  }
  if (!queueItemId) return res.status(400).json({ error: "queueItemId erforderlich" });

  transportPlayFromHereAsync(zoneId, queueItemId)
    .then(result => res.json({ ok: true, result }))
    .catch(err => res.status(500).json({ error: String(err) }));
});

app.post("/api/output", (req, res) => {
  if (!requireConnected(res)) return;
  const { outputId, action, value, controlKey } = req.body;
  if (!outputId || !action) return res.status(400).json({ error: "outputId und action erforderlich" });
  if (!requireOutput(outputId, res)) return;

  let op;
  if (action === "mute" || action === "unmute") {
    op = transportMuteAsync(outputId, action);
  } else if (action === "volume_relative") {
    op = transportChangeVolumeAsync(outputId, "relative", Number(value || 0));
  } else if (action === "volume_step") {
    op = transportChangeVolumeAsync(outputId, "relative_step", Number(value || 0));
  } else {
    op = transportOutputPowerAsync(outputId, action, controlKey);
  }

  op.then(() => res.json({ ok: true }))
    .catch(err => res.status(500).json({ error: String(err) }));
});

app.post("/api/group", (req, res) => {
  if (!requireConnected(res)) return;
  const outputIds = Array.isArray(req.body.outputIds) ? req.body.outputIds : [];
  if (outputIds.length < 2) return res.status(400).json({ error: "Mindestens zwei outputIds erforderlich" });
  const missing = outputIds.find(id => !outputById(id));
  if (missing) return res.status(404).json({ error: "Output nicht gefunden: " + missing });

  transportGroupOutputsAsync(outputIds)
    .then(() => res.json({ ok: true }))
    .catch(err => res.status(500).json({ error: String(err) }));
});

app.post("/api/ungroup", (req, res) => {
  if (!requireConnected(res)) return;
  const outputIds = Array.isArray(req.body.outputIds) ? req.body.outputIds : [];
  if (!outputIds.length) return res.status(400).json({ error: "outputIds erforderlich" });
  const missing = outputIds.find(id => !outputById(id));
  if (missing) return res.status(404).json({ error: "Output nicht gefunden: " + missing });

  transportUngroupOutputsAsync(outputIds)
    .then(() => res.json({ ok: true }))
    .catch(err => res.status(500).json({ error: String(err) }));
});

app.post("/api/transfer", (req, res) => {
  if (!requireConnected(res)) return;
  const { fromZoneId, toZoneId } = req.body;
  if (!fromZoneId || !toZoneId) return res.status(400).json({ error: "fromZoneId und toZoneId erforderlich" });
  if (!requireZone(fromZoneId, res)) return;
  if (!requireZone(toZoneId, res)) return;

  transportTransferZoneAsync(fromZoneId, toZoneId)
    .then(() => res.json({ ok: true }))
    .catch(err => res.status(500).json({ error: String(err) }));
});

app.post("/api/settings", (req, res) => {
  if (!requireConnected(res)) return;
  const { zoneId, shuffle, auto_radio, loop } = req.body;
  if (!zoneId) return res.status(400).json({ error: "zoneId erforderlich" });
  if (!requireZone(zoneId, res)) return;

  const settings = {};
  if (shuffle != null) settings.shuffle = Boolean(shuffle);
  if (auto_radio != null) settings.auto_radio = Boolean(auto_radio);
  if (loop != null) settings.loop = loop;
  if (!Object.keys(settings).length) return res.status(400).json({ error: "Keine Settings angegeben" });

  transportChangeSettingsAsync(zoneId, settings)
    .then(() => res.json({ ok: true }))
    .catch(err => res.status(500).json({ error: String(err) }));
});

app.post("/api/seek", (req, res) => {
  if (!requireConnected(res)) return;
  const { zoneId, seconds } = req.body;
  if (!zoneId || seconds == null) return res.status(400).json({ error: "zoneId und seconds erforderlich" });
  if (!requireZone(zoneId, res)) return;
  transport.seek(zoneId, "absolute", Number(seconds), (err) => {
    if (err) return res.status(500).json({ error: String(err) });
    res.json({ ok: true });
  });
});

app.listen(PORT, () => {
  console.log("[server] Jukebox API läuft auf http://localhost:" + PORT);
});
