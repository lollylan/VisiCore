"""
VisiCore - Datenbank-Layer
Verschluesselte SQLite-Datenbank mit SQLCipher.
Vereint PieksPlan (Impfungen) und Visicycle (Visitenplanung).
"""

import os
import json
from datetime import date, datetime, timedelta
import sqlcipher3
from flask import g, current_app


# ============================================================
# Verbindungsmanagement
# ============================================================

def get_db():
    """Gibt die DB-Verbindung fuer den aktuellen Request zurueck."""
    if 'db' not in g:
        db_path = current_app.config.get('DB_PATH', 'data/visicore.db')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        g.db = sqlcipher3.connect(db_path)
        g.db.execute(f"PRAGMA key = '{current_app.config['DB_KEY']}'")
        g.db.row_factory = sqlcipher3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    """Schliesst die DB-Verbindung am Ende des Requests."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """Erstellt alle Tabellen falls sie nicht existieren."""
    db = get_db()

    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            benutzername TEXT UNIQUE NOT NULL,
            passwort_hash TEXT NOT NULL,
            rolle TEXT NOT NULL CHECK(rolle IN ('admin', 'nutzer')),
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS behandler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            rolle TEXT,
            farbe TEXT DEFAULT '#33656E',
            max_taegliche_minuten INTEGER DEFAULT 240,
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS einrichtungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            adresse TEXT,
            latitude REAL,
            longitude REAL,
            standard_behandler_id INTEGER REFERENCES behandler(id),
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS stationen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            einrichtung_id INTEGER NOT NULL REFERENCES einrichtungen(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            intervall_tage INTEGER DEFAULT 28,
            letzter_besuch TIMESTAMP,
            standard_behandler_id INTEGER REFERENCES behandler(id),
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS patienten (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nachname TEXT NOT NULL,
            vorname TEXT NOT NULL,
            geburtsdatum DATE,
            wohnort_typ TEXT NOT NULL DEFAULT 'ZUHAUSE'
                CHECK(wohnort_typ IN ('ZUHAUSE', 'HEIM')),
            adresse TEXT,
            latitude REAL,
            longitude REAL,
            station_id INTEGER REFERENCES stationen(id),
            intervall_tage INTEGER,
            letzter_besuch TIMESTAMP,
            besuchsdauer_minuten INTEGER DEFAULT 30,
            geplanter_besuch DATE,
            snooze_bis DATE,
            ist_einmalig BOOLEAN DEFAULT 0,
            primaer_behandler_id INTEGER REFERENCES behandler(id),
            override_behandler_id INTEGER REFERENCES behandler(id),
            cave TEXT,
            notizen TEXT,
            aktiv BOOLEAN DEFAULT 1,
            geocode_status TEXT CHECK(geocode_status IN ('OK', 'FEHLER')),
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS impfungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES patienten(id) ON DELETE CASCADE,
            impftyp TEXT NOT NULL,
            ist_standardimpfung BOOLEAN DEFAULT 0,
            einverstaendnis_status TEXT NOT NULL DEFAULT 'NICHT_ANGEFRAGT'
                CHECK(einverstaendnis_status IN (
                    'NICHT_ANGEFRAGT', 'JA', 'NEIN',
                    'JA_JAEHRLICH', 'JA_JAEHRLICH_NACHFRAGEN',
                    'NEIN_JAEHRLICH_NACHFRAGEN'
                )),
            einverstaendnis_jahr INTEGER,
            plan_datum DATE,
            status TEXT NOT NULL DEFAULT 'OFFEN'
                CHECK(status IN ('OFFEN', 'GEPLANT', 'DURCHGEFUEHRT')),
            durchfuehrung_datum DATE,
            wiederholung_intervall_jahre INTEGER,
            wiederholung_reset_monat INTEGER
                CHECK(wiederholung_reset_monat >= 1 AND wiederholung_reset_monat <= 12),
            naechste_faelligkeit DATE,
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS dokumente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES patienten(id) ON DELETE CASCADE,
            impfung_id INTEGER REFERENCES impfungen(id) ON DELETE CASCADE,
            dateiname TEXT NOT NULL,
            daten BLOB NOT NULL,
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS protokoll (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            zeitpunkt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            benutzer_id INTEGER,
            benutzer_name TEXT NOT NULL,
            aktion TEXT NOT NULL,
            entitaet_typ TEXT NOT NULL,
            entitaet_id INTEGER,
            entitaet_bezeichnung TEXT,
            aenderungen TEXT
        );

        CREATE TABLE IF NOT EXISTS einstellungen (
            schluessel TEXT PRIMARY KEY,
            wert TEXT
        );
    ''')
    
    # Automatische Migration bestehender Datenbanken, falls Feld fehlt
    try:
        db.execute("ALTER TABLE impfungen ADD COLUMN wiederholung_reset_monat INTEGER CHECK(wiederholung_reset_monat >= 1 AND wiederholung_reset_monat <= 12)")
        
        # Bestehende Grippe-Impfungen auf Reset-Monat 9 updaten
        db.execute("UPDATE impfungen SET wiederholung_reset_monat = 9 WHERE impftyp LIKE '%Grippe%' AND wiederholung_reset_monat IS NULL AND wiederholung_intervall_jahre IS NULL")
        
        # Bestehende Corona-Impfungen auf Intervall 1 Jahr updaten
        db.execute("UPDATE impfungen SET wiederholung_intervall_jahre = 1 WHERE impftyp LIKE '%Corona%' AND wiederholung_intervall_jahre IS NULL AND wiederholung_reset_monat IS NULL")
    except sqlcipher3.OperationalError:
        pass # Spalte existiert bereits

    # Migration: geocode_status Feld für Patienten
    try:
        db.execute("ALTER TABLE patienten ADD COLUMN geocode_status TEXT CHECK(geocode_status IN ('OK', 'FEHLER'))")
    except sqlcipher3.OperationalError:
        pass  # Spalte existiert bereits

    # Migration: override_behandler_id für Stationen (einmaliger Behandlerwechsel)
    try:
        db.execute("ALTER TABLE stationen ADD COLUMN override_behandler_id INTEGER REFERENCES behandler(id)")
    except sqlcipher3.OperationalError:
        pass  # Spalte existiert bereits

    # Migration: override_kein_behandler – explizite "Ohne Zuordnung"-Markierung
    try:
        db.execute("ALTER TABLE patienten ADD COLUMN override_kein_behandler INTEGER DEFAULT 0")
    except sqlcipher3.OperationalError:
        pass  # Spalte existiert bereits
    try:
        db.execute("ALTER TABLE stationen ADD COLUMN override_kein_behandler INTEGER DEFAULT 0")
    except sqlcipher3.OperationalError:
        pass  # Spalte existiert bereits

    # Migration: 'ANGEFRAGT' zu einverstaendnis_status CHECK-Constraint hinzufügen
    schema_row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='impfungen'"
    ).fetchone()
    if schema_row and "'ANGEFRAGT'" not in schema_row[0]:
        db.execute("PRAGMA foreign_keys = OFF")
        db.execute("""
            CREATE TABLE impfungen_migr (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL REFERENCES patienten(id) ON DELETE CASCADE,
                impftyp TEXT NOT NULL,
                ist_standardimpfung BOOLEAN DEFAULT 0,
                einverstaendnis_status TEXT NOT NULL DEFAULT 'NICHT_ANGEFRAGT'
                    CHECK(einverstaendnis_status IN (
                        'NICHT_ANGEFRAGT', 'ANGEFRAGT', 'JA', 'NEIN',
                        'JA_JAEHRLICH', 'JA_JAEHRLICH_NACHFRAGEN',
                        'NEIN_JAEHRLICH_NACHFRAGEN'
                    )),
                einverstaendnis_jahr INTEGER,
                plan_datum DATE,
                status TEXT NOT NULL DEFAULT 'OFFEN'
                    CHECK(status IN ('OFFEN', 'GEPLANT', 'DURCHGEFUEHRT')),
                durchfuehrung_datum DATE,
                wiederholung_intervall_jahre INTEGER,
                wiederholung_reset_monat INTEGER
                    CHECK(wiederholung_reset_monat >= 1 AND wiederholung_reset_monat <= 12),
                naechste_faelligkeit DATE,
                erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("INSERT INTO impfungen_migr SELECT * FROM impfungen")
        db.execute("DROP TABLE impfungen")
        db.execute("ALTER TABLE impfungen_migr RENAME TO impfungen")
        db.execute("UPDATE sqlite_sequence SET name='impfungen' WHERE name='impfungen_migr'")
        db.execute("PRAGMA foreign_keys = ON")

    db.commit()


def init_app(app):
    """Registriert DB-Funktionen bei der Flask-App."""
    app.teardown_appcontext(close_db)


# ============================================================
# Faelligkeits-Check (Grippe, Corona, Wiederholungen)
# ============================================================

def faelligkeits_check():
    """
    Prueft ob Impfungen wieder faellig sind.
    Logik:
    1. Reset-Monat: Wird am 1. des definierten Monats (z.B. Sept) jeden Jahres wieder OFFEN
    2. Intervall: Wird anhand der naechsten_faelligkeit wieder OFFEN
    3. NACHFRAGEN-Status: Einverstaendnis zuruecksetzen (fuer alle abgelaufenen oder reset-monat)
    """
    db = get_db()
    heute = date.today()
    aktuelles_jahr = heute.year

    # 1. Reset-Monat-Logik (z.B. Grippe im September)
    for reset_monat in range(1, 13):
        saison_start = date(aktuelles_jahr, reset_monat, 1)
        saison_aktiv = heute >= saison_start
        saison_jahr = aktuelles_jahr if saison_aktiv else aktuelles_jahr - 1

        if saison_aktiv:
            reset_faellig = db.execute(
                "SELECT id FROM impfungen "
                "WHERE wiederholung_reset_monat = ? "
                "AND status = 'DURCHGEFUEHRT' "
                "AND durchfuehrung_datum < ? "
                "AND einverstaendnis_status != 'NEIN'",
                (reset_monat, saison_start.isoformat())
            ).fetchall()
            
            for imp in reset_faellig:
                db.execute(
                    "UPDATE impfungen SET status = 'OFFEN', "
                    "plan_datum = NULL, durchfuehrung_datum = NULL, "
                    "naechste_faelligkeit = NULL "
                    "WHERE id = ?", (imp['id'],)
                )
        
        # NACHFRAGEN-Status zuruecksetzen fuer diese Saison
        if saison_aktiv:
            db.execute(
                "UPDATE impfungen SET "
                "einverstaendnis_status = 'NICHT_ANGEFRAGT', "
                "einverstaendnis_jahr = NULL "
                "WHERE wiederholung_reset_monat = ? "
                "AND einverstaendnis_status IN "
                "('JA_JAEHRLICH_NACHFRAGEN', 'NEIN_JAEHRLICH_NACHFRAGEN') "
                "AND (einverstaendnis_jahr IS NULL OR einverstaendnis_jahr < ?)",
                (reset_monat, saison_jahr)
            )

    # 2. Reguläre Intervall-Logik (z.B. Corona 1 Jahr, Tetanus 10 Jahre)
    intervall_faellig = db.execute(
        "SELECT id FROM impfungen "
        "WHERE wiederholung_intervall_jahre IS NOT NULL "
        "AND status = 'DURCHGEFUEHRT' "
        "AND naechste_faelligkeit IS NOT NULL "
        "AND naechste_faelligkeit <= ? "
        "AND einverstaendnis_status != 'NEIN'",
        (heute.isoformat(),)
    ).fetchall()
    
    for imp in intervall_faellig:
        db.execute(
            "UPDATE impfungen SET status = 'OFFEN', "
            "plan_datum = NULL, durchfuehrung_datum = NULL, "
            "naechste_faelligkeit = NULL "
            "WHERE id = ?", (imp['id'],)
        )

    # NACHFRAGEN-Status zuruecksetzen fuer Intervall/Einmalige Impfungen
    db.execute(
        "UPDATE impfungen SET "
        "einverstaendnis_status = 'NICHT_ANGEFRAGT', "
        "einverstaendnis_jahr = NULL "
        "WHERE (wiederholung_reset_monat IS NULL) "
        "AND einverstaendnis_status IN "
        "('JA_JAEHRLICH_NACHFRAGEN', 'NEIN_JAEHRLICH_NACHFRAGEN') "
        "AND (einverstaendnis_jahr IS NULL OR einverstaendnis_jahr < ?)",
        (aktuelles_jahr,)
    )
    
    db.commit()


# ============================================================
# CRUD: Benutzer
# ============================================================

def get_user_by_id(user_id):
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_name(benutzername):
    db = get_db()
    return db.execute(
        "SELECT * FROM users WHERE benutzername = ?", (benutzername,)
    ).fetchone()


def get_all_users():
    db = get_db()
    return db.execute("SELECT id, benutzername, rolle, erstellt_am FROM users").fetchall()


def create_user(benutzername, passwort_hash, rolle='nutzer'):
    db = get_db()
    db.execute(
        "INSERT INTO users (benutzername, passwort_hash, rolle) VALUES (?, ?, ?)",
        (benutzername, passwort_hash, rolle)
    )
    db.commit()


def delete_user(user_id):
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()


# ============================================================
# CRUD: Behandler
# ============================================================

def get_alle_behandler():
    db = get_db()
    return db.execute("SELECT * FROM behandler ORDER BY name").fetchall()


def get_behandler(behandler_id):
    db = get_db()
    return db.execute("SELECT * FROM behandler WHERE id = ?", (behandler_id,)).fetchone()


def create_behandler(name, rolle='', farbe='#33656E', max_taegliche_minuten=240):
    db = get_db()
    db.execute(
        "INSERT INTO behandler (name, rolle, farbe, max_taegliche_minuten) "
        "VALUES (?, ?, ?, ?)",
        (name, rolle, farbe, max_taegliche_minuten)
    )
    db.commit()
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_behandler(behandler_id, name, rolle='', farbe='#33656E', max_taegliche_minuten=240):
    db = get_db()
    db.execute(
        "UPDATE behandler SET name=?, rolle=?, farbe=?, max_taegliche_minuten=? "
        "WHERE id=?",
        (name, rolle, farbe, max_taegliche_minuten, behandler_id)
    )
    db.commit()


def delete_behandler(behandler_id):
    db = get_db()
    # Referenzen bei Patienten loesen
    db.execute(
        "UPDATE patienten SET primaer_behandler_id = NULL "
        "WHERE primaer_behandler_id = ?", (behandler_id,)
    )
    db.execute(
        "UPDATE patienten SET override_behandler_id = NULL "
        "WHERE override_behandler_id = ?", (behandler_id,)
    )
    db.execute("DELETE FROM behandler WHERE id = ?", (behandler_id,))
    db.commit()


# ============================================================
# CRUD: Einrichtungen
# ============================================================

def get_einrichtungen():
    db = get_db()
    return db.execute("SELECT * FROM einrichtungen ORDER BY name").fetchall()


def get_einrichtung(einrichtung_id):
    db = get_db()
    return db.execute(
        "SELECT e.*, b.name AS standard_behandler_name, b.farbe AS standard_behandler_farbe "
        "FROM einrichtungen e "
        "LEFT JOIN behandler b ON e.standard_behandler_id = b.id "
        "WHERE e.id = ?", (einrichtung_id,)
    ).fetchone()


def create_einrichtung(name, adresse='', latitude=None, longitude=None, standard_behandler_id=None):
    db = get_db()
    db.execute(
        "INSERT INTO einrichtungen (name, adresse, latitude, longitude, standard_behandler_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, adresse, latitude, longitude, standard_behandler_id)
    )
    db.commit()
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_einrichtung(einrichtung_id, name, adresse='', latitude=None, longitude=None, standard_behandler_id=None):
    db = get_db()
    db.execute(
        "UPDATE einrichtungen SET name=?, adresse=?, latitude=?, longitude=?, standard_behandler_id=? "
        "WHERE id=?",
        (name, adresse, latitude, longitude, standard_behandler_id, einrichtung_id)
    )
    db.commit()


def delete_einrichtung(einrichtung_id):
    db = get_db()
    db.execute("DELETE FROM einrichtungen WHERE id = ?", (einrichtung_id,))
    db.commit()


# ============================================================
# CRUD: Stationen
# ============================================================

def get_stationen(einrichtung_id):
    db = get_db()
    return db.execute(
        "SELECT s.*, e.name as einrichtung_name "
        "FROM stationen s JOIN einrichtungen e ON s.einrichtung_id = e.id "
        "WHERE s.einrichtung_id = ? ORDER BY s.name",
        (einrichtung_id,)
    ).fetchall()


def get_station(station_id):
    db = get_db()
    return db.execute(
        "SELECT s.*, e.name as einrichtung_name, e.id as einrichtung_id_ref, "
        "COALESCE(s.standard_behandler_id, e.standard_behandler_id) as resolved_behandler_id, "
        "b.name as behandler_name, b.farbe as behandler_farbe "
        "FROM stationen s "
        "JOIN einrichtungen e ON s.einrichtung_id = e.id "
        "LEFT JOIN behandler b ON b.id = COALESCE(s.standard_behandler_id, e.standard_behandler_id) "
        "WHERE s.id = ?", (station_id,)
    ).fetchone()


def get_alle_stationen():
    """Alle Stationen mit Einrichtungsname (fuer Dropdowns)."""
    db = get_db()
    return db.execute(
        "SELECT s.*, e.name as einrichtung_name "
        "FROM stationen s JOIN einrichtungen e ON s.einrichtung_id = e.id "
        "ORDER BY e.name, s.name"
    ).fetchall()


def create_station(einrichtung_id, name, intervall_tage=28, standard_behandler_id=None, letzter_besuch=None):
    db = get_db()
    db.execute(
        "INSERT INTO stationen (einrichtung_id, name, intervall_tage, standard_behandler_id, letzter_besuch) "
        "VALUES (?, ?, ?, ?, ?)",
        (einrichtung_id, name, intervall_tage, standard_behandler_id, letzter_besuch)
    )
    db.commit()
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_station(station_id, name, intervall_tage=28, standard_behandler_id=None, letzter_besuch=None):
    db = get_db()
    db.execute(
        "UPDATE stationen SET name=?, intervall_tage=?, standard_behandler_id=?, letzter_besuch=? WHERE id=?",
        (name, intervall_tage, standard_behandler_id, letzter_besuch, station_id)
    )
    db.commit()


def delete_station(station_id):
    db = get_db()
    db.execute("DELETE FROM stationen WHERE id = ?", (station_id,))
    db.commit()


def update_station_behandler(station_id, behandler_id, dauerhaft=False):
    """Aendert den Behandler einer Station – einmalig (override) oder dauerhaft (standard)."""
    db = get_db()
    if dauerhaft:
        db.execute(
            "UPDATE stationen SET standard_behandler_id = ?, override_behandler_id = NULL, override_kein_behandler = 0 WHERE id = ?",
            (behandler_id, station_id)
        )
    elif behandler_id is None:
        # Explizit "Ohne Zuordnung" für heute
        db.execute(
            "UPDATE stationen SET override_behandler_id = NULL, override_kein_behandler = 1 WHERE id = ?",
            (station_id,)
        )
    else:
        db.execute(
            "UPDATE stationen SET override_behandler_id = ?, override_kein_behandler = 0 WHERE id = ?",
            (behandler_id, station_id)
        )
    db.commit()


def station_visite_registrieren(station_id):
    """Registriert eine Stationsvisite: Setzt letzter_besuch der Station
    und aller aktiven Patienten der Station zurueck."""
    db = get_db()
    jetzt = datetime.now().isoformat()
    db.execute(
        "UPDATE stationen SET letzter_besuch = ?, override_behandler_id = NULL, override_kein_behandler = 0 WHERE id = ?",
        (jetzt, station_id)
    )
    db.execute(
        "UPDATE patienten SET letzter_besuch = ?, geplanter_besuch = NULL "
        "WHERE station_id = ? AND aktiv = 1",
        (jetzt, station_id)
    )
    db.commit()


# ============================================================
# CRUD: Patienten
# ============================================================

def get_patienten(nur_aktive=True, wohnort_typ=None, station_id=None):
    db = get_db()
    sql = "SELECT p.*, s.name as station_name, e.name as einrichtung_name, "
    sql += "COALESCE(p.intervall_tage, s.intervall_tage) as resolved_intervall_tage, "
    sql += "COALESCE(p.latitude, e.latitude) as resolved_latitude, "
    sql += "COALESCE(p.longitude, e.longitude) as resolved_longitude "
    sql += "FROM patienten p "
    sql += "LEFT JOIN stationen s ON p.station_id = s.id "
    sql += "LEFT JOIN einrichtungen e ON s.einrichtung_id = e.id "
    where = []
    params = []
    if nur_aktive:
        where.append("p.aktiv = 1")
    if wohnort_typ:
        where.append("p.wohnort_typ = ?")
        params.append(wohnort_typ)
    if station_id:
        where.append("p.station_id = ?")
        params.append(station_id)
    if where:
        sql += "WHERE " + " AND ".join(where) + " "
    sql += "ORDER BY p.nachname, p.vorname"
    return db.execute(sql, params).fetchall()


def get_patient(patient_id):
    db = get_db()
    return db.execute(
        "SELECT p.*, s.name as station_name, e.name as einrichtung_name, "
        "e.id as einrichtung_id, e.adresse as einrichtung_adresse, "
        "COALESCE(p.primaer_behandler_id, s.standard_behandler_id, e.standard_behandler_id) as resolved_behandler_id, "
        "COALESCE(p.intervall_tage, s.intervall_tage) as resolved_intervall_tage, "
        "COALESCE(p.latitude, e.latitude) as resolved_latitude, "
        "COALESCE(p.longitude, e.longitude) as resolved_longitude, "
        "b.name as behandler_name, b.farbe as behandler_farbe "
        "FROM patienten p "
        "LEFT JOIN stationen s ON p.station_id = s.id "
        "LEFT JOIN einrichtungen e ON s.einrichtung_id = e.id "
        "LEFT JOIN behandler b ON b.id = COALESCE(p.primaer_behandler_id, s.standard_behandler_id, e.standard_behandler_id) "
        "WHERE p.id = ?", (patient_id,)
    ).fetchone()


def get_patienten_by_station(station_id, nur_aktive=True):
    db = get_db()
    sql = "SELECT * FROM patienten WHERE station_id = ?"
    params = [station_id]
    if nur_aktive:
        sql += " AND aktiv = 1"
    sql += " ORDER BY nachname, vorname"
    return db.execute(sql, params).fetchall()


def get_inaktive_patienten():
    db = get_db()
    return db.execute(
        "SELECT p.*, s.name as station_name, e.name as einrichtung_name "
        "FROM patienten p "
        "LEFT JOIN stationen s ON p.station_id = s.id "
        "LEFT JOIN einrichtungen e ON s.einrichtung_id = e.id "
        "WHERE p.aktiv = 0 ORDER BY p.nachname"
    ).fetchall()


def create_patient(nachname, vorname, wohnort_typ='ZUHAUSE', geburtsdatum=None,
                   adresse=None, latitude=None, longitude=None, station_id=None,
                   intervall_tage=None, besuchsdauer_minuten=30,
                   primaer_behandler_id=None, cave=None, notizen=None,
                   ist_einmalig=False, letzter_besuch=None):
    db = get_db()
    if letzter_besuch is None:
        letzter_besuch = datetime.now().isoformat()
    db.execute(
        "INSERT INTO patienten (nachname, vorname, geburtsdatum, wohnort_typ, "
        "adresse, latitude, longitude, station_id, intervall_tage, "
        "besuchsdauer_minuten, primaer_behandler_id, cave, notizen, "
        "ist_einmalig, letzter_besuch) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (nachname, vorname, geburtsdatum, wohnort_typ,
         adresse, latitude, longitude, station_id, intervall_tage,
         besuchsdauer_minuten, primaer_behandler_id, cave, notizen,
         ist_einmalig, letzter_besuch)
    )
    db.commit()
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_patient(patient_id, **kwargs):
    """Aktualisiert beliebige Felder eines Patienten."""
    db = get_db()
    erlaubte_felder = {
        'nachname', 'vorname', 'geburtsdatum', 'wohnort_typ',
        'adresse', 'latitude', 'longitude', 'station_id',
        'intervall_tage', 'besuchsdauer_minuten',
        'primaer_behandler_id', 'override_behandler_id', 'override_kein_behandler',
        'cave', 'notizen', 'geplanter_besuch', 'snooze_bis',
        'ist_einmalig', 'aktiv', 'letzter_besuch'
    }
    felder = {k: v for k, v in kwargs.items() if k in erlaubte_felder}
    if not felder:
        return
    set_clause = ", ".join(f"{k} = ?" for k in felder)
    values = list(felder.values()) + [patient_id]
    db.execute(f"UPDATE patienten SET {set_clause} WHERE id = ?", values)
    db.commit()


