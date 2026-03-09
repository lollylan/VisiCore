# SOP: Impflogik

## Ziel
Deterministische Geschaeftslogik fuer Impfplanung, Einverstaendnis und Wiederholung.

## Standard-Impfungen

| Name | Intervall |
|------|-----------|
| Grippe (Influenza) | 1 Jahr |
| Corona (COVID-19) | 1 Jahr |

Alle anderen Impfungen werden als Freitext eingegeben.

## Einverstaendnis-Status (5 Stufen)

| Status | Logik |
|--------|-------|
| `NICHT_ANGEFRAGT` | Default. Impfung sichtbar, keine Aktion. |
| `JA` | Einmaliges Einverstaendnis erteilt. |
| `NEIN` | Abgelehnt. Impfung bleibt sichtbar, wird NICHT geplant. |
| `JA_JAEHRLICH` | Dauerhaftes Einverstaendnis. Gilt automatisch jedes Jahr. |
| `JA_JAEHRLICH_NACHFRAGEN` | Muss jedes Jahr neu eingeholt werden. |

## Jahres-Check (fuer `JA_JAEHRLICH_NACHFRAGEN`)

```
aktuelles_jahr = datetime.now().year
wenn einverstaendnis_status == 'JA_JAEHRLICH_NACHFRAGEN':
    wenn einverstaendnis_jahr == aktuelles_jahr:
        -> Einverstaendnis LIEGT VOR fuer dieses Jahr
    sonst:
        -> Einverstaendnis MUSS NEU EINGEHOLT werden
```

## Impfstatus-Uebergaenge

```
OFFEN -> GEPLANT (plan_datum setzen)
GEPLANT -> DURCHGEFUEHRT (durchfuehrung_datum setzen)
GEPLANT -> OFFEN (plan_datum entfernen / zuruecksetzen)
DURCHGEFUEHRT -> (naechste_faelligkeit berechnen)
```

## Wiederholungslogik

Nach Durchfuehrung:
1. `durchfuehrung_datum` wird gesetzt
2. `wiederholung_intervall_jahre` wird gesetzt (z.B. 1, 5, 10)
3. `naechste_faelligkeit` = durchfuehrung_datum + intervall_jahre
4. Status wird auf `DURCHGEFUEHRT` gesetzt

Cron-artige Pruefung (bei jedem Seitenaufruf):
```
wenn status == 'DURCHGEFUEHRT' UND naechste_faelligkeit <= heute:
    -> Neue Impfung als OFFEN anlegen (oder Status zuruecksetzen)
```

## Anzeige-Logik

Pro Bewohner werden alle Impfungen als Zeilen angezeigt:
- Name der Impfung
- Einverstaendnis-Status (farbcodiert)
- Jahres-Check (bei JA_JAEHRLICH_NACHFRAGEN)
- Plan-Datum / Durchfuehrungsdatum
- Status (farbcodiert: OFFEN=gelb, GEPLANT=blau, DURCHGEFUEHRT=gruen)
