# Vault — Dokumentation & Review

Vault ist ein privater Apple-TV-Medienclient für eine selbst gehostete
Jellyfin-Bibliothek, mit eigener FFmpeg→VideoToolbox-Playback-Engine für
MKV/HEVC-Inhalte, die `AVPlayer` nicht abspielt. Ziel ist nicht ein
generischer Jellyfin-Client, sondern ein auf die eigene Sammlung optimiertes
„persönliches Netflix": entdecken → anfragen → ansehen, plus Musik über Roon.

Dieses Verzeichnis bündelt die Doku für ein Review.

## Lesereihenfolge fürs Review

1. **Dieses Dokument** — Überblick, Status, Architektur in zwei Sätzen.
2. **[architecture-api-first.md](architecture-api-first.md)** — die Zielarchitektur
   (API-First) und die getroffenen Entscheidungen. Das ist das „Wohin".
3. **[implementation-current.md](implementation-current.md)** — was heute im Code
   steht (v. a. die Player-Engine). Das ist das „Was bisher".
4. **[../Mockup/vault-mockup.html](../Mockup/vault-mockup.html)** — das Design aller
   Screens als eigenständiges HTML (am Handy ansehbar).
5. **[../README.md](../README.md)** — Build-Anleitung (Mac) für den tvOS-Teil.

## Status auf einen Blick

| Bereich | Stand |
|---|---|
| tvOS-App M1–M3 (Bibliothek, Browse, Player) | **geschrieben, noch nie kompiliert** |
| Player-Engine (FFmpeg→VideoToolbox, A/V-Sync, Seek) | geschrieben; Risiko: C-Interop/Linking beim ersten Build |
| Unit-Tests (DTO, URL-Builder, PacketQueue, PCMRingBuffer) | geschrieben |
| Design-Mockup (13 Screens + Design-System) | aktuell, am Handy reviewbar |
| `vault-api` Backend (FastAPI) | **M1–M4 gebaut & getestet**: `/health`, `/library/*`, `/stream/*`, Web-Config-UI (M1–M3) + `/discover/*`, `/search`, `/request/*` (M4); 55 Tests grün |
| Zielarchitektur API-First | entschieden, dokumentiert |

> Größtes offenes Risiko: Der Custom-Player ist noch nie auf echter
> Apple-TV-Hardware gelaufen. Erster Schritt am Mac ist „spielt ein MKV?".

## Architektur in zwei Sätzen

Die App kennt genau einen Endpunkt — `vault-api` auf dem NAS —, der Jellyfin,
Radarr/Sonarr/Lidarr, TMDB, OMDb, Roon und (optional) Claude orchestriert und
alle Keys hält. Einzige Ausnahme: die Video-Stream-Bytes fließen direkt von
Jellyfin zur App (LAN, gleicher Docker-Host).

## Getroffene Entscheidungen (Kurzfassung)

1. **Discovery** direkt über TMDB (eigener Key ab M4).
2. **Externe Scores** zuerst aus Jellyfin-Feldern, OMDb optional ab M5.
3. **LLM-Begründungen** ja, als Schicht ab M7.
4. **Empfehlungen** in zwei getrennten Regalen (neu/anfragbar vs. Bibliothek).
5. **Roon** volle Integration ab M8 (Steuerung, Zonen, Musikauswahl,
   Empfehlungen via Lidarr/Roon).

Details und Begründungen in [architecture-api-first.md](architecture-api-first.md).

## Milestones

- **M1–M3** Kern: Bibliothek, Browse-UI, Custom-Player. *(tvOS geschrieben;
  vault-api `/health` `/library/*` `/stream/*` + Web-Config-UI gebaut & getestet,
  siehe [`../../vault-api/`](../../vault-api/). Offen: `VaultClient` am Mac an
  vault-api anbinden.)*
- **M4** Anfragen (Radarr/Sonarr), Suche, TMDB-Discovery. *(vault-api
  `/discover/*` `/search` `/request/*` gebaut & getestet. TMDB-Key erforderlich.)*
- **M5** Bewertungen (→ Jellyfin) & externe Scores.
- **M6** Empfehlungs-Engine (content-based, serverseitig).
- **M7** LLM-Begründungen (Claude).
- **M8** Musik: Roon-Steuerung + Lidarr-Anfragen + Musik-Empfehlungen.

## Repo-Layout

```
Vault/
  README.md                 Build-Anleitung (Mac) + Architektur-Hinweis
  project.yml               XcodeGen-Projektdefinition
  Vault/                    tvOS-App (Swift)
    App/  Models/  Networking/  Settings/  UI/  Player/
  VaultTests/               Unit-Tests (reine Logik)
  Mockup/vault-mockup.html  Design-Mockup aller Screens
  docs/                     diese Doku
    README.md
    architecture-api-first.md
    implementation-current.md
```

## Design-Sprache

Dark `#0A0A0C`, Akzent Amber `#E8A030`, SF-Pro, große Grade für 3 m Sehabstand.
Fokus überall: Skalierung ~1.1× + Amber-Ring + weicher Schatten. Einheitliches
SVG-Icon-Set und Button-System (siehe Mockup, Abschnitt „0 · Design-System").
