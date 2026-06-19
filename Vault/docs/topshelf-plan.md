# Vault — Top Shelf (Apple-TV-Home-Screen) — Umsetzungsplan

Status: Planungsdokument, **noch kein Code**. Ziel ist, Vault-Inhalte (Poster/
Hero-Bilder von Filmen und Serien) direkt im **tvOS-Home-Screen** über dem
App-Grid zu zeigen, wenn Vault in der obersten Reihe liegt. Bezug:
[architecture-api-first.md](architecture-api-first.md).

Gewählter Stil: **Carousel** (große, rotierende Hero-Bilder) — am nächsten am
„Stage"-Gefühl. (Alternative „Sectioned"/Poster-Reihen ist in §8 notiert.)

## 1. Abgrenzung: Top Shelf ≠ In-App-`StageView`

Es gibt zwei verschiedene „Bühnen":

| | In-App `StageView` | **Top Shelf (dieses Dokument)** |
|---|---|---|
| Wo | oben in Vaults eigener `HomeView` | System-Bereich des **tvOS-Home-Screens** über der App-Reihe |
| Framework | SwiftUI (bestehend) | `TVTopShelf` (neues Target) |
| Sichtbar | nur in der geöffneten App | nur wenn Vault in der **obersten Home-Reihe** liegt, ohne App-Start |
| Prozess | App | eigene **Extension** (separater Prozess) |

Die bestehende `StageView` bleibt unverändert; Top Shelf ist additiv.

## 2. Warum das gut zur Architektur passt

vault-api liefert bereits alles Nötige — kein neuer Backend-Baustein zwingend:

- `GET /library/continue` — Weiterschauen-Queue (inkl. `played_percentage`,
  `resume_position_seconds`).
- `GET /library/latest?type=Movie|Series` — neu hinzugefügt (nach Datum).
- Items tragen `poster_url` und `backdrop_url` (seit dem Image-Sizing-Fix mit
  `maxWidth=1920&quality=90` beim Backdrop — ideal als Hero-Bild).

Die Extension ist damit ein weiterer dünner Client im API-First-Sinn.

## 3. Komponenten im Überblick

```
Vault.app (bestehend)
  └─ ServerSettings  → liest/schreibt vault-URL + Bearer-Token
                       (Umstellung: UserDefaults.standard → App-Group-Suite)
  └─ Deep-Link-Handling (.onOpenURL)  → Detail öffnen / Player starten

VaultTopShelf.appex (NEU, Extension-Target)
  └─ TopShelfContentProvider : TVTopShelfContentProvider
        → ruft vault-api (/library/continue, /library/latest)
        → baut TVTopShelfCarouselContent mit Hero-Bildern + Deep-Link-Action

Gemeinsam genutzt
  └─ App Group  group.de.marzinkewitsch.vault   (geteilte UserDefaults)
  └─ Minimaler Vault-HTTP-Client (URL + Bearer)  — von beiden Targets nutzbar
```

## 4. Target & Projekt (XcodeGen `project.yml`)

Neues Target neben `Vault`/`VaultTests`:

```yaml
  VaultTopShelf:
    type: app-extension
    platform: tvOS
    sources:
      - VaultTopShelf
    settings:
      base:
        INFOPLIST_FILE: VaultTopShelf/Info.plist
```

- Das `Vault`-App-Target bettet die Extension ein (`dependencies: - target:
  VaultTopShelf` mit `embed: true`).
- Extension-`Info.plist` deklariert den Erweiterungspunkt:

```xml
<key>NSExtension</key>
<dict>
  <key>NSExtensionPointIdentifier</key>
  <string>com.apple.tv-top-shelf</string>
  <key>NSExtensionPrincipalClass</key>
  <string>$(PRODUCT_MODULE_NAME).TopShelfContentProvider</string>
</dict>
```

- Bundle-IDs: App `de.marzinkewitsch.Vault`, Extension
  `de.marzinkewitsch.Vault.TopShelf`.

## 5. Geteilte Konfiguration über App Group

Die Extension läuft als **eigener Prozess** und kommt nicht an
`UserDefaults.standard` der App. Daher:

1. **App Group** `group.de.marzinkewitsch.vault` als Entitlement bei **beiden**
   Targets aktivieren.
2. `ServerSettings` von `UserDefaults.standard` auf
   `UserDefaults(suiteName: "group.de.marzinkewitsch.vault")` umstellen
   (Keys bleiben: `vault.serverURL`, `vault.token`).
   - Einmalige **Migration**: vorhandene Standard-Defaults beim ersten Start in
     die Suite kopieren, damit bereits eingerichtete Geräte nicht neu
     onboarden müssen.