def deaktiviere_patient(patient_id):
    db = get_db()
    db.execute("UPDATE patienten SET aktiv = 0 WHERE id = ?", (patient_id,))
    db.commit()


def aktiviere_patient(patient_id):
    db = get_db()
    db.execute("UPDATE patienten SET aktiv = 1 WHERE id = ?", (patient_id,))
    db.commit()


def delete_patient(patient_id):
    db = get_db()
    db.execute("DELETE FROM patienten WHERE id = ?", (patient_id,))
    db.commit()


def patient_visite_registrieren(patient_id):
    """Registriert eine Einzelvisite: Setzt letzter_besuch zurueck,
    loescht geplanten Besuch und Override-Behandler."""
    db = get_db()
    patient = get_patient(patient_id)
    if not patient:
        return None

    jetzt = datetime.now().isoformat()

    # Bei einmaligen Patienten: Deaktivieren nach Visite
    if patient['ist_einmalig']:
        db.execute(
            "UPDATE patienten SET aktiv = 0, letzter_besuch = ? WHERE id = ?",
            (jetzt, patient_id)
        )
    else:
        db.execute(
            "UPDATE patienten SET letzter_besuch = ?, "
            "geplanter_besuch = NULL, override_behandler_id = NULL, override_kein_behandler = 0 "
            "WHERE id = ?",
            (jetzt, patient_id)
        )
    db.commit()
    return patient


