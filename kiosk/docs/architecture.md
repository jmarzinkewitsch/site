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
7. **Roon:** Das bestehende Node-Jukebox-Backend wird **nach Python portiert**
   (`services/roon_extension.py` via pyroon) und hinter eine kuratierte
   `/music/*`-API gelegt; der separate Container und die alte Jukebox-Web-App
   entfallen. Details unter „Roon-Steuerung (K3)".

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
- **K3 — Roon am Kiosk.** Das Roon-Backend **existiert bereits** als separate
  Node-Jukebox (`roon-jukebox-api`, eigener Container); es wird **nach Python in
  vault-api portiert** und kuratiert. Zwei Schritte:
  - **K3a — Port & Kuratierung (pure Python):** `services/roon_extension.py`
    (Roon-Extension über `roonapi`/pyroon, Hintergrund-Thread mit
    `subscribe_zones`/`subscribe_queue`) + kuratierte `/music/*`-API; der rohe
    `/roon`-Passthrough, das `roon`-Docker-Profil und die alte Jukebox-Web-App
    entfallen. Ohne Pi baubar; echter Test braucht eine Roon-Core-Verbindung.
  - **K3b — Kiosk-Plattenspieler-UI** auf `/music/*` (Now-Playing als Vinyl,
    Transport, „Überall"-Button, Plattenregal).
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

**API-Realität:** Das Roon-Backend **existiert schon** — als selbstgebaute
Node-Jukebox (`vault-api/roon-jukebox-api/`, eigener Docker-Container, Roon-
Extension `de.jancloud.jukebox`). Sie hält den Live-Zustand (`subscribe_zones`,
`subscribe_queue`), kapselt Roons **hierarchischen Browser** (`browse`/`load`,
seitenweise) und proxyt die **Image-API** fürs Cover. vault-api spricht sie
heute nur über einen **rohen `/roon`-Passthrough** an — das Gegenteil der
Kuratierungs-Doktrin dieses Plans.

**Entscheidung: Port statt Bridge.** Die Jukebox-Logik wird nach Python in
vault-api gezogen und der Container abgeschafft (gewählt gegenüber „Node-Bridge
intern behalten", weil so der Live-Zustand **im selben Prozess** liegt und direkt
in `/realtime` fließt, statt über eine Container-Grenze gepollt zu werden).

- **`services/roon_extension.py`** — kapselt die Extension über die Community-
  Lib **`roonapi` (pyroon)**. Roons SDK ist callback-basiert und **synchron**,
  FastAPI ist async: Die Extension läuft als **Hintergrund-Thread**, verbindet
  beim App-Start (Autodiscovery oder `ROON_HOST`), pairt sich **einmalig**
  (persistenter Token in einem Volume, wie heute `config.json`) und hält
  `zones`/`queue` im Speicher — dasselbe State-Modell wie der Node-Server.
- **`routers/music.py`** — kuratierte `/music/*`-API; liest den Live-Zustand des
  Threads und ruft dessen Methoden. Ersetzt den rohen `/roon`-Proxy.
- **`/realtime`** multiplext `audio.nowplaying` direkt aus dem Thread.
- **Abgelöst:** `roon-jukebox-api/` (inkl. `public/index.html` — der Kiosk-
  Musik-Screen ersetzt die alte Web-App), das `roon`-Docker-Profil, der
  `/roon`-Passthrough.

**Endpunkt-Schnitt (Jukebox `/api/*` → kuratiertes `/music/*`):** `zones`/
`nowplaying` → `GET /music/zones`, `/music/nowplaying`; `transport`/`seek` →
`POST /music/transport`; `albums`/`search`/`album` → `GET /music/library`,
`/music/search`, `/music/album`; `play`/`queue` → `POST /music/play`;
`group`/`ungroup`/`transfer` → `POST /music/group` («Überall»-Button);
`image/:key` → `GET /music/image/{key}`. Bewusst **nicht** übernommen fürs
Kiosk-MVP: `settings` (Shuffle/Repeat) und `system` — passt zur puristischen
Plattenteller-Metapher.

„In allen Räumen" = **Zonen-Gruppierung** (synchrones Multiroom; nicht jede Zone
ist gruppierbar). Album-Suche bleibt Roons Browse-Baum (Album-zuerst, inkl.
Streaming), die Play-Auflösung läuft wie heute über den Baum bis zur
„Jetzt spielen"-Aktion.