3. Die Extension liest URL + Token read-only aus derselben Suite.

> Sicherheitsnote: Der Bearer-Token liegt damit in der App-Group-Suite statt im
> Standard-Default. Beides ist unverschlüsselter UserDefaults-Speicher; im
> LAN-/Sideload-Kontext akzeptabel (siehe Annahmen in der Architektur). Falls
> später härter: Token in die Keychain mit App-Group-Access-Group.

## 6. Content Provider (Carousel)

Skizze (Pseudostruktur, kein finaler Code):

```
final class TopShelfContentProvider: TVTopShelfContentProvider {
  func loadTopShelfContent(completionHandler: @escaping (TVTopShelfContent?) -> Void) {
    // 1. URL + Token aus der App-Group-Suite lesen; fehlt etwas → nil zurück.
    // 2. vault-api parallel abfragen: /library/continue und /library/latest.
    //    Kurzer Timeout (~3 s) — der Home-Screen darf nicht hängen.
    // 3. Items mappen (siehe unten), auf z. B. max. 8–10 Hero-Items kürzen.
    // 4. TVTopShelfCarouselContent(style: .details, items: items) zurückgeben.
    // 5. Bei Fehler/Timeout: completionHandler(nil) (Home-Screen zeigt dann nichts).
  }
}
```

Mapping `LibraryItem` → `TVTopShelfCarouselItem`:

| Carousel-Feld | Quelle |
|---|---|
| `imageURL` (Shape `.hdtv`, 16:9) | `backdrop_url` (Fallback `poster_url`) |
| `title` | `title` (bei Episode: `series_name`) |
| `summary` | `overview` |
| `genres` | `genres` |
| `duration` | `runtime_seconds` |
| `playbackProgress` | `resume_position_seconds / runtime_seconds` (nur „Weiterschauen") |
| `playAction` / `displayAction` | `TVTopShelfAction(url:)` → Deep-Link (siehe §7) |

- **Bildwahl:** Hero-Carousel braucht Querformat → `backdrop_url`. Items ohne
  Backdrop überspringen oder Poster als Notnagel (Shape dann `.poster`).
- **Kuratierung:** vorne die „Weiterschauen"-Items (mit Fortschrittsbalken),
  danach „Neu hinzugefügt". Duplikate nach `id` entfernen.

## 7. Deep-Linking zurück in die App

1. **URL-Scheme registrieren** in der App-`Info.plist`
   (`CFBundleURLTypes` → Scheme `vault`).
2. Action-URLs je Item:
   - `vault://item/{id}` → Detailseite öffnen (`displayAction`).
   - `vault://play/{id}` → direkt in den Custom-Player (`playAction`).
3. **Routing in der App** (heute fehlt programmatische Navigation):
   - `RootTabView`/`HomeView` nutzen aktuell `NavigationStack` **ohne** gebundenen
     `path`. Für Deep-Links: eine Routing-State in `AppEnvironment` einführen
     (z. B. `pendingRoute: Route?`) und den `NavigationStack(path:)` der Home-Tab
     daran binden.
   - In `VaultApp` `.onOpenURL { url in env.handle(url) }`: URL parsen, Tab auf
     Home schalten, Item-`id` laden (`/library/item/{id}`) und Detail pushen bzw.
     `playerItem(for:)` starten.
4. Kalt- vs. Warmstart: `.onOpenURL` deckt beides ab; beim Kaltstart erst nach
   `isConfigured == true` ausführen (sonst Onboarding zuerst).

## 8. Backend (optional, später)

Für den Start **keine** Backend-Änderung nötig (`/continue` + `/latest`
genügen). Sauberer im API-First-Geist wäre später ein kuratierter Endpoint:

```
GET /topshelf   → fertige, gemischte Hero-Liste (Weiterschauen + Neu + ggf.
                  Empfehlungen ab M6), serverseitig kuratiert und gecacht.
```

Vorteil: Inhalt/Reihenfolge des Home-Screens ohne App-Update änderbar — genau
das Argument aus der Architektur. Bis dahin mischt die Extension clientseitig.

## 9. Aktualisierung & Lebenszyklus

- tvOS ruft `loadTopShelfContent` bei Bedarf auf; die Extension hält **keinen**
  Dauerzustand.
- Wenn die App den Inhalt ändert (z. B. nach Playback-Fortschritt), das System
  per `TVTopShelfContentProvider`-Änderungsnotification zum Neuladen anstoßen.
- Performance: kurzer Timeout, auf vault-apis Redis-Cache verlassen, Bildgrößen
  sind serverseitig schon begrenzt → wenig Bandbreite.

## 10. Risiken & Test

| Risiko | Anmerkung |
|---|---|
| **Nur auf Hardware testbar** | Top Shelf erscheint erst, wenn Vault in der **obersten** Home-Reihe liegt. Kein Simulator-Vollersatz. |
| Provisioning/Signing | App Group + Extension brauchen passende Profile (Apple-Developer-Account, beim Sideload beachten). |
| Reihenfolge-Abhängigkeit | Wie der Player: idealerweise **erst angehen, nachdem die App einmal auf echtem Apple TV lief** (siehe Architektur-Voraussetzung). |
| Token in App Group | Siehe Sicherheitsnote §5. |

## 11. Schrittfolge (Vorschlag)

1. App Group anlegen, `ServerSettings` auf Suite umstellen (+ Migration).
2. Extension-Target in `project.yml` + `Info.plist` + leerer Provider, der
   statische Test-Items liefert → auf Hardware sichtbar machen.
3. Minimalen Vault-Client (URL + Bearer, `GET`) für die Extension nutzbar machen
   (geteilt mit der App oder dupliziert-schlank).
4. `/library/continue` + `/library/latest` anbinden, echtes Mapping → Carousel.
5. URL-Scheme + Deep-Link-Routing in der App (Detail + Play).
6. Feinschliff: Kuratierung, Fortschrittsbalken, Refresh-Notification.
7. (Später) `GET /topshelf` serverseitig, Extension darauf umstellen.

## 12. Offene Entscheidungen

- **Stil endgültig:** Carousel (gewählt) vs. zusätzlich Sectioned-Reihen.
- **Play vs. Detail** als Default-Tap-Aktion (Vorschlag: „Weiterschauen"-Items →
  Play, „Neu"-Items → Detail).
- **Sofort clientseitig mischen** oder gleich den `/topshelf`-Endpoint bauen.

## 13. Feature-Idee: Hero-Bild mit Titel (Apple-TV-Optik)

**Wunsch:** Im Hero-Carousel soll der Titel schon **im Bild** stehen — wie in
der Apple-TV-App — damit man Film/Serie auch ohne Fokus erkennt.

**Warum nicht trivial:** Jellyfin-Backdrops sind ohne Titel. Apple komponiert
Backdrop + **Title-Treatment/Logo** („clearLogo", Jellyfin-Bildtyp `Logo`) zu
einem Bild. Die Top Shelf akzeptiert aber nur **eine** Bild-URL pro Item, d. h.
Backdrop + Logo müssen vorab zu einem Bild zusammengerechnet werden. Der reine
tvOS-Titel-Text (`carouselItem.title`) wird nur fürs **fokussierte/zentrierte**
Item gezeigt — nicht dauerhaft auf allen Kacheln.

**Empfohlener Ansatz — Compositing serverseitig in vault-api (nicht in der Extension):**
1. Backend greift zusätzlich zum Backdrop das `Logo`-Bild des Items ab
   (`ImageTags.Logo` in Jellyfin; bei Episoden das Serien-Logo).
2. vault-api rechnet Backdrop + Logo zu einem Hero-Bild zusammen (z. B. Pillow,
   Logo unten-links, dezenter Scrim für Lesbarkeit) und **cached** das Ergebnis.
3. Neues Feld `hero_url` im Item-DTO; die Top-Shelf-Extension setzt einfach diese
   eine URL via `setImageURL`.
4. **Fallback:** Kein Logo vorhanden → normales Backdrop (aktuelles Verhalten).

**Warum nicht clientseitig komponieren:** Top-Shelf-Extensions haben ein sehr
knappes Speicherlimit. 10× Backdrop+Logo laden und zeichnen kann die Extension
sprengen → Risiko, dass die Top Shelf wieder ganz leer bleibt.

**Abhängigkeit/Risiko:**
- Items brauchen überhaupt `Logo`-Bilder in Jellyfin (Metadaten-Agent / clearLogo).
- Compositing + Cache-Invalidierung sind echtes Backend-Feature (nicht nur App).

**Alternative, falls Hero-mit-Titel zu aufwändig:** Wechsel auf
`TVTopShelfSectionedContent` (Poster-Reihen). Hochkant-Poster tragen den Titel
im Artwork + festes Label unter jeder Kachel — aber kein Hero/Trailer mehr
(siehe §12, Stil-Entscheidung).

*Stand:* Aktuell umgesetzt = Hero-Backdrop + Trailer-Autoplay (`previewVideoURL`)
+ Titel/Genre/Summary fürs fokussierte Item. Diese Idee ist die nächste
Ausbaustufe fürs Hero-Bild.
