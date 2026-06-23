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

**Bestandsaufnahme am 2026-06-23 per MCP erfolgt** — HA war aus der Session
erreichbar. Das meiste ist damit geklärt; offen bleibt nur das Token und das
Anlegen weniger Szenen:

- [ ] **Long-Lived Access Token** in HA erstellen (Profil → Sicherheit) — kommt
      später in vault-api, nicht ins Git. *(weiterhin offen — manueller Schritt)*
- [x] **Welche Entitäten gibt es?** 1363 Entitäten, 8 Bereiche. Relevant
      gemappt: 4 `climate.*` (Heizung je Raum), `switch.kaffeemaschine`,
      3 `binary_sensor.fenster_*`, `weather.wetter_in_hamburg`, `person.*`
      (Jan/Tanni/Kiosk), 16 `scene.*`. **`lock`-Domain leer** → Schlösser raus.
- [ ] **Licht-Szenen:** WZ (7) & SZ (8) vorhanden, aber benannt/reichhaltig;
      **Küche & Bad haben keine** → dort **je 3 anlegen** (Raster Hell·Mood·Aus).
      Flur hat kein smartes Licht. *(Anlegen = offener Schreibschritt in HA.)*
- [x] **Kaffeemaschine:** bestätigt — `switch.kaffeemaschine` (Sonoff S26, an/aus).
- [x] **Apple TV in HA (für K5b):** `media_player.appletv` + `remote.appletv`
      vorhanden → HA kann wecken/steuern; Quellen-/Launch-Details beim K5b-Bau
      verifizieren. Cast-Weg über HA bestätigt (kein pyatv nötig).
- [x] **Music Assistant (für K4 Podcasts):** `media_player.wohnzimmer_ma`
      vorhanden. Welcher MA-Player **exakt = Roon-Speaker** ist, beim K4-Bau
      festklopfen.

---

## 2 · Offene Fäden aus dem Architektur-Durchgang

1. **ZEIT-Premium-Podcasts (K4):** Im ZEIT-Audio/Z+-Konto prüfen, ob es einen
   **persönlichen RSS-Feed mit Token** für andere Podcast-Apps gibt.
   - vorhanden → Token-URL in den Index, inkl. werbefrei.
   - nur Apple Podcasts / Spotify → diese Folgen bleiben das Einzige, was der
     Kiosk nicht ersetzen kann. (Details in `architecture.md` → Podcasts.)
2. **HA-Entity-Kuratierung (K2):** konkrete Auswahl erst mit verbundenem HA
   (siehe Checkliste oben); die Heuristik (welche Domain steuern/anzeigen) steht.
3. **pyroon-Abdeckung (K3a):** Vor dem Port der Node-Jukebox prüfen, ob die
   Python-Lib `roonapi` (pyroon) alle genutzten Roon-Aufrufe abdeckt. Browse/
   load, Transport, Volume, Seek, Group/Ungroup/Transfer, Image und Zone-/Queue-
   Callbacks sollten passen; **zu verifizieren** sind `standby`/
   `convenience_switch` und `change_settings`. Fehlt etwas → dünner direkter
   MOO-Aufruf als Fallback. (Details in `architecture.md` → Roon-Steuerung.)
4. **Roon-Discovery aus dem vault-api-Container (K3a):** Erreicht der Container
   den Roon-Core per Multicast-Autodiscovery, oder muss `ROON_HOST` gesetzt
   bzw. Host-Networking genutzt werden? Heute löst das der separate Jukebox-
   Container — nach dem Port liegt es bei vault-api.

---

## 3 · Stilfragen zu den Mockups — geklärt (2026-06-23)

Zum Startbild „Zuhause":

1. **Zuhause-Gliederung:** **nach Funktion** (Variante A). Licht-Block mit
   **3 Szenen-Chips pro Raum** (Raster „Hell · [Mood] · Aus"), 4 Licht-Räume
   (WZ/SZ/Küche/Bad, **kein Flur**); Heizung-Block (4 Thermostate) + Kaffee.
2. **Status-Details:** **nur Glance im Top-Streifen** (offene Fenster, Lampen an,
   Wetter, Anwesenheit). **Schlösser raus** (keine `lock`-Entitäten). Detailtiefe
   eine Ebene darunter.
3. **Optik-Rahmen** (Wisch-Modell, persistenter Top-Streifen, Größen): **bestätigt**
   — die restlichen Screens im selben Rahmen.

**Neue Wisch-Seite „Heute"** zwischen Zuhause und Musik: Termine + Einkaufsliste/
Erinnerungen + News (Details in `architecture.md` → „Heute"-Seite).

Offener Mockup-Schritt: **Zuhause** auf diesen Stand neu bauen, **Heute** neu
anlegen, dann **Musik** (Plattenspieler), **Podcasts**, **Vault** — im selben
Rahmen.

---

## 4 · Geplante Reihenfolge danach

Mockups fertigstellen → dann Bau in Milestone-Reihenfolge:
**K2** (Home Assistant, Fundament) → **K3** (Roon) → **K4** (Podcasts) →
**K5a** (Vault-Discover am Kiosk) → **K5b** (Cast zum Apple TV, braucht Mac +
tvOS-Listener). Begründung und Details in
[`architecture.md`](architecture.md) → Milestones.
