# Kiosk-Screen-Review — nächste Ausbauwelle

Stand: 2026-06-24. Dieses Dokument ist bewusst Planung, kein Implementierungs-
Ticket. Ziel: die aktuellen Screens anhand der echten Kiosk-Nutzung sortieren,
Verbesserungen ausformulieren und daraus spaeter parallel bearbeitbare Pakete
schneiden.

## Prioritaet

1. **Musik/Roon** und **Podcasts** bleiben die wichtigsten Screens.
2. **Vault** bleibt visuell stark, braucht aber bessere Klickbarkeit und bessere
   Kuratierung.
3. **Heute/Infoscreen** wird als nuetzlicher Daily-Screen neu gedacht.
4. **Wohnung** wird entpriorisiert, bis klar ist, welche Haussteuerung wirklich
   taeglich gebraucht wird.

## 1. Musik/Roon

### Beobachtung

- Die Seite wirkt vom Grunddesign her sehr gelungen.
- Es werden aber immer die gleichen Alben angezeigt.
- Es fehlt eine echte Suche, um gezielt etwas anderes aufzulegen.
- Now Playing aktualisiert sich nicht live genug; man muss manuell refreshen.
- CoverArt koennte deutlich groesser und cinematicer eingesetzt werden, eher wie
  Vault/Film-Backdrops.

### Zielbild

Der Musikscreen soll sich wie ein grosses digitales Plattenregal anfuehlen:
links bzw. prominent die aktuelle Wiedergabe mit grosser CoverArt, darunter
Transport und Raumsteuerung; daneben Suche und Regalreihen. Suche ist nicht
Nebenfunktion, sondern der Hauptweg, um neue Musik aufzulegen.

### Ideen

- Prominenter Now-Playing-Bereich mit grossem Cover, optional blurred/dimmed
  CoverArt-Hintergrund.
- Suchleiste direkt auf der Musikseite, mit Ergebnisgruppen: Alben zuerst,
  danach Artists/Tracks nur wenn sauber abbildbar.
- "Zuletzt hinzugefuegt", "Favoriten", "Alben-Suche" als Tabs oder kompakte
  Filterchips statt immer derselben statischen Reihe.
- Live-Aktualisierung via `/realtime` oder kurz getaktetes Polling von
  `/music/zones`, solange der Screen aktiv ist.
- Wenn Musik laeuft: Cover/Backdrop auch als Input fuer Ambient/Idle.

### Agentenpaket M1: Roon-Suche in der UI

**Aufgabe:** vorhandenes `/music/search` in die Kiosk-Musikseite integrieren.

**Akzeptanz:**

- Suchfeld auf Musikseite.
- Eingabe zeigt Ergebnisse ohne Fullscreen-Reload.
- Ein Ergebnis kann per Tap abgespielt werden.
- Leere/fehlerhafte Suche zeigt einen ruhigen Empty-State.

### Agentenpaket M2: Live-Now-Playing

**Aufgabe:** Now Playing automatisch aktualisieren.

**Akzeptanz:**

- Trackwechsel erscheint ohne manuelles Neuladen.
- Fortschritt/Position laeuft sichtbar weiter.
- Polling pausiert oder reduziert sich, wenn der Screen nicht sichtbar ist.

### Agentenpaket M3: CoverArt-Layout

**Aufgabe:** Musikscreen visuell ueberarbeiten.

**Akzeptanz:**

- CoverArt ist deutlich groesser.
- Kein Text ueber unruhigem Bild ohne Lesbarkeits-Layer.
- Mobile/Kiosk-Viewport bleibt ohne Ueberlappungen.

## 2. Podcasts

### Beobachtung

- Podcasts brauchen eine bessere Pflegemoeglichkeit.
- Feed-Konfiguration im Admin ist fuer echten Alltag zu sperrig.
- Suche/Subscribe ist backendseitig vorbereitet, muss aber im Kiosk/Admin sauber
  bedienbar werden.

### Zielbild

Podcasts sollen wie eine abonnierte Mediathek funktionieren: Shows suchen,
hinzufuegen, Episoden starten, Fortschritt behalten, Gehoertes abhaken.

### Ideen

- Podcast-Suche im Kiosk: "Sendung suchen" → Treffer → abonnieren.
- Kleine Verwaltungsansicht: abonnierte Shows, Entfernen, Reihenfolge optional.
- Episodenlisten mit Resume/Gehoert-Status sichtbarer machen.
- Optional spaeter OPML-Import im Admin.

### Agentenpaket P1: Podcast-Suche und Subscribe im Kiosk

**Aufgabe:** `/podcasts/search` und `/podcasts/subscribe` im UI nutzbar machen.

