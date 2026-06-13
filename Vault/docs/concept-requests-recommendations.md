# Konzept: Anfragen & Empfehlungen

Stand: Planungsdokument, noch kein Code. Baut auf Milestones 1–3 (Bibliothek,
Browse-UI, Custom-Player) auf. Ziel: Vault von „Player für meine Bibliothek"
zu „Entdecken → Anfragen → Abspielen" erweitern — als **persönliches Netflix**
für eine Ein-Personen-Installation.

Entschiedene Rahmenbedingungen:

- Infrastruktur: **Jellyfin + Radarr/Sonarr**, **kein Jellyseerr**.
- Anfragen daher **direkt gegen die Radarr/Sonarr-API**.
- Kein eigenes Backend. Alles läuft on-device in der tvOS-App; ausgehende
  Calls nur an Jellyfin, Radarr/Sonarr und (für Empfehlungen) TMDB/OMDb.

---

## Teil A — Filme/Serien anfragen (Radarr/Sonarr)

### Flow aus Nutzersicht

1. In einem „Entdecken"-Regal oder über Suche einen Titel finden, der **nicht**
   in der Bibliothek ist.
2. Detailseite zeigt statt „Abspielen" einen **„Anfragen"**-Button.
3. Tippen → Titel wird Radarr/Sonarr hinzugefügt und sofort zur Suche
   freigegeben. Button wechselt zu **„Angefragt"** bzw. zeigt Download-Fortschritt.
4. Sobald der Download fertig importiert ist, taucht der Titel in Jellyfin auf
   und wird normal abspielbar.

### Technische Umsetzung

Radarr und Sonarr haben fast deckungsgleiche v3-REST-APIs. Auth über
`X-Api-Key`-Header. Die nötigen Endpunkte:

| Zweck | Radarr | Sonarr |
|---|---|---|
| Suche/Discovery | `GET /api/v3/movie/lookup?term=` | `GET /api/v3/series/lookup?term=` |
| Quality-Profile | `GET /api/v3/qualityprofile` | `GET /api/v3/qualityprofile` |
| Root-Folder | `GET /api/v3/rootfolder` | `GET /api/v3/rootfolder` |
| Hinzufügen + suchen | `POST /api/v3/movie` | `POST /api/v3/series` |
| Download-Status | `GET /api/v3/queue` | `GET /api/v3/queue` |

**Eleganter Nebeneffekt:** Der `lookup`-Endpunkt von Radarr/Sonarr proxyt
selbst TMDB/TVDB. Für das *Anfragen* brauchen wir also **keinen eigenen
TMDB-Key** — die Suche läuft komplett über die *arr*-Instanzen, und die
Antwort sagt sogar, ob ein Titel schon hinzugefügt ist.

**Hinzufügen (Radarr-Beispiel):** POST mit `tmdbId`, gewähltem
`qualityProfileId`, `rootFolderPath`, `monitored: true` und
`addOptions: { searchForMovie: true }`. Sonarr analog mit `tvdbId`,
`seasonFolder: true`, `addOptions: { searchForMissingEpisodes: true }`.

**Statusermittlung** kombiniert drei Quellen:

- Nicht in Bibliothek + nicht in Radarr/Sonarr → **„Anfragen"**.
- In Radarr/Sonarr, aber `hasFile == false` → **„Angefragt / lädt"**
  (Fortschritt aus `/queue`).
- In Jellyfin vorhanden → normaler **„Abspielen"**-Pfad.

### Neue Einstellungen

Pro Dienst eine URL + ein API-Key, dazu die Default-Auswahl für
Quality-Profile und Root-Folder (einmalig, mit Override pro Anfrage):

- Radarr-URL + API-Key
- Sonarr-URL + API-Key
- Standard-Quality-Profile / Root-Folder je Dienst

### Architektur-Einordnung

Neuer, isolierter Networking-Layer analog zum Jellyfin-Client:

```
Vault/Networking/Arr/
  ArrClient.swift          // generisch, X-Api-Key, GET/POST
  RadarrService.swift      // lookup, add, queue
  SonarrService.swift      // lookup, add, queue
  Models/ (ArrLookupResult, QualityProfile, RootFolder, QueueItem)
RequestService.swift       // vereint: Status bestimmen, Anfrage stellen
```

---

## Teil B — Empfehlungen nach Geschmack

### Drei Bausteine

**1. Geschmackssignal (was mag ich?)**

Kein eigener Speicher nötig — Jellyfin liefert das meiste:

- **Eigene Bewertung 0–10** pro Titel (`UserData`, beschreibbar). Wird in
  Vault als Sterne-/Daumen-UI angezeigt und zurückgeschrieben.
- **Implizit:** durchgeschaut vs. abgebrochen, Wiederholungen, Favoriten,
  `PlayCount`.

**2. Externe Wertungen (IMDB / Rotten Tomatoes)**

Teilweise schon da: Jellyfin füllt `CommunityRating` (≈ IMDB) und
`CriticRating` (≈ Rotten Tomatoes) bei vielen Titeln. Für Vollständigkeit:

- **OMDb** (`omdbapi.com`, kostenloser Key): liefert IMDB-, Rotten-Tomatoes-
  und Metacritic-Score in einem Call, adressiert per IMDB-ID
  (`ProviderIds.Imdb` aus Jellyfin).
