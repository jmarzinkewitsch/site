# Kiosk-Dashboard — Architektur (Konzept)

Stand: Planungsdokument, noch kein Code. Erweitert die bestehende
**API-First**-Architektur (siehe
[`../../Vault/docs/architecture-api-first.md`](../../Vault/docs/architecture-api-first.md))
um einen **zweiten dünnen Client**: ein Touch-Dashboard auf einem Raspberry Pi 5
mit 8″-Touchscreen, das nicht Medien *rendert*, sondern das Zuhause *steuert*.

## Grundsatzentscheidung

Das Kiosk-Dashboard ist eine **Schaltzentrale**, kein Renderer. Es spielt selbst
**kein Video** ab (das macht der Apple TV) und gibt selbst **keinen Roon-Ton**
aus. Es ist eine **Touch-Bedienoberfläche** für vier Dinge:

1. **Roon** — Musik steuern (Now-Playing, Transport, Zonen).
2. **Podcasts** — abspielen über **Music Assistant** auf dieselben Lautsprecher
   wie Roon (nicht über Roon selbst).
3. **Vault am Apple TV** — Inhalte **anstoßen** („Jetzt am Apple TV abspielen"),
   keine volle Fernbedienung.
4. **Home Assistant** — Licht, Heizung, Kaffeemaschine.

Wie der Apple TV kennt der Kiosk **genau einen Endpunkt: `vault-api`**. Kein
direkter Call aus dem Kiosk an Home Assistant, Music Assistant, Roon, einen
Podcast-Index oder den Apple TV. Alle fremden Keys und Credentials bleiben im
Backend. Der Kiosk kennt nur **vault-api-URL + ein Gerätetoken**.

Damit gilt dieselbe Begründung wie für den Apple TV (kein fremder Key auf dem
Gerät, Logik serverseitig änderbar, Caching/Rate-Limiting/Realtime einmal
gebaut), und die ganze neue Logik (HA, Podcasts, Push-to-TV) ist **reines
Python und damit sofort baubar und testbar**, auch ohne den Pi.

## Annahmen & Scope

- **LAN-first.** Pi, NAS (vault-api/Redis), Home Assistant, Music Assistant,
  Roon-Core und Apple TV liegen im selben Netz. Kein Remote-Zugriff von
  unterwegs.
- **Always-on-Gerät.** Der Kiosk wird einmal eingerichtet und läuft dann
  dauerhaft im Vollbild. Es gibt **keinen** Login-Screen, keine Tastatur — das
  prägt sowohl Auth (Gerätetoken statt Eintippen) als auch UI (große
  Touch-Ziele, keine Texteingabe außer Suche).
- **Querformat.** Übliche 8″-Pi-Panels haben 1280 × 800. Das Layout wird für
  Landscape entworfen; die Design-Tokens (Farben, Schrift, Amber-Akzent) kommen
  aus dem bestehenden Vault-Design, das Raster ist aber **touch**, nicht
  fokus-/fernbedienungsgetrieben.
- **Ehrlicher Tradeoff:** vault-api sitzt jetzt auch im kritischen Pfad für die
  **Haussteuerung**. Fällt das Backend aus, lässt sich am Kiosk kein Licht
  schalten — obwohl Home Assistant gesund ist. Gegenmaßnahme wie beim Apple TV:
  vault-api robust halten, bei Teilausfall sinnvoll degradieren, und der Kiosk
  kann als Notnagel die native HA-Oberfläche öffnen.

## Laufzeit auf dem Pi

- **Chromium im Kiosk-Modus** (`--kiosk`, Vollbild, Cursor aus), zeigt eine von
  **vault-api ausgelieferte Web-App** unter `http://<nas>:8787/kiosk`.
- **Eine Quelle, ein Deploy:** Die Kiosk-UI wird wie die Admin-UI aus vault-api
  serviert. Der Pi hält keinen eigenen App-Build vor — er zeigt nur eine URL.
  Updates passieren serverseitig, kein Anfassen des Pi.
- Systemseitig nur das Nötigste: Autostart (Chromium im Kiosk), Display-Sleep
  steuern, optional Helligkeit nach Tageszeit. Das ist OS-Konfiguration des Pi,
  kein App-Code.

## vault-api — neue Verantwortlichkeiten

Der Kiosk braucht vom Backend vier neue Fähigkeiten. Alle folgen dem Muster der
bestehenden Services: **kuratierte, vault-spezifische API nach außen**, fremde
Details (HA-Entity-IDs, Music-Assistant-Player, Podcast-Feeds) bleiben innen.

### 1 · Home Assistant (`services/homeassistant.py`)

HA bietet eine saubere **REST-API** (Zustände lesen, Services aufrufen) plus
eine **WebSocket-API** (Live-Zustandsänderungen). vault-api spricht beides und
gibt nach außen **nur die Entitäten frei, die der Kiosk braucht** — nicht das
ganze Haus. Welche Entität „Wohnzimmerlicht", „Heizung Bad" oder
„Kaffeemaschine" ist, wird **einmal in der Admin-UI gemappt**.

```
GET  /home/lights                 Liste freigegebener Leuchten + Zustand
POST /home/lights/{id}            on/off, Helligkeit, ggf. Farbe/Temperatur
GET  /home/climate                Heizkreise + Ist-/Soll-Temperatur
POST /home/climate/{id}           Soll-Temperatur / Modus setzen
GET  /home/coffee                 Kaffeemaschine: an/aus, ggf. Status
POST /home/coffee                 einschalten / ausschalten
```

### 2 · Audio-Wiedergabe & Podcasts (`services/musicassistant.py`, `services/podcasts.py`)

Podcasts laufen über **Music Assistant** auf dieselben physischen Lautsprecher
wie Roon (per AirPlay/MA-Player), **nicht** über Roon. vault-api kann Music
Assistant entweder direkt oder über Home Assistant ansprechen — da HA ohnehin
angebunden wird, ist der HA-Weg der naheliegende.

Podcast-**Discovery** (Suchen/Abonnieren) kommt aus einem Podcast-Index
(z. B. Podcast Index oder iTunes-Search) plus Feed-Parsing; die Episoden-Audio-
URL wird dann an Music Assistant zum Abspielen auf dem Ziel-Player übergeben.

```
GET  /audio/players               abspielbare Ziele (dieselben Speaker wie Roon)
POST /audio/transport             Play/Pause/Seek/Lautstärke je Player
GET  /podcasts/subscriptions      abonnierte Podcasts
GET  /podcasts/search?q=          Podcast-Index-Suche
GET  /podcasts/feed/{id}/episodes Episodenliste eines Feeds (gecacht)
POST /podcasts/play               Episode → Music-Assistant-Player (Speaker)
GET  /podcasts/nowplaying         aktueller Podcast-Stand je Player
```

### 3 · Push-to-TV (`routers/cast.py`)

„Jetzt am Apple TV abspielen" stößt eine Vault-Wiedergabe am Apple TV an. Das
ist die **einzige Fähigkeit, die nicht rein serverseitig** ist: Die tvOS-App
braucht dafür einen **minimalen Listener**, der vom Backend ein „spiele Item X"
entgegennimmt und in den bestehenden Player springt. Bewusst klein gehalten —
**nur Starten**, kein Transport, keine laufende Fernsteuerung.

```
POST /cast/appletv                { itemId }  → Apple TV startet Vault-Player
GET  /cast/appletv/status         online? was läuft gerade?
```

Die Bibliotheks- und Detaildaten zum Auswählen kommen unverändert aus den
bestehenden `/library/*`-Endpunkten — der Kiosk bekommt „Browsen" geschenkt.

### 4 · Realtime-Kanal (`routers/realtime.py`)

Ein Touch-Dashboard muss **sofort** stimmen: Licht, das woanders geschaltet
wurde, der gerade gewechselte Roon-Titel, der Podcast-Fortschritt. Statt
Polling bietet vault-api dem Kiosk **einen WebSocket**, der mehrere Quellen
multiplext:

```
GET  /realtime   (WebSocket)
     ← home.lights / home.climate / home.coffee   (aus HA-WebSocket)
     ← audio.nowplaying                            (Roon + Music Assistant)
     ← cast.appletv.status                         (Apple-TV-Status)
```

Die Kiosk-UI rendert **optimistisch** (Tipp auf „Licht an" schaltet sofort
visuell) und korrigiert über den Realtime-Kanal, falls HA widerspricht.

## Datenfluss

**Haussteuerung (Beispiel Kaffeemaschine):**
```
Kiosk → vault-api   POST /home/coffee {on:true}
vault-api → HA      service call switch.turn_on
Kiosk ← realtime    home.coffee {state:"on"}     (Bestätigung)
```

**Podcast abspielen:**
```
Kiosk → vault-api   POST /podcasts/play {episodeId, player}
vault-api → MA      play_media(url) auf Ziel-Player (Roon-Speaker)
Kiosk ← realtime    audio.nowplaying {…}
```

**Vault am Apple TV starten:**
```
Kiosk → vault-api   GET  /library/movies            (Browsen)
Kiosk → vault-api   POST /cast/appletv {itemId}
vault-api → AppleTV „spiele Item X" (Listener in der tvOS-App)
AppleTV → vault-api GET  /stream/{id}               (wie heute)
AppleTV → Jellyfin  direkter Byte-Stream            (wie heute, LAN)
```

## Authentifizierung — Gerät statt Eintippen

Am Apple TV gibt man den Bearer-Token einmal von Hand ein. Am kopflosen Kiosk
geht das nicht. Stattdessen: In der **Admin-UI ein langlebiges Gerätetoken**
für „Kiosk" erzeugen und einmalig in die Kiosk-Konfiguration (bzw. die
Start-URL) legen. Ein eigenes Token pro Gerät heißt: einzeln widerrufbar, und
der Kiosk-Scope kann später enger gezogen werden als der des Apple TV.

