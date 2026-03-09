# SOP: Export

## Ziel
Daten als PDF oder TXT exportieren, damit sie ins Pflegeheim mitgenommen werden koennen.

## PDF-Export (ReportLab)

### Struktur pro Pflegeheim:
1. Titel: "Impfplan - [Pflegeheim-Name]"
2. Export-Datum
3. Pro Wohngruppe:
   a. Ueberschrift: Wohngruppe-Name
   b. Pro Bewohner:
      - Name (Nachname, Vorname)
      - Geburtsdatum (falls vorhanden)
      - Tabelle mit Impfungen:
        | Impfung | Einverstaendnis | Status | Geplant | Checkbox |
      - Checkbox: Leeres Kaestchen zum handschriftlichen Abhaken

### Layout:
- A4 Hochformat
- Kopfzeile: PieksPlan + Pflegeheim
- Tabellenformat mit Zebra-Streifen
- Seitenumbruch pro Wohngruppe (wenn noetig)

## TXT-Export

### Struktur:
```
========================================
IMPFPLAN - [Pflegeheim-Name]
Export: [Datum]
========================================

--- Wohngruppe: [Name] ---

Nachname, Vorname (Geb: DD.MM.YYYY)
  [ ] Grippe - Einverstaendnis: JA_JAEHRLICH - Status: GEPLANT (15.10.2026)
  [ ] Corona - Einverstaendnis: JA_JAEHRLICH - Status: OFFEN
  [ ] Tetanus - Einverstaendnis: JA - Status: DURCHGEFUEHRT (01.03.2026)

Nachname2, Vorname2
  ...
```

## Datenbank-Backup

- Route: `/admin/backup`
- Nur Admin-Zugang
- Kopiert die verschluesselte DB-Datei
- Download als `pieksplan_backup_YYYY-MM-DD.db`
- Die Datei ist bereits verschluesselt (SQLCipher)

## Endpunkte

| Route | Methode | Beschreibung |
|-------|---------|-------------|
| `/export/pdf/<pflegeheim_id>` | GET | PDF-Export |
| `/export/txt/<pflegeheim_id>` | GET | TXT-Export |
| `/admin/backup` | GET | DB-Backup Download |