**Risiken (vor dem Bau zu klären, siehe [open-questions.md](open-questions.md)):**

1. **pyroon-Abdeckung.** Browse/load, Transport, Volume, Seek, Group, Transfer,
   Image und Zone-/Queue-Callbacks deckt pyroon ab. Wenige Spezialaufrufe
   (`standby`/`convenience_switch`, `change_settings`) sind **gegen pyroons API
   zu verifizieren** — Fallback: dünner direkter MOO-Aufruf. **Erster Schritt
   von K3a**, nicht angenommen.
2. **Netzwerk/Discovery.** Der vault-api-Container muss den Roon-Core per
   Multicast-Discovery **oder** `ROON_HOST` erreichen (ggf. Host-Networking) —
   heute löst das der Jukebox-Container. Deployment-Constraint.

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

### Podcasts (K4) — geklärt

**Aufbau:** zwei Hälften — (a) Finden/Verwalten über einen **eigenen Index**
(Podcast Index / iTunes-Search + Feed-Parsing) mit **eigener Abo-Liste in
vault-api**; (b) Abspielen via **Music Assistant** auf denselben Lautsprechern
wie Roon. Roon und Music Assistant kennen sich nicht — beim Podcast-Start wird
**Roon im Ziel-Raum pausiert**.

**Entscheidungen:**

- **Eigener Index, Abo-zentriert.** Startbild = abonnierte Shows (neueste Folge
  oben); Suche dient v. a. dem Hinzufügen. Volle Abo-Verwaltung darf später ein
  Handy-Client übernehmen (gleiche vault-api-Liste). Bestehende Apple-Abos per
  **OPML-Import** einmalig übernehmbar.
- **Resume + gehört-Status: ja, in vault-api** (eigener SQLite-Speicher wie die
  Rating-Snapshots) — pro Episode Position merken und „erledigt" markieren.
- **Transport:** Play/Pause, ±30 s, Seek; **Geschwindigkeit „wo der Player es
  kann"**.
- **Ein wählbarer Raum** (kein Multiroom-Zwang); Roon dort beim Start pausieren.
- **Eigene Episoden-/Now-Playing-Ansicht**, klar getrennt von der Vinyl-Welt
  (quadratisches Show-Cover, Episodenliste mit Dauer/Restzeit, Fortschritt).

**Werbung überspringen:** automatisches Erkennen dynamischer Werbung ist *nicht*
zuverlässig machbar und bleibt bewusst draußen. Stattdessen: (1) **werbefreie
Premium-Feeds** nutzen, wo vorhanden; (2) **Kapitelmarken** auswerten und als
Werbung markierte Kapitel automatisch überspringen; (3) großzügiger
**±30 s-Skip** als Fallback.

**Offener Punkt — ZEIT-Premium-Podcasts:** Kostenlose ZEIT-Feeds sind normale
RSS-Feeds → integrierbar. Die bezahlten Exklusiv-/Werbefrei-Folgen aus „ZEIT
Audio"/Z+ werden laut Recherche über **Apple Podcasts Subscriptions / Spotify**
(geschlossene Plattformen) ausgeliefert — ein eigener Client kommt da **nur**
ran, wenn ZEIT zusätzlich einen **persönlichen RSS-Feed mit Token** anbietet.
**Zu prüfen:** im ZEIT-Audio/Z+-Konto nach „RSS-Feed für andere Podcast-Apps"
suchen. Wenn vorhanden → Token-URL in den Index eintragen (inkl. werbefrei);
wenn nicht → diese Folgen bleiben das einzige, was der Kiosk nicht von Apple
Podcasts übernehmen kann.