def umziehen_patient(patient_id, neue_station_id):
    """Zieht einen Patienten in eine andere Station um."""
    db = get_db()
    db.execute(
        "UPDATE patienten SET station_id = ? WHERE id = ?",
        (neue_station_id, patient_id)
    )
    db.commit()


# ============================================================
# CRUD: Impfungen
# ============================================================

def get_impfungen(patient_id):
    db = get_db()
    return db.execute(
        "SELECT i.*, (SELECT id FROM dokumente WHERE impfung_id = i.id LIMIT 1) as dokument_id "
        "FROM impfungen i WHERE i.patient_id = ? ORDER BY i.impftyp",
        (patient_id,)
    ).fetchall()


def get_offene_impfungen(patient_id):
    db = get_db()
    return db.execute(
        "SELECT i.*, (SELECT id FROM dokumente WHERE impfung_id = i.id LIMIT 1) as dokument_id "
        "FROM impfungen i WHERE i.patient_id = ? AND i.status IN ('OFFEN', 'GEPLANT') ORDER BY i.impftyp",
        (patient_id,)
    ).fetchall()


def get_impfung(impfung_id):
    db = get_db()
    return db.execute(
        "SELECT i.*, p.nachname, p.vorname "
        "FROM impfungen i JOIN patienten p ON i.patient_id = p.id "
        "WHERE i.id = ?", (impfung_id,)
    ).fetchone()


