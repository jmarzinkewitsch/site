# K5 — Trailer am Kiosk + Cast zum Apple TV — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auf der Kiosk-Vault-Seite Trailer (MP4) direkt am Pi abspielen und ganze Filme zum Apple TV casten (HA weckt/startet die Vault-App, die tvOS-App holt das Abspiel-Kommando ab und springt in den Player).

**Architecture:** Drei Teile. **A** vault-api-Backend: HA-Apple-TV-Launch + ein `/cast/appletv`-Router mit kurzlebigem „pending"-Kommando + ein kiosk-zugänglicher Trailer-Endpunkt. **B** Kiosk-Web-Frontend: Die Vault-Detailansicht bekommt statt des (nicht spielbaren MKV-)Direktstreams zwei Aktionen — „Trailer" (spielt MP4 am Kiosk) und „Am Apple TV abspielen" (POST /cast). **C** tvOS-Vault-App: ein minimaler Listener, der beim Start/Foreground `/cast/appletv/pending` abholt und in den bestehenden Player springt.

**Tech Stack:** FastAPI/httpx (Python 3.12), Vanilla-JS-Kiosk-App, SwiftUI/tvOS (Vault-App). HA REST über `services/homeassistant.py`. Trailer-Auflösung via vorhandenem yt-dlp-Resolver in `routers/library.py`.

## Global Constraints

- **Keine fremden Keys/Hosts an den Browser oder Pi.** Alles über vault-api; Jellyfin/HA-Credentials bleiben im Backend (wie bei `/kiosk/media/image|stream`).
- **Auth:** Kiosk-erreichbare Endpunkte nutzen `require_bearer_or_kiosk` (akzeptiert Header *oder* `?token=`). Der tvOS-Listener nutzt den **vollen Bearer-Token** (`require_bearer`).
- **Tests zuerst (TDD), häufige Commits.** vault-api-Tests laufen mit `.venv312/bin/python -m pytest -q` (aktuell 217 grün — nicht brechen).
- **Deploy:** Code wird per rsync auf den NAS (`admin_jan@192.168.0.42:vault-api/`) gespiegelt; statische Web-Assets liefert vault-api mit `Cache-Control: no-cache`. tvOS wird auf dem Mac in Xcode gebaut.
- **Konsistenz:** Bestehende Muster aus `routers/home.py`, `routers/music.py`, `services/homeassistant.py` übernehmen (kuratiert, Whitelist-404, `HomeAssistantError`→HTTPException).

---

## API-Vertrag (BEIDE Agenten halten sich exakt daran)

```
POST /cast/appletv                 (require_bearer_or_kiosk)
     Body:  { "item_id": "<jellyfin-id>" }
     Wirkung: (1) HA: Apple TV wecken + Vault-App starten,
              (2) pending-Kommando { item_id, created_at } ablegen (überschreibt vorheriges).
     200:   { "ok": true, "item_id": "<id>", "appletv": "<state>" }
     502:   HA-Fehler

GET  /cast/appletv/pending         (require_bearer)   ← nur die tvOS-App
     Wirkung: liefert das pending-Kommando und LÖSCHT es (consume-once).
     200:   { "item_id": "<id>", "created_at": "<iso>" }  oder  { "item_id": null }

GET  /cast/appletv/status          (require_bearer_or_kiosk)
     200:   { "online": true|false, "state": "<ha-state>", "app": "<app_name|null>" }
```

- `item_id` ist die **Jellyfin-Item-Id** (dieselbe wie in `/kiosk/media/*`). Die tvOS-App spielt sie über ihren bestehenden Player-Pfad (Resume aus Jellyfin) ab.
- pending-Store: **in-memory** auf `app.state` (kurzlebig; geht bei vault-api-Neustart verloren — akzeptiert, da der Apple TV unmittelbar nach dem Cast pollt).

```
GET  /kiosk/media/item/{item_id}/trailer   (require_bearer_or_kiosk)
     200:   { "url": "<https-mp4-cdn-url>", "container": "mp4" }
     404:   kein Trailer verfügbar
```

- Die Trailer-URL ist eine **öffentliche googlevideo-CDN-MP4** (cross-origin, browsertauglich). Der Browser lädt sie direkt (kein Token nötig, da fremde Origin).

---

## Part A — vault-api Backend  (Agent: `vault-api`)

### Task A1: HA — Apple TV wecken/starten + Status

