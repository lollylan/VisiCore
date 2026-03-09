# VisiCore

**Webbasierte Plattform zur Verwaltung von Hausbesuchen und Impfungen in Arztpraxen.**

VisiCore vereint zwei integrierte Systeme: **Visicycle** (Besuchsplanung) und **PieksPlan** (Impfverwaltung) in einer modernen, dunklen Benutzeroberfläche.

---

## Features

### Patientenverwaltung
- Aktive und inaktive Patienten verwalten
- Standortbasierte Besuchsplanung (Zuhause / Einrichtung)
- Besuchsintervalle und letzte Besuche tracken
- Geocoding von Patientenadressen
- Hinweise und Warnungen (CAVE-Feld)
- Behandler-Zuordnung

### Impfverwaltung (PieksPlan)
- Mehrere Impftypen pro Patient
- Einwilligungs-Tracking (nicht angefragt, ja, nein, jaehrliche Nachfrage)
- Impfstatus (offen, geplant, abgeschlossen)
- Automatische Terminplanung mit konfigurierbaren Intervallen
- Reset-Monate fuer saisonale Impfungen

### Einrichtungen & Stationen
- Einrichtungen mit Stationen/Wohnbereichen verwalten
- Standard-Behandler pro Einrichtung/Station
- Besuchsintervalle pro Station

### Tourenplanung
- Haversine-Distanzberechnung
- Transportmodus (Auto, Fahrrad, zu Fuss)
- Reisezeitschaetzung mit Umwegen und Puffern
- Behandler-Auslastungsoptimierung

### PDF-Exporte
- Einrichtungsuebersichten
- Tagesplaene
- Erweiterte Stationsberichte mit Patientendetails

### Admin
- Nutzerverwaltung (Admin/User-Rollen)
- Aktivitaets-Protokoll (Audit-Log)
- Datenbank-Backup & Restore
- Einstellungen

---

## Tech-Stack

| Bereich | Technologie |
|---------|-------------|
| Backend | Python 3, Flask |
| Datenbank | SQLCipher (verschluesselte SQLite) |
| Auth | Flask-Login, Flask-Bcrypt |
| PDF | ReportLab |
| Geocoding | Geopy |
| Server | Waitress (WSGI) |
| Frontend | Jinja2, HTML5, CSS3 (Dark Theme) |

---

## Installation

### Voraussetzungen
- Python 3.8+

### Setup

```bash
# Repository klonen
git clone https://github.com/lollylan/VisiCore.git
cd VisiCore

# Virtuelle Umgebung erstellen und aktivieren
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS

# Abhaengigkeiten installieren
pip install -r requirements.txt
```

### Konfiguration

Eine `.env`-Datei im Projektverzeichnis erstellen:

```env
DB_KEY=<sicherer-verschluesselungsschluessel>
SECRET_KEY=<zufaelliger-secret-key>
PRAXIS_STADT=Wuerzburg
PORT=5001
```

---

## Starten

**Windows (empfohlen):**
```bash
start.bat
```

**Direkt mit Python:**
```bash
python app.py
```

Die Anwendung ist dann unter `http://localhost:5001` erreichbar.

### Standard-Zugangsdaten

| Benutzer | Passwort |
|----------|----------|
| `admin` | `admin` |

> **Wichtig:** Zugangsdaten nach dem ersten Login aendern!

---

## Projektstruktur

```
VisiCore/
├── app.py              # Flask-Hauptanwendung
├── database.py         # Datenbankschicht & Schema
├── export.py           # PDF-Export
├── routing.py          # Tourenoptimierung
├── requirements.txt    # Python-Abhaengigkeiten
├── start.bat           # Windows-Startskript
├── data/               # Verschluesselte Datenbank
├── static/css/         # Dark-Theme Styling
└── templates/          # Jinja2-Templates
    ├── patienten/      # Patientenseiten
    ├── einrichtungen/  # Einrichtungsseiten
    ├── stationen/      # Stationsseiten
    ├── impfungen/      # Impfformulare
    ├── behandler/      # Behandlerseiten
    └── admin/          # Adminseiten
```

---

## Sicherheit

- Verschluesselte Datenbank (SQLCipher)
- Passwort-Hashing (Bcrypt)
- CSRF-Schutz
- Rollenbasierte Zugriffskontrolle
- Vollstaendiges Audit-Log

---

## Lizenz

Dieses Projekt ist proprietaer. Alle Rechte vorbehalten.
