# VisiCore

**Webbasierte Plattform zur Verwaltung von Hausbesuchen und Impfungen in Arztpraxen.**

VisiCore vereint zwei integrierte Systeme: **Visicycle** (Besuchsplanung) und **PieksPlan** (Impfverwaltung) in einer modernen, dunklen Benutzeroberflaeche.

---

## Schnellstart (fuer Anwender)

1. **[VisiCore.exe herunterladen](https://github.com/lollylan/VisiCore/releases/latest)**
2. In einen eigenen Ordner verschieben, z.B. `C:\VisiCore\`
3. **Doppelklick** auf `VisiCore.exe` – fertig!

Beim ersten Start wird alles automatisch eingerichtet (Datenbank, Zertifikat, Konfiguration).
Login: `admin` / `admin` (Passwortwechsel wird erzwungen).

> Windows zeigt moeglicherweise eine SmartScreen-Warnung. Auf **"Trotzdem ausfuehren"** klicken.

---

## Features

### Patientenverwaltung
- Aktive und inaktive Patienten verwalten
- Standortbasierte Besuchsplanung (Zuhause / Einrichtung)
- Besuchsintervalle und letzte Besuche tracken
- Geocoding von Patientenadressen
- Hinweise und Warnungen (CAVE-Feld)
- Behandler-Zuordnung
- Sortierbare Spalten in der Patientenliste
- Farbliche Markierung: rot = ueberfaellig, orange = heute faellig

### Impfverwaltung (PieksPlan)
- Impfungen-Uebersichtsseite mit Filter (alle/offen/erledigt) und Sortierung
- Mehrere Impftypen pro Patient
- Einwilligungs-Tracking (nicht angefragt, ja, nein, jaehrliche Nachfrage)
- Impfstatus (offen, geplant, abgeschlossen)
- Automatische Terminplanung mit konfigurierbaren Intervallen
- Reset-Monate fuer saisonale Impfungen
- Automatischer Status-Wechsel bei Eintragen des Durchfuehrungsdatums

### Kalenderansicht
- 4-Wochen-Uebersicht aller geplanten Besuche
- Tagesplanung mit Behandler-Zuordnung
- PDF-Export fuer verschiedene Zeitraeume (Heute, Morgen, 7/14 Tage, Monat)

### Snooze-Funktion
- Patienten und Stationen temporaer zurueckstellen (1d, 3d, 7d, 14d, 30d oder individuell)
- Direkt aus dem Tagesplan steuerbar
- Gesnoozete Eintraege werden aus Tagesplan und Dashboard ausgeblendet

### Konfigurierbarer PDF-Export
- Frei waehlbare Spalten (Name, Geburtsdatum, Einrichtung, Adresse, Behandler, etc.)
- Filter nach Einrichtung, Station, Wohnort-Typ, Behandler oder faellige Patienten
- Impfstatus-Uebersicht im Export

### Einrichtungen & Stationen
- Einrichtungen mit Stationen/Wohnbereichen verwalten
- Standard-Behandler pro Einrichtung/Station
- Besuchsintervalle pro Station

### Tourenplanung
- Haversine-Distanzberechnung
- Transportmodus (Auto, Fahrrad, zu Fuss)
- Reisezeitschaetzung mit Umwegen und Puffern
- Behandler-Auslastungsoptimierung

### Dashboard
- Klickbare Statistik-Kacheln mit Direktlinks
- Warnung bei Standard-Admin-Passwort

### Admin
- Nutzerverwaltung (Admin/User-Rollen)
- Passwort-aendern Seite
- Aktivitaets-Protokoll (Audit-Log)
- Datenbank-Backup & Restore
- Einstellungen

---

## Sicherheit

- HTTPS mit automatisch generiertem TLS-Zertifikat
- Verschluesselte Datenbank (SQLCipher)
- Passwort-Hashing (Bcrypt)
- CSRF-Schutz
- Rollenbasierte Zugriffskontrolle
- Security Headers (CSP, HSTS, X-Frame-Options)
- Vollstaendiges Audit-Log

---

## Tech-Stack

| Bereich | Technologie |
|---------|-------------|
| Backend | Python 3, Flask |
| Datenbank | SQLCipher (verschluesselte SQLite) |
| Auth | Flask-Login, Flask-Bcrypt |
| PDF | ReportLab |
| TLS | Cryptography (automatisches Zertifikat) |
| Geocoding | Geopy |
| Server | Werkzeug (HTTPS) |
| Frontend | Jinja2, HTML5, CSS3 (Dark Theme) |

---

## Installation (fuer Entwickler)

### Voraussetzungen
- Python 3.8+

### Setup

```bash
git clone https://github.com/lollylan/VisiCore.git
cd VisiCore
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Konfiguration

Eine `.env`-Datei wird beim ersten Start automatisch erstellt. Alternativ manuell anlegen:

```env
DB_KEY=<sicherer-verschluesselungsschluessel>
SECRET_KEY=<zufaelliger-secret-key>
PRAXIS_STADT=Wuerzburg
PORT=5001
```

### Starten

```bash
python launcher.py
```

Die Anwendung ist dann unter `https://localhost:5001` erreichbar.

---

## Projektstruktur

```
VisiCore/
├── app.py              # Flask-Hauptanwendung
├── database.py         # Datenbankschicht & Schema
├── export.py           # PDF-Export
├── routing.py          # Tourenoptimierung
├── launcher.py         # Standalone-Launcher (EXE-Einstiegspunkt)
├── tls.py              # TLS-Zertifikatsgenerierung
├── requirements.txt    # Python-Abhaengigkeiten
├── data/               # Datenbank & Zertifikate (automatisch erstellt)
├── static/css/         # Dark-Theme Styling
└── templates/          # Jinja2-Templates
```

---

## Lizenz

Dieses Projekt ist proprietaer. Alle Rechte vorbehalten.