**Files:**
- Modify: `vault-api/services/homeassistant.py` (neue Methoden `launch_apple_tv`, `media_player_state`)
- Modify: `vault-api/config.py` (neue `CastConfig`)
- Test: `vault-api/tests/test_cast.py` (neu)

**Interfaces:**
- Produces:
  - `HomeAssistantService.launch_apple_tv(entity_id: str, source: str | None) -> None`
  - `HomeAssistantService.media_player_state(entity_id: str) -> HAState | None` (nutzt das vorhandene `state()`)
  - `config.cast: CastConfig` mit `appletv_entity: str = "media_player.appletv"`, `appletv_source: str = "Vault"` (der Quellen-/App-Name in HA — **live zu verifizieren**, s. u.)

- [ ] **Step 1: Failing test** — `launch_apple_tv` ruft `media_player.turn_on` und dann `media_player.select_source` mit der Quelle:

```python
# tests/test_cast.py
import pytest
from services.homeassistant import HomeAssistantService

class _FakeHTTP:
    def __init__(self): self.calls = []
    async def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append((url, json))
        class R: status_code = 200
        return R()

@pytest.mark.asyncio
async def test_launch_apple_tv_wakes_then_selects_source():
    from config import ServiceConfig
    http = _FakeHTTP()
    svc = HomeAssistantService(ServiceConfig(base_url="http://ha", api_key="k"), http)
    await svc.launch_apple_tv("media_player.appletv", "Vault")
    assert "/api/services/media_player/turn_on" in http.calls[0][0]
    assert "/api/services/media_player/select_source" in http.calls[1][0]
    assert http.calls[1][1] == {"entity_id": "media_player.appletv", "source": "Vault"}
```

- [ ] **Step 2: Run** `.venv312/bin/python -m pytest tests/test_cast.py -q` → FAIL (no `launch_apple_tv`).
- [ ] **Step 3: Implement** in `services/homeassistant.py` (nutzt das vorhandene flache `call_service`-Payload-Muster `{"entity_id": ..., **data}`):

```python
async def launch_apple_tv(self, entity_id: str, source: str | None = None) -> None:
    await self.call_service("media_player.turn_on", entity_id=entity_id)
    if source:
        await self.call_service(
            "media_player.select_source", entity_id=entity_id, data={"source": source}
        )

async def media_player_state(self, entity_id: str):
    return await self.state(entity_id)
```

  Und in `config.py` neben den anderen Kiosk-Configs:

```python
class CastConfig(BaseModel):
    appletv_entity: str = "media_player.appletv"
    appletv_source: str = "Vault"  # HA-Quellenname der Vault-App — live prüfen
```

  In `VaultConfig`: `cast: CastConfig = Field(default_factory=CastConfig)`.

- [ ] **Step 4: Run** pytest → PASS.
- [ ] **Step 5: Commit** `feat(cast): HA Apple-TV launch + status helpers`.

> **Live-Verifikation (Mensch/Agent mit HA-Zugriff):** Vault-App einmal am Apple TV öffnen, dann `media_player.appletv` → `source_list` in HA prüfen und `cast.appletv_source` auf den exakten Namen setzen. Aktuell (idle) ist keine `source_list` sichtbar.

### Task A2: `/cast/appletv`-Router mit pending-Store

**Files:**
- Create: `vault-api/routers/cast.py`
- Modify: `vault-api/main.py` (Router mounten), `vault-api/models.py` (Modelle)
- Modify: `vault-api/deps.py` (falls Config/HA-Dep gebraucht — bestehende `get_config`, `get_homeassistant` nutzen)
- Test: `vault-api/tests/test_cast.py` (erweitern)

**Interfaces:**
- Consumes: `HomeAssistantService.launch_apple_tv`, `media_player_state` (A1); `config.cast` (A1).
- Produces: Endpunkte exakt nach API-Vertrag. pending-Store auf `request.app.state.cast_pending` (dict | None).
- Modelle: `CastRequest{item_id:str}`, `CastResult{ok:bool,item_id:str,appletv:str|None}`, `CastPending{item_id:str|None,created_at:str|None}`, `CastStatus{online:bool,state:str,app:str|None}`.

- [ ] **Step 1: Failing tests** (TestClient): POST setzt pending + ruft HA; GET /pending consumed-once; GET /status liest HA. Beispiel:

```python
def test_cast_post_stores_pending_and_calls_ha(client, store):
    store.update(kiosk_token="kt", homeassistant={"base_url":"http://ha","api_key":"k"})
    fake = FakeCastHA()  # zeichnet launch_apple_tv-Aufrufe auf
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: fake
    try:
        r = client.post("/cast/appletv", headers={"Authorization":"Bearer kt"}, json={"item_id":"m1"})
        assert r.status_code == 200 and r.json()["item_id"] == "m1"
        assert fake.launched == [("media_player.appletv","Vault")]
        p = client.get("/cast/appletv/pending", headers={"Authorization":"Bearer kt"})  # bearer
        assert p.json()["item_id"] == "m1"
        p2 = client.get("/cast/appletv/pending", headers={"Authorization":"Bearer kt"})
        assert p2.json()["item_id"] is None  # consume-once
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)
```

  *(Hinweis: `/pending` ist `require_bearer` — der Test nutzt den vollen Bearer-Token, den `store` per `auth`-Fixture/`bearer_token` setzt.)*

- [ ] **Step 2: Run** pytest → FAIL.
- [ ] **Step 3: Implement** `routers/cast.py`:

```python
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from auth import require_bearer, require_bearer_or_kiosk
from config import VaultConfig
from deps import get_config, get_homeassistant
from models import CastRequest, CastResult, CastPending, CastStatus
from services.homeassistant import HomeAssistantError, HomeAssistantService

router = APIRouter(prefix="/cast", tags=["cast"])

@router.post("/appletv", response_model=CastResult, dependencies=[Depends(require_bearer_or_kiosk)])
async def cast_appletv(body: CastRequest, request: Request,
                       config: VaultConfig = Depends(get_config),
                       ha: HomeAssistantService = Depends(get_homeassistant)) -> CastResult:
    cfg = config.cast
    try:
        await ha.launch_apple_tv(cfg.appletv_entity, cfg.appletv_source)
        state = await ha.media_player_state(cfg.appletv_entity)
    except HomeAssistantError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    request.app.state.cast_pending = {"item_id": body.item_id,
                                      "created_at": datetime.now(timezone.utc).isoformat()}
    return CastResult(ok=True, item_id=body.item_id, appletv=state.state if state else None)

@router.get("/appletv/pending", response_model=CastPending, dependencies=[Depends(require_bearer)])
async def cast_pending(request: Request) -> CastPending:
    pending = getattr(request.app.state, "cast_pending", None)
    request.app.state.cast_pending = None
    if not pending:
        return CastPending(item_id=None, created_at=None)
    return CastPending(**pending)

@router.get("/appletv/status", response_model=CastStatus, dependencies=[Depends(require_bearer_or_kiosk)])
async def cast_status(config: VaultConfig = Depends(get_config),
                      ha: HomeAssistantService = Depends(get_homeassistant)) -> CastStatus:
    try:
        state = await ha.media_player_state(config.cast.appletv_entity)
    except HomeAssistantError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    if state is None:
        return CastStatus(online=False, state="unknown", app=None)
    return CastStatus(online=state.state not in {"off","unavailable","standby"},
                      state=state.state, app=state.attributes.get("app_name"))
```

  Modelle in `models.py` ergänzen; in `main.py` `from routers import ... cast` + `app.include_router(cast.router)`. `app.state.cast_pending = None` im Startup setzen (neben den anderen app.state-Inits).

- [ ] **Step 4: Run** pytest → PASS.
- [ ] **Step 5: Commit** `feat(cast): /cast/appletv router with consume-once pending store`.

### Task A3: Kiosk-Trailer-Endpunkt

**Files:**
- Modify: `vault-api/routers/kiosk.py` (neuer Endpunkt `/kiosk/media/item/{item_id}/trailer`)
- Test: `vault-api/tests/test_kiosk.py` (erweitern)

**Interfaces:**
- Consumes: vorhandene Trailer-Auflösung in `routers/library.py` — die Funktionen `_resolve_trailer_stream(url)` und `_trailer_url(media_type, tmdb_id, config, cache, http)` sowie der Endpunkt `trailer_stream` als Vorlage. Liefert `TrailerStreamInfo{url, container}`.
- Produces: `GET /kiosk/media/item/{id}/trailer` → `TrailerStreamInfo` (kiosk-token-fähig).