- **TMDB** (kostenloser Key): Genres, Keywords, Cast/Crew sowie die
  Endpunkte `recommendations` / `similar` / `discover` für Kandidaten.

> Eine offizielle Rotten-Tomatoes-API existiert nicht — der Wert kommt über
> OMDb. Falls wir den OMDb-Key nicht wollen, reichen Jellyfins vorhandene
> Felder als Näherung.

**3. Vorhersage-Engine**

Für **einen Nutzer** ist Collaborative Filtering („andere mochten auch…")
ungeeignet — es fehlen die vielen Nutzer. Richtiger Ansatz: **Content-based**,
on-device, in drei Schritten.

- **Profil bilden:** aus hoch bewerteten/durchgeschauten Titeln gewichtete
  Merkmale aggregieren — Genres, Keywords, Regie, Haupt-Cast, Jahrzehnt,
  Laufzeit-Band. Gewicht steigt mit deiner Bewertung und mit Abschlussrate.
- **Kandidaten sammeln:** TMDB-`recommendations`/`similar` deiner Lieblinge
  plus gezieltes `discover` (deine Top-Genres). Schon Gesehenes herausfiltern.
- **Scoren & begründen:** Ähnlichkeit (Merkmals-Überlappung × Profilgewichte)
  als Hauptfaktor, Qualitäts-Score (IMDB/RT) als Sekundärfaktor, plus ein
  kleiner Neuheits-/Aktualitätsbonus. Ausgabe rangiert, mit Klartext-Grund
  („Weil dir *Sicario* und *Dune* gefallen: Action-Thriller, Regie Villeneuve,
  RT 93 %").

**Optional — LLM-Schicht (Claude API):** Top-Lieblinge + Kandidatenliste an
Claude geben, um neu zu ranken und die Begründungen natürlicher zu machen.
Wenig Code, sehr gute Erklärungen — kostet API-Calls und muss gegen echte
TMDB-Titel geerdet werden (gegen Halluzination). Klares Add-on, kein Muss.

### Die Schleife

Empfehlungen liefern oft Titel, die **nicht** in der Bibliothek sind. Genau da
greift Teil A: Jede Empfehlung bekommt — je nach Verfügbarkeit — einen
**„Abspielen"**- oder **„Anfragen"**-Button. Entdecken → Anfragen → automatisch
herunterladen → ansehen.

### Architektur-Einordnung

```
Vault/Networking/Metadata/
  TMDBService.swift        // recommendations, similar, discover, keywords, credits
  OMDbService.swift        // imdb/rt/metacritic per IMDB-ID
Vault/Recommendations/
  TasteProfile.swift       // Merkmalsgewichte aus Jellyfin-UserData
  CandidateSource.swift    // Kandidaten holen + Bibliothek/Gesehenes filtern
  Recommender.swift        // Scoring + Begründung (rein, gut testbar)
  LLMRecommender.swift     // optional, Claude-API-Schicht
```

`TasteProfile` und `Recommender` sind reine Logik ohne UIKit/Netzwerk —
gut unit-testbar (im Gegensatz zur Player-Engine).

---

## Datenquellen & Keys (Übersicht)

| Quelle | Wofür | Key nötig? |
|---|---|---|
| Jellyfin | Bibliothek, Bewertungen, Gesehen-Status | bestehend |
| Radarr/Sonarr | Suche + Anfragen + Download-Status | X-Api-Key (vorhanden) |
| TMDB | Empfehlungs-Kandidaten, Genres/Keywords | kostenloser Key |
| OMDb | IMDB/RT/Metacritic-Scores | kostenloser Key (optional) |
| Claude API | LLM-Begründungen | nur falls LLM-Schicht |

Keys liegen lokal in der App (für eine private Installation vertretbar) — wie
beim Jellyfin-Token werden sie nicht in URLs, sondern in Headern gesendet.

---

## Sequenzierung (Vorschlag)

**Voraussetzung:** Milestones 1–3 müssen erst auf echtem Apple TV bauen und
laufen. Erst auf geprüftem Fundament aufstocken.

- **M4 — Anfragen:** Radarr/Sonarr-Client, Einstellungen, „Anfragen"-Button +
  Status, einfaches „Entdecken"-Regal (über *arr*-`lookup`/TMDB).
- **M5 — Bewertungen & externe Scores:** Bewertungs-UI (schreibt Jellyfin-
  Rating), IMDB/RT-Anzeige auf Detail & im Player-Overlay (OMDb/TMDB).
- **M6 — Empfehlungs-Engine:** `TasteProfile` + `Recommender`, „Für dich"-
  Screen mit begründeten Vorschlägen, verzahnt mit dem Anfragen-Button.
- **M7 — optional LLM-Begründungen.**

## Offene Entscheidungen (für später)

1. Discovery-Suche über *arr*-`lookup` (kein TMDB-Key) **oder** direkt TMDB
   (reicheres Material)? — Tendenz: mit `lookup` starten, TMDB für Empfehlungen.
2. OMDb-Key holen, oder reichen Jellyfins vorhandene Rating-Felder?
3. LLM-Begründungen: ja/nein (Kosten vs. Erlebnis)?
4. Sollen Empfehlungen auch schon vorhandene Bibliotheks-Titel mischen, oder
   bewusst auf „neue, anfragbare" fokussieren?