## Sicherheit

- **Keine fremden Keys auf dem Pi** — der Kiosk kennt nur vault-api-URL +
  Gerätetoken. HA-, Music-Assistant- und Podcast-Index-Credentials liegen im
  Backend.
- **Kuratierte HA-Freigabe.** vault-api gibt **nur die gemappten Entitäten**
  frei (Licht/Heizung/Kaffee), kein roher HA-Passthrough. Selbst wenn das
  Gerätetoken abhandenkommt, ist die Angriffsfläche auf diese Entitäten
  begrenzt.
- **`/realtime` und `/home/*` hinter dem Bearer/Gerätetoken**, wie alle
  App-Endpunkte. Nur `/admin` bleibt das LAN-Konfig-Tor (wie gehabt).

## Design für 8″-Touch

- **Tokens wiederverwenden:** Dark `#0A0A0C`, Amber `#E8A030`, SF-Pro —
  konsistent mit Apple-TV-Vault, damit beide Oberflächen als „Vault" lesbar
  sind.
- **Aber neues Raster:** kein Fokus-Ring, kein 3-m-Sehabstand. Stattdessen
  **große Kacheln**, Daumen-erreichbare Transportknöpfe, fette Statuswerte
  (Temperatur, Uhrzeit). Mindest-Touch-Ziel ~48 px.