- [ ] **Step 1: Failing test** — Kiosk-Token bekommt eine MP4-Trailer-URL (Fake-Jellyfin liefert `trailer_url`, Fake-Resolver liefert mp4):

```python
def test_kiosk_trailer_accepts_scoped_token(client, store, monkeypatch):
    store.update(kiosk_token="kt", jellyfin={"base_url":"http://jf","api_key":"x","user_id":"u"})
    # Fake-Jellyfin.item liefert LibraryItem(trailer_url="https://youtube/watch?v=x")
    # Resolver monkeypatchen → TrailerStreamInfo(url="https://cdn/t.mp4", container="mp4")
    ...
    r = client.get("/kiosk/media/item/m1/trailer", headers={"Authorization":"Bearer kt"})
    assert r.status_code == 200 and r.json()["container"] == "mp4"
```

- [ ] **Step 2: Run** pytest → FAIL.
- [ ] **Step 3: Implement** in `kiosk.py` — DRY: dieselbe Auflösungslogik wie `library.trailer_stream` nutzen. Sauberste Variante: die Resolver-Helfer aus `library.py` importieren (`from routers.library import _resolve_trailer_stream, _trailer_url, _trailer_stream_key`) und den Endpunkt-Body spiegeln (Cache-Key teilen, damit Kiosk- und tvOS-Trailer denselben Cache treffen). Endpunkt unter `require_bearer_or_kiosk`, Deps `get_config`, `get_jellyfin`, `get_cache`, und `request.app.state.http`. Bei „kein Trailer" → 404.

  *(Falls der Import privater Helfer unsauber wirkt: die drei Funktionen vorab in ein `services/trailers.py` extrahieren und beide Router (`library`, `kiosk`) darauf umstellen — separater, optionaler Refactor-Commit.)*

- [ ] **Step 4: Run** pytest → PASS (volle Suite ebenfalls grün halten).
- [ ] **Step 5: Commit** `feat(kiosk): kiosk-scoped trailer endpoint`.

---

## Part B — Kiosk-Web-Frontend  (Agent: `vault-api`, gleiche Dateien wie A)

### Task B1: Vault-Detail — „Trailer" + „Am Apple TV abspielen"

