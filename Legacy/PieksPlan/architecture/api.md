# SOP: API-Routen

## Ziel
Alle HTTP-Endpunkte des PieksPlan-Systems.

## Authentifizierung

| Route | Methode | Auth | Beschreibung |
|-------|---------|------|-------------|
| `/login` | GET/POST | Nein | Login-Formular |
| `/logout` | GET | Ja | Abmelden |

## Dashboard

| Route | Methode | Auth | Beschreibung |
|-------|---------|------|-------------|
| `/` | GET | Ja | Dashboard / Uebersicht |

## Pflegeheime

| Route | Methode | Auth | Beschreibung |
|-------|---------|------|-------------|
| `/pflegeheime` | GET | Ja | Liste aller Pflegeheime |
| `/pflegeheime/neu` | GET/POST | Ja | Neues Pflegeheim anlegen |
| `/pflegeheime/<id>` | GET | Ja | Pflegeheim-Detail (Wohngruppen) |
| `/pflegeheime/<id>/bearbeiten` | GET/POST | Ja | Pflegeheim bearbeiten |
| `/pflegeheime/<id>/loeschen` | POST | Ja | Pflegeheim loeschen |

## Wohngruppen

| Route | Methode | Auth | Beschreibung |
|-------|---------|------|-------------|
| `/pflegeheime/<ph_id>/wohngruppen/neu` | GET/POST | Ja | Neue Wohngruppe |
| `/wohngruppen/<id>` | GET | Ja | Wohngruppe-Detail (Bewohner) |
| `/wohngruppen/<id>/bearbeiten` | GET/POST | Ja | Wohngruppe bearbeiten |
| `/wohngruppen/<id>/loeschen` | POST | Ja | Wohngruppe loeschen |

## Bewohner

| Route | Methode | Auth | Beschreibung |
|-------|---------|------|-------------|
| `/wohngruppen/<wg_id>/bewohner/neu` | GET/POST | Ja | Neuer Bewohner |
| `/bewohner/<id>` | GET | Ja | Bewohner-Detail (Impfungen) |
| `/bewohner/<id>/bearbeiten` | GET/POST | Ja | Bewohner bearbeiten |
| `/bewohner/<id>/deaktivieren` | POST | Ja | Bewohner deaktivieren |
| `/bewohner/<id>/aktivieren` | POST | Ja | Bewohner reaktivieren |
| `/bewohner/<id>/loeschen` | POST | Ja | Bewohner endgueltig loeschen |
| `/bewohner/<id>/umziehen` | POST | Ja | Wohngruppe wechseln |
| `/bewohner/inaktive` | GET | Ja | Liste inaktiver Bewohner |

## Impfungen

| Route | Methode | Auth | Beschreibung |
|-------|---------|------|-------------|
| `/bewohner/<b_id>/impfung/neu` | GET/POST | Ja | Neue Impfung |
| `/impfung/<id>/bearbeiten` | GET/POST | Ja | Impfung bearbeiten |
| `/impfung/<id>/loeschen` | POST | Ja | Impfung loeschen |
| `/impfung/<id>/status` | POST | Ja | Status aendern (AJAX) |

## Export

| Route | Methode | Auth | Beschreibung |
|-------|---------|------|-------------|
| `/export/pdf/<ph_id>` | GET | Ja | PDF-Export pro Pflegeheim |
| `/export/txt/<ph_id>` | GET | Ja | TXT-Export pro Pflegeheim |

## Admin

| Route | Methode | Auth | Beschreibung |
|-------|---------|------|-------------|
| `/admin/nutzer` | GET | Admin | Nutzerliste |
| `/admin/nutzer/neu` | GET/POST | Admin | Nutzer anlegen |
| `/admin/nutzer/<id>/loeschen` | POST | Admin | Nutzer loeschen |
| `/admin/backup` | GET | Admin | DB-Backup Download |