**Akzeptanz:**

- Suchfeld fuer Podcasts.
- Treffer zeigen Titel, Autor, Cover.
- "Abonnieren" fuegt Feed hinzu.
- Danach taucht die Show ohne manuelles Config-Edit in der Uebersicht auf.

### Agentenpaket P2: Podcast-Verwaltung

**Aufgabe:** Abos besser pflegen.

**Akzeptanz:**

- Liste abonnierter Shows.
- Entfernen/Deaktivieren eines Feeds.
- Optional Feed-URL manuell hinzufuegen.

## 3. Wohnung

### Beobachtung

- Der aktuelle Wohnungsscreen ist optisch nicht stark genug.
- Licht per Szenen-Chips fuehlt sich zu grob an; Slider waeren besser.
- Heizung ist aktuell nicht so wichtig und nimmt zu viel gedanklichen Raum ein.

### Zielbild

Wohnung wird nicht als komplexes Smart-Home-Cockpit gebaut, sondern als ruhige
Schnellsteuerung fuer Dinge, die am Kiosk wirklich Sinn ergeben: Lichtstimmung,
Kaffee/Steckdosen, offene Fenster, vielleicht Luft/Temperatur als Status.

### Ideen

- Licht pro Raum als Slider: Helligkeit, optional Farbtemperatur wenn verfuegbar.
- Szenen bleiben als kleine Presets, aber nicht als Hauptsteuerung.
- Heizung einklappen oder auf reine Statuszeile reduzieren.
- Sinnvolle Zusatzinfos:
  - offene Fenster/Tueren
  - Lampen an
  - Kaffee/Steckdosen
  - Anwesenheit Jan/Tanni nur wenn wirklich nuetzlich
  - Luftqualitaet/Feuchtigkeit, falls HA gute Sensoren hat

### Entscheidungsvorschlag

Wohnung erstmal nach hinten schieben. Nur reparieren, wenn es technische
Nebeneffekte fuer Heute/Idle braucht. Musik, Podcasts, Heute und Vault liefern
mehr Alltagswert.

### Agentenpaket W1: Licht-Slider-Konzept

**Aufgabe:** HA-Lichtsteuerung auf Slider vorbereiten.

**Akzeptanz:**

- Backend liefert pro Raum dimmbare Licht-Entitaeten mit Helligkeit.
- UI kann Helligkeit setzen.
- Fallback fuer nicht dimmbare Lichter bleibt An/Aus.

## 4. Heute/Hausuebersicht

### Beobachtung

- Die Hausuebersicht funktioniert aktuell nicht gut.
- News sollen dort raus.
- Stattdessen: ausfuehrlichere Wettervorhersage, naechste 4 Termine,
  Einkaufsliste. Die Einkaufsliste wird aktuell gar nicht angezeigt.

### Zielbild

Heute ist der Morgen-/Zwischendurch-Screen: Was ist los, was muss raus, was
brauchen wir, wie wird das Wetter. Keine Spielerei, sondern schnelle Orientierung.

### Inhalte

- Wetter jetzt + Tagesverlauf + naechste Tage kompakt.
- Naechste 4 Termine aus den relevanten Kalendern.
- Einkaufsliste prominent, mit Checkboxen.
- Optional: Muell/Abholung, Pendel-/HVV-Info, Paketstatus, wenn spaeter Daten
  verfuegbar sind.

### Agentenpaket H1: Wetter ausbauen

**Aufgabe:** Today-Backend und UI fuer Wettervorhersage erweitern.

**Akzeptanz:**

- Heute zeigt aktuelle Temperatur, Regenwahrscheinlichkeit/Condition und
  Forecast fuer mehrere Zeitpunkte/Tage.
- Keine News-Kachel mehr auf dem Heute-Screen.

### Agentenpaket H2: Termine und Einkaufsliste

**Aufgabe:** Termine auf 4 begrenzen und Todo/Einkaufsliste sichtbar machen.

**Akzeptanz:**

- Genau die naechsten 4 relevanten Termine sichtbar.
- Einkaufsliste wird angezeigt.
- Abhaken funktioniert oder ist bewusst als Folgeaufgabe markiert.

## 5. Vault

### Beobachtung

- Der Vault-Screen gefaellt grundsaetzlich sehr gut.
- Die grosse Empfehlung links ist nicht klickbar.
- Rechts erscheinen vor allem Serienfolgen.
- Bei Serien soll hoechstens eine Folge pro Serie sichtbar sein.
- Es sollen auch Filme beigemischt werden.

### Zielbild