- **Startbild = Übersicht:** Uhr/Datum, Now-Playing (Roon/Podcast), die
  wichtigsten Haus-Kacheln (Licht-Szenen, Heizung, Kaffee) auf einen Blick.
  Detailtiefe (alle Leuchten, Podcast-Browser, Vault-Bibliothek) eine
  Ebene darunter.
- Mockups als eigenständiges HTML (am Handy reviewbar), wie beim Apple TV —
  Zielordner [`../mockup/`](../mockup/).

## Getroffene Entscheidungen

1. **Rolle:** Der Kiosk **steuert**, er **rendert nicht** (kein Video, kein
   eigener Roon-Ton). Damit bleibt er ein dünner Client an einem Endpunkt.
2. **Laufzeit:** **Web-App im Chromium-Kiosk**, von vault-api unter `/kiosk`
   ausgeliefert. Kein eigener App-Build auf dem Pi.
3. **Podcasts:** über **Music Assistant** (HA-Weg) auf **dieselben Lautsprecher
   wie Roon**, nicht über Roon. Discovery über einen Podcast-Index + Feed-Parsing.
4. **Home Assistant:** **kuratierte** `/home/*`-API (nur gemappte Entitäten),
   Live-Zustand über einen `/realtime`-WebSocket. Mapping in der Admin-UI.
5. **Vault am Apple TV:** nur **„Jetzt abspielen"** (`/cast/appletv`). Erfordert
   einen **minimalen Listener** in der tvOS-App — das einzige nicht rein
   serverseitige Stück, bewusst zuletzt.
6. **Auth:** **langlebiges Gerätetoken** pro Kiosk, in der Admin-UI erzeugt.

## Milestones

Reihenfolge nach **täglichem Nutzwert** und **Risiko**: erst Gerüst, dann die
Haussteuerung (größter sofortiger Mehrwert), dann Roon, dann Podcasts, zuletzt
das Apple-TV-Anstoßen (braucht als Einziges eine tvOS-Änderung).