**Files:**
- Modify: `vault-api/web/kiosk/index.html` (Media-Detail-Overlay: zwei Buttons statt nur „Abspielen")
- Modify: `vault-api/web/kiosk/app.js` (`openMediaDetail`, neue Handler `playTrailer`, `castToAppleTv`; den MKV-Direktstream-Play **entfernen**)
- Modify: `vault-api/web/kiosk/app.css` (Button-Styling, Cast-Feedback)

**Interfaces:**
- Consumes: `GET /kiosk/media/item/{id}/trailer` (A3), `POST /cast/appletv` (A2). Vorhandene Helfer: `api(path, options)`, `imageUrl(url)`, `els.mediaVideo`, `els.mediaOverlay`.

- [ ] **Step 1:** In `index.html` im `.media-detail` die Aktionszeile auf zwei Buttons ändern:

```html
<div class="detail-actions">
  <button type="button" class="play-action" data-media-trailer>Trailer</button>
  <button type="button" class="play-action primary" data-media-cast>Am Apple TV abspielen</button>
  <span class="cast-feedback" data-cast-feedback></span>
</div>
```

- [ ] **Step 2:** In `app.js`:
  - `els` um `mediaTrailer`, `mediaCast`, `castFeedback` ergänzen; `mediaPlay`/`playCurrentMedia` und das Setzen von `els.mediaVideo.src = imageUrl(item.stream_url)` in `openMediaDetail` **entfernen** (kein MKV-Direktplay mehr).
  - Neue Handler:

```js
async function playTrailer() {
  if (!currentMediaDetail) return;
  try {
    const t = await api(`/kiosk/media/item/${encodeURIComponent(currentMediaDetail.id)}/trailer`);
    els.mediaVideo.hidden = false;
    els.mediaVideo.src = t.url;          // öffentliche CDN-MP4, cross-origin, kein Token
    await els.mediaVideo.play();
  } catch {
    els.castFeedback.textContent = "Kein Trailer verfügbar";
  }
}
async function castToAppleTv() {
  if (!currentMediaDetail) return;
  els.castFeedback.textContent = "Starte am Apple TV …";
  try {
    await api("/cast/appletv", { method: "POST",
      body: JSON.stringify({ item_id: currentMediaDetail.id }) });
    els.castFeedback.textContent = "Am Apple TV gestartet";
  } catch {
    els.castFeedback.textContent = "Apple TV nicht erreichbar";
  }
}
els.mediaTrailer.addEventListener("click", playTrailer);
els.mediaCast.addEventListener("click", castToAppleTv);
```

- [ ] **Step 3: Verifizieren** — lokal/headless: Detail öffnen, „Trailer" spielt MP4; „Am Apple TV abspielen" gibt Feedback. (Kein automatisierter Test fürs JS; manuell + Screenshot.)
- [ ] **Step 4: Commit** `feat(kiosk): vault detail plays trailers on-device and casts full films to Apple TV`.

---

## Part C — tvOS Vault-App: Cast-Listener  (Agent: `tvos`, paralleler Worktree)

> Vorab in `Vault/` orientieren: wie startet die App heute eine Wiedergabe (Player-View, Resume aus Jellyfin)? Den **bestehenden** Abspielpfad wiederverwenden — der Listener liefert nur die Item-Id hinein.

### Task C1: CastListener — pending beim Start/Foreground abholen

**Files:**
- Create: `Vault/Vault/Services/CastListener.swift`
- Modify: die App-Einstiegs-/Szenen-Datei (`@main` App bzw. der Root-View), um den Listener bei `.active`/Launch zu starten.
- Test: bestehende Test-Konventionen der Vault-App folgen (falls vorhanden).

**Interfaces:**
- Consumes: `GET {vaultApiBaseURL}/cast/appletv/pending` mit `Authorization: Bearer <vault-bearer-token>` (derselbe Token/Client, den die App schon für vault-api nutzt). Antwort `{ item_id: String?, created_at: String? }`.
- Produces: bei `item_id != nil` → Aufruf des bestehenden Player-Starts mit dieser Jellyfin-Id.

- [ ] **Step 1:** `CastListener` implementieren: beim App-Start und bei jedem Wechsel in den Vordergrund **einmal** `/cast/appletv/pending` abrufen; zusätzlich, solange im Vordergrund, alle ~5 s pollen (leichtgewichtig). Bei `item_id` → auf dem MainActor den vorhandenen Player mit der Id öffnen (Resume-Position kommt wie gehabt aus Jellyfin).
- [ ] **Step 2:** Im `@main`-App/Scene den Listener an den ScenePhase-`.active`-Übergang hängen (und einmal beim Erststart). Den vorhandenen vault-api-Client/Bearer-Token wiederverwenden (nicht neu erfinden).
- [ ] **Step 3:** Build in Xcode (`Vault.xcodeproj`), auf dem Apple TV / Simulator testen: vom Kiosk casten → App kommt nach vorn → springt in den Film.
- [ ] **Step 4: Commit** `feat(tvos): cast listener picks up pending play command and opens the player`.

---

## Reihenfolge & Abhängigkeiten

1. **A1 → A2 → A3** (vault-api, sequentiell; B1 danach, gleiche Codebasis).
2. **C** kann **parallel** zu A/B laufen — der tvOS-Agent codet gegen den **API-Vertrag** oben (POST von B, GET /pending von C). Erst zum End-to-End-Test müssen beide fertig sein.
3. **Live-Punkte** (Mensch mit HA/Geräten): `cast.appletv_source` gegen HA-`source_list` verifizieren; End-to-End: Kiosk → HA weckt Apple TV → Vault-App startet → holt pending → spielt.

## Deploy & Verifikation

- vault-api: geänderte Dateien nach `admin_jan@192.168.0.42:vault-api/` rsyncen, dann `cd ~/vault-api && docker compose up -d --build vault-api`. Verifizieren: `POST /cast/appletv` (Apple TV wacht auf), `/kiosk/media/item/{id}/trailer` liefert mp4, Vault-Detail spielt Trailer.
- tvOS: in Xcode auf den Apple TV deployen.

## Definition of Done

- [ ] Vault-Detail am Kiosk: „Trailer" spielt MP4 am Pi.
- [ ] „Am Apple TV abspielen": HA weckt/startet die Vault-App, die App springt in den richtigen Film.
- [ ] Kein MKV-Direktstream-Play mehr im Kiosk; kein Jellyfin/HA-Key im Browser.
- [ ] vault-api-Tests grün (inkl. neuer `test_cast.py` + Trailer-Test).