def create_impfung(patient_id, impftyp, ist_standardimpfung=False,
                   wiederholung_intervall_jahre=None, wiederholung_reset_monat=None):
    db = get_db()
    db.execute(
        "INSERT INTO impfungen (patient_id, impftyp, ist_standardimpfung, "
        "wiederholung_intervall_jahre, wiederholung_reset_monat) VALUES (?, ?, ?, ?, ?)",
        (patient_id, impftyp, ist_standardimpfung, wiederholung_intervall_jahre, wiederholung_reset_monat)
    )
    db.commit()
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_impfung(impfung_id, **kwargs):
    """Aktualisiert beliebige Felder einer Impfung."""
    db = get_db()
    erlaubte_felder = {
        'impftyp', 'ist_standardimpfung', 'einverstaendnis_status',
        'einverstaendnis_jahr', 'plan_datum', 'status',
        'durchfuehrung_datum', 'wiederholung_intervall_jahre',
        'wiederholung_reset_monat', 'naechste_faelligkeit'
    }
    felder = {k: v for k, v in kwargs.items() if k in erlaubte_felder}
    if not felder:
        return
    set_clause = ", ".join(f"{k} = ?" for k in felder)
    values = list(felder.values()) + [impfung_id]
    db.execute(f"UPDATE impfungen SET {set_clause} WHERE id = ?", values)
    db.commit()