Vault ist ein kuratierter Leanback-Chooser: eine grosse Empfehlung, daneben
wenige, hochwertige Alternativen. Alles ist tappable. Serien duerfen auftauchen,
aber nicht als mehrere Folgen derselben Serie die Flaeche auffressen.

### Ideen

- Grosse Empfehlung links als voll klickbare Karte: Detail/Trailer/Play-Overlay.
- Rechte Liste dedupliziert Serien nach `series_id`.
- Mischung aus "Next up", Filmen und Empfehlungen.
- Klare Typ-Badges: Film, Serie, Folge.
- Optional Filterchips: Filme, Serien, Weitersehen.

### Agentenpaket V1: Klickbarkeit der Hero-Empfehlung

**Aufgabe:** grosse linke Empfehlung interaktiv machen.

**Akzeptanz:**

- Tap/Klick oeffnet dieselbe Detail-/Play-Aktion wie kleinere Items.
- Fokus-/Hover-/Pressed-State sichtbar.

### Agentenpaket V2: Vault-Kuratierung

**Aufgabe:** Serienfolgen deduplizieren und Filme beimischen.

**Akzeptanz:**

- Maximal eine Folge pro Serie in der rechten Liste.
- Mindestens einige Filme, wenn Bibliothek/Empfehlungen welche liefern.
- Tests fuer Dedupe-Regel.

## 6. Idle-Infoscreen

### Beobachtung

Der Idle-Modus soll nicht nur ein Screensaver sein, sondern ein simulierter
Info-Screen wie in Bahnen: wechselnde Tafeln, ruhig, gross, klar.

### Zielbild

Nach Inaktivitaet rotiert der Kiosk durch einzelne, vollflaechige Info-Seiten.
Jede Seite hat genau eine starke Botschaft, keine Dashboard-Ueberladung.

### Rotationskarten

- Wettervorhersage.
- Filmempfehlung.
- Serienempfehlung.
- Headlines mit kurzer Zusammenfassung, eine Headline pro Seite.
- Foto.
- Optional Now Playing, wenn Musik/Podcast laeuft.

### Foto-Kuratierung

Fotos sollen nicht komplett zufaellig sein. Gewuenscht: nur Fotos, auf denen
bestimmte Personen zu sehen sind.

Immich-Optionen, die zu pruefen sind:

- Suche nach Personen-IDs/Personen-Namen, falls Immich-API das stabil erlaubt.
- Dediziertes Immich-Album "Kiosk" als robuste erste Version.
- Spaeter: Album automatisch aus Personenfilter fuellen.

### Agentenpaket I1: Idle-Rotation als Infoboard

**Aufgabe:** vorhandenen Ambient-Modus in einzelne Info-Tafeln umbauen.

**Akzeptanz:**

- Jede Karte ist vollflaechig und eigenstaendig.
- Rotation zwischen Wetter, Vault-Empfehlung, Headlines und Foto.
- Antippen beendet Idle und kehrt zum vorherigen Screen zurueck.

### Agentenpaket I2: Immich-Personenfilter recherchieren

**Aufgabe:** klaeren, wie Immich Fotos bestimmter Personen per API liefert.

**Akzeptanz:**

- Dokumentierte API-Route oder belastbarer Fallback.
- Vorschlag fuer Config: `person_ids`, `album_id`, `mode`.
- Kein Secret im Repo.

## 7. Parallelisierung

Gute Parallelpakete ohne starke Konflikte:

- **M1 Roon-Suche UI**
- **M2 Live-Now-Playing**
- **P1 Podcast-Suche/Subscribe UI**
- **H1 Wetter ausbauen**
- **V1 Hero klickbar**
- **I2 Immich-Personenfilter recherchieren**

Pakete mit hoeherem Konfliktrisiko, besser nacheinander:

- **M3 CoverArt-Layout** und **M1/M2**, weil alle dieselbe Musikseite anfassen.
- **H1** und **H2**, weil beide Today-Modelle und Today-UI betreffen.
- **I1** nach H1/V2, weil Idle von Wetter/Vault-Daten profitiert.

## 8. Offene Produktentscheidungen

- Soll **Wohnung** vorerst aus der Hauptnavigation nach hinten wandern?
- Welche Wetterquelle ist gewuenscht: HA `weather.*`, eigener Forecast-Dienst
  oder beides mit HA zuerst?
- Welche Podcast-Verwaltung gehoert auf den Kiosk, welche in die Admin-UI?
- Welche Personen sollen fuer Immich-Fotos erlaubt sein?
- Soll der Idle-Infoscreen News ueber HA-Entitaeten, RSS oder eine eigene
  News-API bekommen?
