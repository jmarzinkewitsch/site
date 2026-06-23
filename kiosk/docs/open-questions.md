# Kiosk-Dashboard — Offene Punkte & lokal zu prüfen

Stand der Arbeit: Architektur-Durchgang **komplett** (alle vier Bereiche in
[`architecture.md`](architecture.md) festgehalten), erstes Mockup steht
(Startbild „Zuhause" als wischbare Vollbild-Seite,
[`../mockup/kiosk-mockup.html`](../mockup/kiosk-mockup.html)).

Dieses Dokument sammelt, was noch offen ist — getrennt nach „brauche **deine
Entscheidung**", „kann ich erst **mit verbundenem HA**" und „**Stilfragen** zu
den Mockups".

---

## 1 · Lokal mit Home Assistant prüfen (dein Review)

Erst mit erreichbarem HA möglich — die Build-Umgebung kommt nicht in dein LAN.
Diese Antworten brauchen wir, bevor K2 (HA) und K5b (Apple-TV-Cast) gebaut werden:

- [ ] **Long-Lived Access Token** in HA erstellen (Profil → Sicherheit) — kommt
      später in vault-api, nicht ins Git.
- [ ] **Welche Entitäten gibt es?** Grobe Liste je Domain für die Kuratierung:
      `scene.*` (Licht-Szenen), `climate.*` (Heizung), der Kaffee-`switch.*`,
      `light.*`, `binary_sensor.*` (door/window), `lock.*`, Temperatur-`sensor.*`,
      `weather.*`, `person.*`.
- [ ] **Licht-Szenen:** Gibt es `scene.*` pro Raum (z. B. Hell/Abend/Aus), oder
      müssen die in HA erst angelegt werden? (Das Mockup setzt Szenen voraus.)
- [ ] **Kaffeemaschine:** bestätigt nur an/aus (Steckdose) — welche `switch`-Entität?
- [ ] **Apple TV in HA (für K5b):** Kann HA ihn **wecken** (`media_player.turn_on`)
      *und* die **Vault-App starten** (`media_player.select_source` / Quellenliste)?
      Taucht die Vault-App in der Quellenliste auf? Daran hängt der Cast-Weg.
- [ ] **Music Assistant (für K4 Podcasts):** über HA erreichbar? Welche **Player
      = dieselben Lautsprecher wie Roon**? (Ziel für die Podcast-Wiedergabe.)

---

## 2 · Offene Fäden aus dem Architektur-Durchgang

1. **ZEIT-Premium-Podcasts (K4):** Im ZEIT-Audio/Z+-Konto prüfen, ob es einen
   **persönlichen RSS-Feed mit Token** für andere Podcast-Apps gibt.
   - vorhanden → Token-URL in den Index, inkl. werbefrei.
   - nur Apple Podcasts / Spotify → diese Folgen bleiben das Einzige, was der
     Kiosk nicht ersetzen kann. (Details in `architecture.md` → Podcasts.)
2. **HA-Entity-Kuratierung (K2):** konkrete Auswahl erst mit verbundenem HA
   (siehe Checkliste oben); die Heuristik (welche Domain steuern/anzeigen) steht.

---

## 3 · Stilfragen zu den Mockups

Zum Startbild „Zuhause" (wischbare Vollbild-Seite):

1. **Zuhause-Gliederung:** nach **Funktion** (aktueller Stand: Licht-Block /
   Heizung-Block) — oder nach **Räumen** (eine große Kachel je Raum, die Licht +
   Heizung dieses Raums zusammenfasst)?
2. **Status-Details:** reicht der **Glance im Top-Streifen**, oder zusätzlich auf
   der Zuhause-Seite die Detail-Status (welche Fenster offen, Schlösser)?
3. **Optik grundsätzlich** ok (Wisch-Modell, Top-Streifen, Größen)?

Sobald der Stil sitzt, folgen die restlichen Screens: **Musik** (Plattenspieler),
**Podcasts**, **Vault** — im selben Rahmen.

---

## 4 · Geplante Reihenfolge danach

Mockups fertigstellen → dann Bau in Milestone-Reihenfolge:
**K2** (Home Assistant, Fundament) → **K3** (Roon) → **K4** (Podcasts) →
**K5a** (Vault-Discover am Kiosk) → **K5b** (Cast zum Apple TV, braucht Mac +
tvOS-Listener). Begründung und Details in
[`architecture.md`](architecture.md) → Milestones.