def delete_impfung(impfung_id):
    db = get_db()
    db.execute("DELETE FROM impfungen WHERE id = ?", (impfung_id,))
    db.commit()


# ============================================================
# CRUD: Dokumente
# ============================================================

def save_dokument(patient_id, dateiname, daten, impfung_id=None):
    db = get_db()
    db.execute(
        "INSERT INTO dokumente (patient_id, dateiname, daten, impfung_id) "
        "VALUES (?, ?, ?, ?)",
        (patient_id, dateiname, daten, impfung_id)
    )
    db.commit()
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_dokument(dokument_id):
    db = get_db()
    return db.execute(
        "SELECT * FROM dokumente WHERE id = ?", (dokument_id,)
    ).fetchone()


def get_dokumente_fuer_patient(patient_id):
    db = get_db()
    return db.execute(
        "SELECT id, patient_id, impfung_id, dateiname, erstellt_am "
        "FROM dokumente WHERE patient_id = ? ORDER BY erstellt_am DESC",
        (patient_id,)
    ).fetchall()


def get_dokument_fuer_impfung(impfung_id):
    db = get_db()
    return db.execute(
        "SELECT id, patient_id, impfung_id, dateiname, erstellt_am "
        "FROM dokumente WHERE impfung_id = ?", (impfung_id,)
    ).fetchone()


