# Kiosk-Dashboard

Touch-Schaltzentrale auf einem **Raspberry Pi 5 mit 8″-Touchscreen**: steuert
Medien (Roon, Vault am Apple TV), spielt Podcasts und bedient Home Assistant
(Licht, Heizung, Kaffeemaschine).

Ein **zweiter dünner Client** an derselben `vault-api` wie die Apple-TV-App —
der Kiosk *steuert*, er *rendert nicht*. Er kennt nur vault-api-URL +
Gerätetoken; alle fremden Keys bleiben im Backend.

- **[docs/architecture.md](docs/architecture.md)** — Architekturplan, getroffene
  Entscheidungen, Milestones K1–K5. (Schritt 1)
- **[mockup/](mockup/)** — Design-Mockups der Screens als HTML, am Handy
  reviewbar. (Schritt 2, folgt)

Gehört zum selben Projekt wie [`../Vault/`](../Vault/) (tvOS-App) und
[`../vault-api/`](../vault-api/) (Backend); Gesamt-Zielbild in
[`../Vault/docs/architecture-api-first.md`](../Vault/docs/architecture-api-first.md).
