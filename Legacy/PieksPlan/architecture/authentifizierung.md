# SOP: Authentifizierung

## Ziel
Passwortgeschuetzter Zugang mit zwei Benutzerrollen.

## Rollen

| Rolle | Rechte |
|-------|--------|
| `admin` | Alles + Nutzerverwaltung |
| `nutzer` | Daten sehen und bearbeiten, NICHT Nutzer verwalten |

## Login-Flow

1. Benutzer oeffnet App im Browser
2. Nicht eingeloggt -> Weiterleitung zu `/login`
3. Benutzername + Passwort eingeben
4. Bcrypt-Hash vergleichen
5. Bei Erfolg: Session erstellen via Flask-Login
6. Bei Fehlschlag: Fehlermeldung anzeigen

## Passwort-Hashing

- Algorithmus: bcrypt (via Flask-Bcrypt)
- Automatischer Salt bei jedem Hash
- Passwort wird NIEMALS im Klartext gespeichert

## Session-Management

- Flask-Login verwaltet Sessions
- Session-Cookie ist signiert (SECRET_KEY aus .env)
- Session laeuft nach Inaktivitaet ab

## Erster Start

- Beim ersten Start wird ein Admin-Konto erstellt
- Credentials aus `.env` (ADMIN_USERNAME, ADMIN_PASSWORD)
- Admin sollte Passwort nach erstem Login aendern

## CSRF-Schutz

- Flask-WTF schuetzt alle POST-Formulare
- Hidden CSRF-Token in jedem Formular

## Endpunkte

| Route | Methode | Beschreibung |
|-------|---------|-------------|
| `/login` | GET/POST | Login-Formular |
| `/logout` | GET | Abmelden |
| `/admin/nutzer` | GET | Nutzerliste (nur Admin) |
| `/admin/nutzer/neu` | GET/POST | Nutzer anlegen (nur Admin) |
| `/admin/nutzer/<id>/loeschen` | POST | Nutzer loeschen (nur Admin) |
