# SOP: Datenbank-Architektur

## Ziel
Verschluesselte SQLite-Datenbank mit SQLCipher fuer die Speicherung aller PieksPlan-Daten.

## Technologie
- SQLite via `sqlcipher3-wheels`
- AES-256 Verschluesselung (PRAGMA key)
- Passwort aus `.env` (DB_ENCRYPTION_KEY)

## Schema-Version
Aktuelle Version: **1**

## Tabellen-Erstellung (Reihenfolge beachten!)

1. `users` - Benutzerkonten
2. `pflegeheime` - Pflegeheime
3. `wohngruppen` - Wohngruppen (FK: pflegeheime)
4. `bewohner` - Bewohner (FK: wohngruppen)
5. `impfungen` - Impfungen (FK: bewohner)

## Verbindungsmanagement

- Pro Request eine DB-Verbindung (`g.db`)
- Verbindung wird am Ende des Requests geschlossen
- PRAGMA key wird bei JEDER neuen Verbindung gesetzt

## Migrations-Strategie

- Schema-Version in `PRAGMA user_version` gespeichert
- Bei App-Start: Schema-Version pruefen, ggf. Migration ausfuehren
- Migrationen sind idempotent (IF NOT EXISTS)

## Backup

- Verschluesselter Export: Datei kopieren (DB ist bereits verschluesselt)
- Pfad: Benutzer waehlt Download-Ort via Browser

## Sicherheit

- DB-Passwort NIEMALS im Code hartcodiert
- DB-Datei liegt in `data/` (gitignored)
- Parameterisierte Queries IMMER verwenden (kein String-Formatting!)