def delete_dokument(dokument_id):
    db = get_db()
    db.execute("DELETE FROM dokumente WHERE id = ?", (dokument_id,))
    db.commit()


# ============================================================
# Protokoll (Audit Log)
# ============================================================

def log_aktion(benutzer_id, benutzer_name, aktion, entitaet_typ,
               entitaet_id, entitaet_bezeichnung, aenderungen=None):
    """Schreibt einen Protokoll-Eintrag."""
    db = get_db()
    aenderungen_str = json.dumps(aenderungen, ensure_ascii=False) if aenderungen else None
    db.execute(
        "INSERT INTO protokoll (benutzer_id, benutzer_name, aktion, "
        "entitaet_typ, entitaet_id, entitaet_bezeichnung, aenderungen) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (benutzer_id, benutzer_name, aktion, entitaet_typ,
         entitaet_id, entitaet_bezeichnung, aenderungen_str)
    )
    db.commit()


def get_protokoll(entitaet_typ=None, benutzer_id=None,
                  datum_von=None, datum_bis=None, limit=50, offset=0):
    db = get_db()
    sql = "SELECT * FROM protokoll"
    where = []
    params = []
    if entitaet_typ:
        where.append("entitaet_typ = ?")
        params.append(entitaet_typ)
    if benutzer_id:
        where.append("benutzer_id = ?")
        params.append(benutzer_id)
    if datum_von:
        where.append("zeitpunkt >= ?")
        params.append(datum_von)
    if datum_bis:
        where.append("zeitpunkt <= ?")
        params.append(datum_bis)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY zeitpunkt DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return db.execute(sql, params).fetchall()


def count_protokoll(entitaet_typ=None, benutzer_id=None,
                    datum_von=None, datum_bis=None):
    db = get_db()
    sql = "SELECT COUNT(*) FROM protokoll"
    where = []
    params = []
    if entitaet_typ:
        where.append("entitaet_typ = ?")
        params.append(entitaet_typ)
    if benutzer_id:
        where.append("benutzer_id = ?")
        params.append(benutzer_id)
    if datum_von:
        where.append("zeitpunkt >= ?")
        params.append(datum_von)
    if datum_bis:
        where.append("zeitpunkt <= ?")
        params.append(datum_bis)
    if where:
        sql += " WHERE " + " AND ".join(where)
    return db.execute(sql, params).fetchone()[0]


# ============================================================
# Einstellungen
# ============================================================

def get_einstellung(schluessel, default=None):
    db = get_db()
    row = db.execute(
        "SELECT wert FROM einstellungen WHERE schluessel = ?", (schluessel,)
    ).fetchone()
    return row['wert'] if row else default


def set_einstellung(schluessel, wert):
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO einstellungen (schluessel, wert) VALUES (?, ?)",
        (schluessel, wert)
    )
    db.commit()


# ============================================================
# Dashboard-Statistiken
# ============================================================

def get_dashboard_stats():
    db = get_db()
    stats = {}
    stats['einrichtungen'] = db.execute("SELECT COUNT(*) FROM einrichtungen").fetchone()[0]
    stats['stationen'] = db.execute("SELECT COUNT(*) FROM stationen").fetchone()[0]
    stats['patienten_aktiv'] = db.execute(
        "SELECT COUNT(*) FROM patienten WHERE aktiv = 1"
    ).fetchone()[0]
    stats['patienten_heim'] = db.execute(
        "SELECT COUNT(*) FROM patienten WHERE aktiv = 1 AND wohnort_typ = 'HEIM'"
    ).fetchone()[0]
    stats['patienten_zuhause'] = db.execute(
        "SELECT COUNT(*) FROM patienten WHERE aktiv = 1 AND wohnort_typ = 'ZUHAUSE'"
    ).fetchone()[0]
    stats['impfungen_offen'] = db.execute(
        "SELECT COUNT(*) FROM impfungen i JOIN patienten p ON i.patient_id = p.id "
        "WHERE i.status = 'OFFEN' AND p.aktiv = 1"
    ).fetchone()[0]
    stats['behandler'] = db.execute("SELECT COUNT(*) FROM behandler").fetchone()[0]

    # Faellige Visiten heute (Hausbesuche + Stationen)
    heute = date.today().isoformat()
    faellige_hausbesuche = db.execute(
        "SELECT COUNT(*) FROM patienten p "
        "LEFT JOIN stationen s ON p.station_id = s.id "
        "WHERE p.aktiv = 1 AND p.wohnort_typ = 'ZUHAUSE' AND ("
        "(COALESCE(p.intervall_tage, s.intervall_tage) IS NOT NULL AND COALESCE(p.intervall_tage, s.intervall_tage) > 0 AND "
        "datetime(p.letzter_besuch, '+' || COALESCE(p.intervall_tage, s.intervall_tage) || ' days') <= ?) OR "
        "(p.geplanter_besuch IS NOT NULL AND p.geplanter_besuch <= ?) OR "
        "(p.letzter_besuch IS NULL AND COALESCE(p.intervall_tage, s.intervall_tage) IS NOT NULL)"
        ")",
        (heute, heute)
    ).fetchone()[0]
    faellige_stationen = db.execute(
        "SELECT COUNT(*) FROM stationen s "
        "WHERE s.intervall_tage > 0 AND ("
        "datetime(s.letzter_besuch, '+' || s.intervall_tage || ' days') <= ? OR "
        "s.letzter_besuch IS NULL"
        ")",
        (heute,)
    ).fetchone()[0]
    stats['visiten_faellig'] = faellige_hausbesuche + faellige_stationen

    return stats