### Vault am Kiosk + Cast zum Apple TV (K5) — geklärt

Erweitert sich vom reinen „Anstoßen" zur **vollen Discover-Schleife am Kiosk**
(Küchen-Use-Case: raussuchen → ggf. Trailer → anfragen → am Apple TV abspielen).
Aufgeteilt in zwei Milestones, weil nur eines eine tvOS-Änderung braucht.

**K5a — Vault-Discover am Kiosk (kein tvOS-Eingriff, sofort baubar):**

- Nutzt die **bereits gebauten** vault-api-Endpunkte: `/library/*` (Browsen,
  Weiterschauen), `/search`, `/recommend` (Janno-/Tanno-Profile), `/request/*`
  (Radarr/Sonarr). Der Kiosk ist nur UI darauf.
- **Trailer laufen auf dem Kiosk selbst** (Chromium kann Video), nicht am Apple
  TV — kurze Vorschau am kleinen Schirm. Baut auf der vorhandenen
  Trailer-Vorarbeit auf (`vault-api`-Trailer-Stream).
- Schleife am Kiosk: **stöbern/empfehlen → Trailer → anfragen → später am Apple
  TV abspielen.**

**K5b — Cast zum Apple TV (Variante B, braucht Mac + tvOS-Listener):**

- **Wecken + Vault starten über Home Assistant** (funktioniert beim Nutzer schon;
  HAs Apple-TV-Integration weckt den Apple TV und startet die App als Quelle).
  **Kein eigenes pyatv-Pairing in vault-api nötig** — vault-api ruft HA. HDMI-CEC
  schaltet ab da Fernseher/Receiver mit; wenn der Apple TV läuft, läuft alles.
- **Richtiger Film an Resume-Stelle:** der Kiosk legt in vault-api ein **„offenes
  Abspiel-Kommando"** ab; die tvOS-App holt es **beim Start** und springt in den
  Player (bzw. reagiert live, wenn sie schon läuft). Dieser **minimale
  tvOS-Listener** ist das einzige nicht-rein-serverseitige Stück.
- Endpunkte: `POST /cast/appletv {itemId}` (setzt Wecken+Launch via HA in Gang
  und hinterlegt das Kommando), `GET /cast/appletv/pending` (App holt es ab),
  `GET /cast/appletv/status` (Kiosk-Feedback über `/realtime`).
- **Steuern** (Pause/Seek) bleibt bei der Apple-TV-Fernbedienung; Kiosk ist
  Auslöser, nicht Fernbedienung. Resume aus Jellyfin. Ein fester Apple TV.
- **Abhängigkeit:** setzt die HA-Anbindung (K2) voraus.

### Home Assistant (K2) — geklärt

**Rolle:** Fundament des Kiosks — HA macht dreierlei: Haussteuerung,
**Apple TV wecken/starten** (K5b) und **Music Assistant** für Podcasts (K4).
Deshalb wird HA zuerst gebaut.

**Basis:** vault-api spricht HA über **REST + WebSocket** mit einem
**Long-Lived Access Token** (einmal in HA erzeugt, liegt im Backend). Der
WebSocket speist Live-Zustände in `/realtime`. Nach außen gibt vault-api **nur
kuratierte, gemappte Entitäten** frei — kein roher Vollzugriff.

**Leitgedanke:** Das Startbild soll **„den sauberen Zustand der Wohnung auf den
ersten Blick"** zeigen. Daraus folgt die Trennung in zwei Flächen:

- **Steuern (schreibend) — bewusst nur drei:**
  - **Licht:** **3 Szenen pro Raum** nach dem Raster **„Hell · [Raum-Mood] · Aus"**
    (erste/letzte fix, Mitte = Signatur-Stimmung des Raums) — visuell konsistente
    Chip-Reihe. **Licht-Räume: Wohnzimmer, Schlafzimmer, Küche, Bad** (4). Der
    **Flur hat kein smartes Licht** und fällt raus. „Alles aus" global =
    `scene.wohnung_licht_aus`. Einzellampen/Dimmen nur in der Detailebene.
  - **Heizung:** **pro Raum** (`climate.*`) Ist-/Soll-Temperatur + Presets
    (Komfort/Eco/Aus) — 4 Thermostate (Küche/Bad/Schlafzimmer/Wohnzimmer).
  - **Kaffeemaschine:** **an/aus** (`switch.kaffeemaschine`, Sonoff-Steckdose) —
    simple Kachel, kein Status.
- **Status auf einen Blick (nur lesend, darf breiter sein):** die „ist alles in
  Ordnung?"-Übersicht. Reale Komposition: **offene Fenster** (3
  `binary_sensor.fenster_*` — Bad/Schlafzimmer/Wohnzimmer), **noch brennende
  Lampen** (`light.*`-An-Zustand: Anzahl + Räume), Raumtemperaturen, Wetter
  (`weather.wetter_in_hamburg`), Anwesenheit (`person.*` — Jan/Tanni/Kiosk).
  **Schlösser entfallen** — die `lock`-Domain ist in diesem HA leer.

**Kuratierung — Bestandsaufnahme erfolgt (Stand 2026-06-23):** Anders als ur-
sprünglich angenommen ist HA aus dieser Session **erreichbar** (MCP) — die
Inventur wurde gemacht. Befund: 1363 Entitäten, 8 Bereiche (Bad, Flur, Küche,
Schlafzimmer, Wohnzimmer + appletv/system). Relevant:

- **Szenen:** Wohnzimmer (7) & Schlafzimmer (8) **benannt & reichhaltig**
  (Couchmodus, Lesen, Lounge, Wind Down …), **nicht** „Hell/Abend/Aus". Küche,
  Bad, Flur: **keine Szenen**. → Plan: HA auf **3 Kiosk-Szenen pro Raum**
  ausrichten; für **Küche & Bad je 3 neu anlegen** (Schreibschritt), WZ/SZ nur
  3 referenzieren (Rest bleibt für Automationen/Sprache). Flur: kein Licht.
- **Heizung:** 4 `climate.*`-Thermostate sauber pro Raum; Presets via Helfer
  (`input_select` Eco, `input_number` Eco-/Wohlfühl-Temp) schon vorhanden.
- **Kaffee:** `switch.kaffeemaschine` (Sonoff, an/aus) — bestätigt.
- **K4/K5 live bestätigt:** `media_player.wohnzimmer_ma` (Music Assistant) und
  `media_player.appletv` + `remote.appletv` (HA steuert Apple TV → K5b-Cast ohne
  pyatv). Offen bleibt nur das **Long-Lived Access Token** (in HA zu erzeugen).

**Startbild:** Now-Playing (Roon/Podcast) + Wohnungs-Status-Übersicht + die drei
Steuer-Kacheln griffbereit; Detailtiefe (alle Leuchten, alle Sensoren) eine
Ebene darunter.

### „Heute"-Seite (HA-Glance, neu)

Eigene Wisch-Seite zwischen Zuhause und Musik (Reihenfolge: **Zuhause · Heute ·
Musik · Podcasts · Vault**). Bündelt die glanceable HA-Infos, die nicht auf die
Steuerseite passen: **heutige Termine** (6 `calendar.*`), **Einkaufsliste +
Erinnerungen** (`todo.*`) und die **News-Zusammenfassung** (`input_text.
hamburg_news_summary` / Morgen-Briefing). Rein lesend bzw. Liste abhaken; alles
über `/home/*` aus vault-api, kein roher HA-Zugriff.