- **K1 — Gerüst & Rahmen.** Kiosk-Web-App-Skeleton, von vault-api unter `/kiosk`
  serviert; Gerätetoken in der Admin-UI; Chromium-Autostart auf dem Pi;
  Startbild mit Uhr + Design-Tokens; `/realtime`-WebSocket-Gerüst (noch ohne
  Quellen).
- **K2 — Home Assistant.** `services/homeassistant.py`, `/home/*`-Endpunkte
  (Licht/Heizung/Kaffee), HA-WebSocket → `/realtime`. Admin-UI: Entity-Mapping.
  Kiosk: Haus-Kacheln, optimistisches Schalten.
- **K3 — Roon am Kiosk.** Nutzt die `/music/*`-Endpunkte aus Vault-M8
  (Now-Playing, Transport, Zonen) in einer Touch-UI. *(Abhängigkeit: Roon-
  Anbindung in vault-api — entweder M8 vorziehen oder parallel bauen.)*
- **K4 — Podcasts.** `services/podcasts.py` (Index-Suche + Feed-Parsing) und
  `services/musicassistant.py` (Wiedergabe auf den Roon-Speakern),
  `/podcasts/*` + `/audio/*`. Kiosk: Abos, Episodenliste, Abspielen, Transport.
- **K5 — Vault „Jetzt am Apple TV abspielen".** `/cast/appletv` im Backend +
  **minimaler Listener** in der tvOS-App. Kiosk: Vault-Bibliothek browsen
  (`/library/*`) und „Auf Apple TV abspielen".

## Was zuerst gebaut wird

Wie bei vault-api: alles **Python-seitige zuerst**, weil sofort baubar und
testbar, auch ohne den Pi und ohne Apple-TV-Änderung. Reihenfolge:
`services/homeassistant.py` + `/home/*` + `/realtime` (mit Test-Doubles für HA)
→ Kiosk-Web-App-Skeleton unter `/kiosk` → von dort Feature für Feature
(K2 → K3 → K4). K5 (tvOS-Listener) kommt zuletzt, sobald wieder ein Mac da ist.

Der nächste Schritt nach diesem Plan sind die **Mockups** (Startbild,
Haussteuerung, Roon, Podcasts, Vault-Browse) als HTML in
[`../mockup/`](../mockup/).

---

## Feature-Details (im Durchsprechen geklärt)

Wird beim Punkt-für-Punkt-Durchgehen je Feature gefüllt; ergänzt die groben
Milestones oben um die konkreten Entscheidungen.

### Roon-Steuerung (K3) — geklärt

**API-Realität:** Roon-Anbindung existiert in vault-api noch nicht (für K3 aus
M8 vorgezogen) und braucht eine **einmal in Roon freigeschaltete Extension**.
„Suchen" ist kein flacher Endpunkt, sondern Roons **hierarchischer Browser**
(`browse`/`load`, seitenweise) — vault-api kapselt ihn in eine saubere
`/music/*`-API. „In allen Räumen" = **Zonen-Gruppierung** (synchrones
Multiroom; nicht jede Zone ist gruppierbar). **Album-Cover** kommen aus Roons
Image-API (von vault-api geproxyt) — Basis für die Vinyl-Optik.

**Entscheidungen:**

- **Suche: Album-zuerst, inkl. Streaming.** Ein Treffer = eine Platte;
  Tidal/Qobuz werden mitgesucht, wenn in Roon verbunden (nicht nur lokale
  Bibliothek). Künstler/Tracks/Playlists sekundär.
- **„Überall"-Button + Raum-Picker.** Ein Tipp gruppiert alle gruppierbaren
  Zonen und spielt synchron; zusätzlich wählbare Teilmenge. **Lautstärke pro
  Raum** *und* als Gruppe.
- **Queue puristisch ausgeblendet, kein Shuffle/Repeat.** Plattenteller-Metapher:
  eine Platte liegt auf, keine sichtbare Warteschlange.
- **Transport:** Play/Pause, Skip vor/zurück, Seek (am Fortschritt ziehen),
  Lautstärke — für aktive Zone/Gruppe.
- **Einstieg „Plattenregal":** zuletzt hinzugefügt / Favoriten als Reihe von
  Plattencovern, aus der man direkt auflegt; Suche daneben.
- **Now-Playing als Plattenspieler:** Cover rund als Vinyl (dreht sich) mit
  Tonarm, daneben Titel/Album/Künstler + Transport; Räume als umschaltbare Chips.