# ============================================================
# Export-Hilfsfunktionen
# ============================================================

def get_export_data(einrichtung_id):
    """Holt alle Daten einer Einrichtung fuer den Export."""
    db = get_db()
    einrichtung = get_einrichtung(einrichtung_id)
    if not einrichtung:
        return None

    stationen_list = get_stationen(einrichtung_id)
    result = {
        'einrichtung': dict(einrichtung),
        'stationen': []
    }

    for station in stationen_list:
        patienten = get_patienten_by_station(station['id'])
        station_data = {
            'station': dict(station),
            'patienten': []
        }
        for patient in patienten:
            impfungen = get_impfungen(patient['id'])
            station_data['patienten'].append({
                'patient': dict(patient),
                'impfungen': [dict(i) for i in impfungen]
            })
        result['stationen'].append(station_data)

    return result


def get_faellige_patienten(stichtag=None):
    """
    Gibt alle aktiven Patienten zurueck, die am Stichtag faellig sind.
    Faellig = intervall_tage abgelaufen ODER geplanter_besuch <= stichtag.
    Nur Zuhause-Patienten (Heim-Patienten nutzen Stations-Counter).
    """
    db = get_db()
    if stichtag is None:
        stichtag = date.today().isoformat()
    return db.execute(
        "SELECT p.*, COALESCE(p.override_kein_behandler, 0) AS override_kein_behandler, "
        "e.name AS einrichtung_name, s.name AS station_name, "
        "COALESCE(p.override_behandler_id, p.primaer_behandler_id, s.standard_behandler_id, e.standard_behandler_id) AS resolved_behandler_id, "
        "COALESCE(p.latitude, e.latitude) AS resolved_latitude, "
        "COALESCE(p.longitude, e.longitude) AS resolved_longitude, "
        "b.name AS behandler_name, b.farbe AS behandler_farbe "
        "FROM patienten p "
        "LEFT JOIN stationen s ON p.station_id = s.id "
        "LEFT JOIN einrichtungen e ON s.einrichtung_id = e.id "
        "LEFT JOIN behandler b ON b.id = COALESCE(p.override_behandler_id, p.primaer_behandler_id, s.standard_behandler_id, e.standard_behandler_id) "
        "WHERE p.aktiv = 1 AND p.wohnort_typ = 'ZUHAUSE' AND ("
        "(COALESCE(p.intervall_tage, s.intervall_tage) IS NOT NULL AND COALESCE(p.intervall_tage, s.intervall_tage) > 0 AND "
        "datetime(p.letzter_besuch, '+' || COALESCE(p.intervall_tage, s.intervall_tage) || ' days') <= ?) OR "
        "(p.geplanter_besuch IS NOT NULL AND p.geplanter_besuch <= ?) OR "
        "(p.letzter_besuch IS NULL AND COALESCE(p.intervall_tage, s.intervall_tage) IS NOT NULL)"
        ") ORDER BY resolved_behandler_id, p.nachname",
        (stichtag, stichtag)
    ).fetchall()


