# PieksPlan

PieksPlan ist ein einfach zu bedienendes Impfplanungs-Tool für Pflegeheime. 
Mit diesem Programm können Sie Bewohner, Impfungen und Einverständniserklärungen sicher und DSGVO-konform verwalten. Alle Daten werden dabei lokal auf Ihrem Computer gespeichert und sicher verschlüsselt.

## 🚀 Erste Schritte (Für Anwender)

Sie benötigen **keine** Installation! Das Programm läuft direkt von Ihrem PC:

1. **Herunterladen:** Laden Sie die Datei `PieksPlan.exe` aus dem Bereich "Releases" auf der rechten Seite herunter.
2. **Speicherort wählen:** Legen Sie die Datei in einen eigenen Ordner (z. B. auf Ihrem Desktop), da das Programm dort alle Daten (wie Ihre verschlüsselte Datenbank `data/pieksplan.db`) speichert.
3. **Starten:** Klicken Sie doppelt auf `PieksPlan.exe`. (Falls Windows fragt, ob Sie die App trotzdem ausführen möchten, klicken Sie auf "Weitere Informationen" und dann auf "Trotzdem ausführen").
4. **Im Browser öffnen:** Es öffnet sich ein schwarzes Fenster (bitte geöffnet lassen, solange Sie arbeiten). Öffnen Sie nun Ihren Internetbrowser (z. B. Chrome, Firefox oder Edge) und tippen Sie in die Adresszeile oben ein:
   👉 **http://localhost:5555**

### 🔑 Erste Anmeldung

Beim ersten Start wurden automatisch folgende Zugangsdaten für Sie angelegt:
- **Benutzername:** `admin`
- **Passwort:** `admin`

*(Bitte melden Sie sich damit an und legen idealerweise in den Admin-Einstellungen ein sicheres Kennwort oder persönliche Benutzer-Accounts an.)*

---

## 🔒 Ihre Daten sind sicher (Datenschutz & DSGVO)

- **Lokal:** Die Software verbindet sich nicht mit dem Internet. Alles bleibt bei Ihnen in der Praxis oder im Heim auf dem Rechner.
- **Verschlüsselt:** Die Datenbank und alle hochgeladenen Dokumente (z. B. PDF-Einverständniserklärungen) sind stark verschlüsselt. Startet jemand das Programm ohne Ihr Passwort, kann er die Dokumente nicht einfach aus dem Windows-Ordner auslesen.
- **Datensicherung:** Sie können über das Menü "Admin-Bereich > Backup & Import" jederzeit komplette Sicherungen Ihrer Daten herunterladen und bei Bedarf wiederherstellen. Speichern Sie diese Backups regelmäßig sicher ab!

## ⚙️ Erweiterte Konfiguration (Optional)

Falls Sie Passwörter, Ports oder die Verschlüsselung von Grund auf selbst definieren möchten, können Sie im selben Ordner wie die `PieksPlan.exe` eine einfache Textdatei namens `.env` erstellen.
*(Dies ist für Computerlaien nicht zwingend erforderlich!)*

Beispiel-Inhalt für die `.env` Datei:
```env
SECRET_KEY=ein-sehr-sicherer-schluessel-123
DB_ENCRYPTION_KEY=ein-sicheres-db-passwort-456
PORT=5555
ADMIN_USERNAME=mein_wunsch_admin
ADMIN_PASSWORD=mein_starkes_passwort
```

## 👋 Hilfe und Support

Das Programm wurde so entwickelt, dass Sie intuitiv arbeiten können. Sie starten das Programm immer über die `PieksPlan.exe` und greifen dann über Ihren normalen Webbrowser darauf zu. Wenn Sie das schwarze Fenster schließen, ist das Programm beendet!