def get_tagesplan(stichtag=None, praxis_lat=None, praxis_lon=None, transportmodi=None):
    """
    Erstellt den Tagesplan: Patienten und Stationen gruppiert nach Behandler, optimierte Route.
    transportmodi: Dict {behandler_id: 'auto'|'fahrrad'|'fuss'} - Transportmodus pro Behandler.
    Bei 'fahrrad' oder 'fuss' werden Patienten ausserhalb des konfigurierten Radius
    in die Gruppe 'Ohne Zuordnung' verschoben.
    """
    import routing

    if stichtag is None:
        stichtag = date.today().isoformat()
    if transportmodi is None:
        transportmodi = {}

    faellige_patienten = get_faellige_patienten(stichtag)
    faellige_stationen = get_faellige_stationen(stichtag)

    # Praxis-Koordinaten (Fallback) - frueh laden fuer Radius-Check
    if praxis_lat is None or praxis_lon is None:
        praxis_lat = float(get_einstellung('praxis_lat', '49.7913'))
        praxis_lon = float(get_einstellung('praxis_lon', '9.9534'))

    # Radius-Einstellungen laden
    radius_fussweg = float(get_einstellung('radius_fussweg', '1.0'))
    radius_fahrrad = float(get_einstellung('radius_fahrrad', '5.0'))

    # Beides in eine Liste werfen mit Typ-Flag
    alle_besuche = []
    for p in faellige_patienten:
        d = dict(p)
        d['_typ'] = 'P'
        d['latitude'] = d.get('resolved_latitude') or d.get('latitude')
        d['longitude'] = d.get('resolved_longitude') or d.get('longitude')
        # Entfernung zur Praxis berechnen (fuer spaetere Radius-Pruefung)
        if d.get('latitude') and d.get('longitude'):
            d['entfernung_km'] = round(routing.haversine_distance(
                praxis_lat, praxis_lon, d['latitude'], d['longitude']
            ), 1)
        alle_besuche.append(d)
    for s in faellige_stationen:
        d = dict(s)
        d['_typ'] = 'S'
        d['besuchsdauer_minuten'] = 15
        # Entfernung zur Praxis berechnen (fuer spaetere Radius-Pruefung)
        if d.get('latitude') and d.get('longitude'):
            d['entfernung_km'] = round(routing.haversine_distance(
                praxis_lat, praxis_lon, d['latitude'], d['longitude']
            ), 1)
        alle_besuche.append(d)

    # Gruppieren nach Behandler
    behandler_gruppen = {}
    ohne_behandler = []

    for b in alle_besuche:
        if b.get('override_kein_behandler'):
            ohne_behandler.append(b)
            continue
        if b['resolved_behandler_id']:
            bid = b['resolved_behandler_id']
            if bid not in behandler_gruppen:
                behandler_gruppen[bid] = {
                    'behandler': {
                        'id': bid,
                        'name': b['behandler_name'] or 'Unbekannt',
                        'farbe': b['behandler_farbe'] or '#33656E',
                    },
                    'besuche': []
                }
            behandler_gruppen[bid]['besuche'].append(b)
        else:
            ohne_behandler.append(b)

    start = (praxis_lat, praxis_lon)

    # Radius-Check pro Behandler: Patienten ausserhalb verschieben
    ausserhalb_radius = 0
    for bid, gruppe in list(behandler_gruppen.items()):
        modus = transportmodi.get(int(bid), 'auto')
        if modus == 'fuss':
            radius_km = radius_fussweg
        elif modus == 'fahrrad':
            radius_km = radius_fahrrad
        else:
            continue  # Auto = kein Radius-Limit

        verbleibend = []
        for b in gruppe['besuche']:
            if b.get('entfernung_km') is not None and b['entfernung_km'] > radius_km:
                b['ausserhalb_radius'] = True
                ohne_behandler.append(b)
                ausserhalb_radius += 1
            else:
                verbleibend.append(b)
        gruppe['besuche'] = verbleibend

    # Leere Gruppen entfernen
    behandler_gruppen = {bid: g for bid, g in behandler_gruppen.items() if g['besuche']}

    # Routen optimieren
    routen = []
    for bid, gruppe in behandler_gruppen.items():
        modus = transportmodi.get(int(bid), 'auto')
        optimiert = routing.optimiere_route(start, gruppe['besuche'])
        stats = routing.berechne_routen_stats(start, optimiert, modus)
        maps_url = routing.google_maps_route_url(start, optimiert)
        if modus == 'fuss':
            radius_km = radius_fussweg
        elif modus == 'fahrrad':
            radius_km = radius_fahrrad
        else:
            radius_km = None
        routen.append({
            'behandler': gruppe['behandler'],
            'besuche': optimiert,
            'stats': stats,
            'maps_url': maps_url,
            'transportmodus': modus,
            'radius_km': radius_km,
        })

    # Ohne Behandler als eigene Gruppe (separat, nicht in routen)
    ohne_zuordnung_route = None
    if ohne_behandler:
        optimiert = routing.optimiere_route(start, ohne_behandler)
        stats = routing.berechne_routen_stats(start, optimiert, 'auto')
        maps_url = routing.google_maps_route_url(start, optimiert)
        ohne_zuordnung_route = {
            'behandler': {'id': None, 'name': 'Ohne Zuordnung', 'farbe': '#999999'},
            'besuche': optimiert,
            'stats': stats,
            'maps_url': maps_url,
            'transportmodus': 'auto',
            'radius_km': None,
        }

    return {
        'datum': stichtag,
        'praxis_coords': start,
        'transportmodi': transportmodi,
        'ausserhalb_radius': ausserhalb_radius,
        'routen': routen,
        'ohne_zuordnung': ohne_zuordnung_route,
        'gesamt_patienten': len(faellige_patienten),
        'faellige_stationen_count': len(faellige_stationen)
    }


def update_geocoordinates(patient_id, latitude, longitude, geocode_status='OK'):
    """Speichert Geokoordinaten und Geocode-Status fuer einen Patienten."""
    db = get_db()
    db.execute(
        "UPDATE patienten SET latitude = ?, longitude = ?, geocode_status = ? WHERE id = ?",
        (latitude, longitude, geocode_status, patient_id)
    )
    db.commit()


def get_faellige_stationen(stichtag=None):
    """
    Gibt alle Stationen zurueck, deren Besuchsintervall abgelaufen ist.
    """
    db = get_db()
    if stichtag is None:
        stichtag = date.today().isoformat()
    return db.execute(
        "SELECT s.*, COALESCE(s.override_kein_behandler, 0) AS override_kein_behandler, "
        "e.name AS einrichtung_name, e.adresse, e.latitude, e.longitude, "
        "COALESCE(s.override_behandler_id, s.standard_behandler_id, e.standard_behandler_id) AS resolved_behandler_id, "
        "b.name AS behandler_name, b.farbe AS behandler_farbe "
        "FROM stationen s "
        "JOIN einrichtungen e ON s.einrichtung_id = e.id "
        "LEFT JOIN behandler b ON b.id = COALESCE(s.override_behandler_id, s.standard_behandler_id, e.standard_behandler_id) "
        "WHERE s.intervall_tage > 0 AND ("
        "datetime(s.letzter_besuch, '+' || s.intervall_tage || ' days') <= ? OR "
        "s.letzter_besuch IS NULL"
        ") ORDER BY e.name, s.name",
        (stichtag,)
    ).fetchall()
