"""
PieksPlan - Datenbank-Layer
Verschluesselte SQLite-Datenbank mit SQLCipher.
"""

import os
import json
from datetime import date, datetime
import sqlcipher3
from flask import g, current_app


# ============================================================
# Verbindungsmanagement
# ============================================================

def get_db():
    """Gibt die DB-Verbindung fuer den aktuellen Request zurueck."""
    if 'db' not in g:
        db_path = current_app.config['DB_PATH']
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        g.db = sqlcipher3.connect(db_path)
        g.db.execute(f"PRAGMA key='{current_app.config['DB_ENCRYPTION_KEY']}'")
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

        CREATE TABLE IF NOT EXISTS pflegeheime (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            adresse TEXT,
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS wohngruppen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pflegeheim_id INTEGER NOT NULL REFERENCES pflegeheime(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS bewohner (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wohngruppe_id INTEGER NOT NULL REFERENCES wohngruppen(id),
            nachname TEXT NOT NULL,
            vorname TEXT NOT NULL,
            geburtsdatum DATE,
            aktiv BOOLEAN DEFAULT 1,
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS impfungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bewohner_id INTEGER NOT NULL REFERENCES bewohner(id) ON DELETE CASCADE,
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
            naechste_faelligkeit DATE,
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS dokumente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bewohner_id INTEGER NOT NULL REFERENCES bewohner(id) ON DELETE CASCADE,
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
    ''')
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
    Wird bei jedem relevanten Seitenaufruf ausgefuehrt.

    Logik:
    1. Grippe: Wird am 1. September jeden Jahres wieder OFFEN
       (es sei denn NEIN ohne Nachfragen)
    2. Corona: Wird 1 Jahr nach Durchfuehrung wieder OFFEN
    3. Andere: naechste_faelligkeit pruefen
    4. NACHFRAGEN-Status: Einverstaendnis zurucksetzen wenn
       Jahr abgelaufen (Corona: Neujahr, Grippe: September)
    """
    db = get_db()
    heute = date.today()
    aktuelles_jahr = heute.year
    grippe_saison_start = date(aktuelles_jahr, 9, 1)
    grippe_saison_aktiv = heute >= grippe_saison_start

    # Grippe-Saison-Jahr: Wenn vor September, gilt Vorjahrs-Saison
    grippe_saison_jahr = aktuelles_jahr if grippe_saison_aktiv else aktuelles_jahr - 1

    # --- 1. Grippe: September-Logik ---
    if grippe_saison_aktiv:
        # Finde Grippe-Impfungen die DURCHGEFUEHRT sind aber
        # deren Durchfuehrung VOR dieser Saison liegt
        grippe_durchgefuehrt = db.execute(
            "SELECT id, einverstaendnis_status, durchfuehrung_datum "
            "FROM impfungen "
            "WHERE impftyp LIKE '%Grippe%' "
            "AND status = 'DURCHGEFUEHRT' "
            "AND durchfuehrung_datum < ? "
            "AND einverstaendnis_status != 'NEIN'",
            (grippe_saison_start.isoformat(),)
        ).fetchall()

        for imp in grippe_durchgefuehrt:
            db.execute(
                "UPDATE impfungen SET status = 'OFFEN', "
                "plan_datum = NULL, durchfuehrung_datum = NULL, "
                "naechste_faelligkeit = NULL "
                "WHERE id = ?", (imp['id'],)
            )

    # --- 2. Corona: 1-Jahres-Logik ---
    corona_faellig = db.execute(
        "SELECT id, einverstaendnis_status "
        "FROM impfungen "
        "WHERE impftyp LIKE '%Corona%' "
        "AND status = 'DURCHGEFUEHRT' "
        "AND naechste_faelligkeit IS NOT NULL "
        "AND naechste_faelligkeit <= ? "
        "AND einverstaendnis_status != 'NEIN'",
        (heute.isoformat(),)
    ).fetchall()

    for imp in corona_faellig:
        db.execute(
            "UPDATE impfungen SET status = 'OFFEN', "
            "plan_datum = NULL, durchfuehrung_datum = NULL, "
            "naechste_faelligkeit = NULL "
            "WHERE id = ?", (imp['id'],)
        )

    # --- 3. Andere Impfungen mit naechster Faelligkeit ---
    andere_faellig = db.execute(
        "SELECT id, einverstaendnis_status "
        "FROM impfungen "
        "WHERE impftyp NOT LIKE '%Grippe%' "
        "AND impftyp NOT LIKE '%Corona%' "
        "AND status = 'DURCHGEFUEHRT' "
        "AND naechste_faelligkeit IS NOT NULL "
        "AND naechste_faelligkeit <= ? "
        "AND einverstaendnis_status != 'NEIN'",
        (heute.isoformat(),)
    ).fetchall()

    for imp in andere_faellig:
        db.execute(
            "UPDATE impfungen SET status = 'OFFEN', "
            "plan_datum = NULL "
            "WHERE id = ?", (imp['id'],)
        )

    # --- 4. NACHFRAGEN-Status: Einverstaendnis zuruecksetzen ---
    # Grippe: Wenn neue Saison (September) und altes Einverstaendnis
    if grippe_saison_aktiv:
        db.execute(
            "UPDATE impfungen SET "
            "einverstaendnis_status = 'NICHT_ANGEFRAGT', "
            "einverstaendnis_jahr = NULL "
            "WHERE impftyp LIKE '%Grippe%' "
            "AND einverstaendnis_status IN "
            "('JA_JAEHRLICH_NACHFRAGEN', 'NEIN_JAEHRLICH_NACHFRAGEN') "
            "AND (einverstaendnis_jahr IS NULL OR einverstaendnis_jahr < ?)",
            (grippe_saison_jahr,)
        )

    # Corona + Andere: Wenn neues Kalenderjahr und altes Einverstaendnis
    db.execute(
        "UPDATE impfungen SET "
        "einverstaendnis_status = 'NICHT_ANGEFRAGT', "
        "einverstaendnis_jahr = NULL "
        "WHERE impftyp NOT LIKE '%Grippe%' "
        "AND einverstaendnis_status IN "
        "('JA_JAEHRLICH_NACHFRAGEN', 'NEIN_JAEHRLICH_NACHFRAGEN') "
        "AND (einverstaendnis_jahr IS NULL OR einverstaendnis_jahr < ?)",
        (aktuelles_jahr,)
    )

    db.commit()


# ============================================================
# CRUD: Pflegeheime
# ============================================================

def get_pflegeheime():
    db = get_db()
    return db.execute(
        'SELECT * FROM pflegeheime ORDER BY name'
    ).fetchall()


def get_pflegeheim(pflegeheim_id):
    db = get_db()
    return db.execute(
        'SELECT * FROM pflegeheime WHERE id = ?', (pflegeheim_id,)
    ).fetchone()


def create_pflegeheim(name, adresse=''):
    db = get_db()
    db.execute(
        'INSERT INTO pflegeheime (name, adresse) VALUES (?, ?)',
        (name, adresse)
    )
    db.commit()


def update_pflegeheim(pflegeheim_id, name, adresse=''):
    db = get_db()
    db.execute(
        'UPDATE pflegeheime SET name = ?, adresse = ? WHERE id = ?',
        (name, adresse, pflegeheim_id)
    )
    db.commit()


def delete_pflegeheim(pflegeheim_id):
    db = get_db()
    db.execute('DELETE FROM pflegeheime WHERE id = ?', (pflegeheim_id,))
    db.commit()


# ============================================================
# CRUD: Wohngruppen
# ============================================================

def get_wohngruppen(pflegeheim_id):
    db = get_db()
    return db.execute(
        'SELECT * FROM wohngruppen WHERE pflegeheim_id = ? ORDER BY name',
        (pflegeheim_id,)
    ).fetchall()


def get_wohngruppe(wohngruppe_id):
    db = get_db()
    return db.execute(
        'SELECT w.*, p.name as pflegeheim_name, p.id as pflegeheim_id '
        'FROM wohngruppen w JOIN pflegeheime p ON w.pflegeheim_id = p.id '
        'WHERE w.id = ?',
        (wohngruppe_id,)
    ).fetchone()


def get_alle_wohngruppen():
    """Alle Wohngruppen mit Pflegeheim-Name (fuer Umzug-Dropdown)."""
    db = get_db()
    return db.execute(
        'SELECT w.id, w.name, p.name as pflegeheim_name '
        'FROM wohngruppen w JOIN pflegeheime p ON w.pflegeheim_id = p.id '
        'ORDER BY p.name, w.name'
    ).fetchall()


def create_wohngruppe(pflegeheim_id, name):
    db = get_db()
    db.execute(
        'INSERT INTO wohngruppen (pflegeheim_id, name) VALUES (?, ?)',
        (pflegeheim_id, name)
    )
    db.commit()


def update_wohngruppe(wohngruppe_id, name):
    db = get_db()
    db.execute(
        'UPDATE wohngruppen SET name = ? WHERE id = ?',
        (name, wohngruppe_id)
    )
    db.commit()


def delete_wohngruppe(wohngruppe_id):
    db = get_db()
    db.execute('DELETE FROM wohngruppen WHERE id = ?', (wohngruppe_id,))
    db.commit()


# ============================================================
# CRUD: Bewohner
# ============================================================

def get_bewohner_by_wohngruppe(wohngruppe_id, nur_aktive=True):
    db = get_db()
    query = 'SELECT * FROM bewohner WHERE wohngruppe_id = ?'
    if nur_aktive:
        query += ' AND aktiv = 1'
    query += ' ORDER BY nachname, vorname'
    return db.execute(query, (wohngruppe_id,)).fetchall()


def get_bewohner(bewohner_id):
    db = get_db()
    return db.execute(
        'SELECT b.*, w.name as wohngruppe_name, w.pflegeheim_id, '
        'p.name as pflegeheim_name '
        'FROM bewohner b '
        'JOIN wohngruppen w ON b.wohngruppe_id = w.id '
        'JOIN pflegeheime p ON w.pflegeheim_id = p.id '
        'WHERE b.id = ?',
        (bewohner_id,)
    ).fetchone()


def get_inaktive_bewohner():
    db = get_db()
    return db.execute(
        'SELECT b.*, w.name as wohngruppe_name, p.name as pflegeheim_name '
        'FROM bewohner b '
        'JOIN wohngruppen w ON b.wohngruppe_id = w.id '
        'JOIN pflegeheime p ON w.pflegeheim_id = p.id '
        'WHERE b.aktiv = 0 '
        'ORDER BY b.nachname, b.vorname'
    ).fetchall()


def create_bewohner(wohngruppe_id, nachname, vorname, geburtsdatum=None):
    db = get_db()
    db.execute(
        'INSERT INTO bewohner (wohngruppe_id, nachname, vorname, geburtsdatum) '
        'VALUES (?, ?, ?, ?)',
        (wohngruppe_id, nachname, vorname, geburtsdatum)
    )
    db.commit()


def update_bewohner(bewohner_id, nachname, vorname, geburtsdatum=None):
    db = get_db()
    db.execute(
        'UPDATE bewohner SET nachname = ?, vorname = ?, geburtsdatum = ? '
        'WHERE id = ?',
        (nachname, vorname, geburtsdatum, bewohner_id)
    )
    db.commit()


def deaktiviere_bewohner(bewohner_id):
    db = get_db()
    db.execute('UPDATE bewohner SET aktiv = 0 WHERE id = ?', (bewohner_id,))
    db.commit()


def aktiviere_bewohner(bewohner_id):
    db = get_db()
    db.execute('UPDATE bewohner SET aktiv = 1 WHERE id = ?', (bewohner_id,))
    db.commit()


def delete_bewohner(bewohner_id):
    db = get_db()
    db.execute('DELETE FROM bewohner WHERE id = ?', (bewohner_id,))
    db.commit()


def umziehen_bewohner(bewohner_id, neue_wohngruppe_id):
    db = get_db()
    db.execute(
        'UPDATE bewohner SET wohngruppe_id = ? WHERE id = ?',
        (neue_wohngruppe_id, bewohner_id)
    )
    db.commit()


# ============================================================
# CRUD: Impfungen
# ============================================================

def get_impfungen(bewohner_id):
    db = get_db()
    return db.execute(
        'SELECT * FROM impfungen WHERE bewohner_id = ? ORDER BY impftyp',
        (bewohner_id,)
    ).fetchall()


def get_impfung(impfung_id):
    db = get_db()
    return db.execute(
        'SELECT i.*, b.nachname, b.vorname, b.wohngruppe_id '
        'FROM impfungen i JOIN bewohner b ON i.bewohner_id = b.id '
        'WHERE i.id = ?',
        (impfung_id,)
    ).fetchone()


def create_impfung(bewohner_id, impftyp, ist_standardimpfung=False,
                   wiederholung_intervall_jahre=None):
    db = get_db()
    db.execute(
        'INSERT INTO impfungen (bewohner_id, impftyp, ist_standardimpfung, '
        'wiederholung_intervall_jahre) VALUES (?, ?, ?, ?)',
        (bewohner_id, impftyp, ist_standardimpfung,
         wiederholung_intervall_jahre)
    )
    db.commit()


def update_impfung(impfung_id, **kwargs):
    """Aktualisiert beliebige Felder einer Impfung."""
    db = get_db()
    erlaubte_felder = {
        'impftyp', 'einverstaendnis_status', 'einverstaendnis_jahr',
        'plan_datum', 'status', 'durchfuehrung_datum',
        'wiederholung_intervall_jahre', 'naechste_faelligkeit'
    }
    felder = {k: v for k, v in kwargs.items() if k in erlaubte_felder}
    if not felder:
        return

    set_clause = ', '.join(f'{k} = ?' for k in felder.keys())
    values = list(felder.values()) + [impfung_id]
    db.execute(f'UPDATE impfungen SET {set_clause} WHERE id = ?', values)
    db.commit()


def delete_impfung(impfung_id):
    db = get_db()
    db.execute('DELETE FROM impfungen WHERE id = ?', (impfung_id,))
    db.commit()


# ============================================================
# CRUD: Benutzer
# ============================================================

def get_user_by_id(user_id):
    db = get_db()
    return db.execute(
        'SELECT * FROM users WHERE id = ?', (user_id,)
    ).fetchone()


def get_user_by_name(benutzername):
    db = get_db()
    return db.execute(
        'SELECT * FROM users WHERE benutzername = ?', (benutzername,)
    ).fetchone()


def get_all_users():
    db = get_db()
    return db.execute(
        'SELECT id, benutzername, rolle, erstellt_am FROM users ORDER BY benutzername'
    ).fetchall()


def create_user(benutzername, passwort_hash, rolle='nutzer'):
    db = get_db()
    db.execute(
        'INSERT INTO users (benutzername, passwort_hash, rolle) VALUES (?, ?, ?)',
        (benutzername, passwort_hash, rolle)
    )
    db.commit()


def delete_user(user_id):
    db = get_db()
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()


# ============================================================
# CRUD: Dokumente (verschluesselt in SQLCipher)
# ============================================================

def save_dokument(bewohner_id, dateiname, daten, impfung_id=None):
    """Speichert ein PDF-Dokument als BLOB in der verschluesselten DB."""
    db = get_db()
    db.execute(
        'INSERT INTO dokumente (bewohner_id, impfung_id, dateiname, daten) '
        'VALUES (?, ?, ?, ?)',
        (bewohner_id, impfung_id, dateiname, daten)
    )
    db.commit()


def get_dokument(dokument_id):
    """Holt ein Dokument inkl. BLOB-Daten."""
    db = get_db()
    return db.execute(
        'SELECT * FROM dokumente WHERE id = ?', (dokument_id,)
    ).fetchone()


def get_dokumente_fuer_bewohner(bewohner_id):
    """Alle Dokumente eines Bewohners (ohne Impfung-Zuordnung)."""
    db = get_db()
    return db.execute(
        'SELECT id, dateiname, erstellt_am FROM dokumente '
        'WHERE bewohner_id = ? AND impfung_id IS NULL '
        'ORDER BY erstellt_am DESC',
        (bewohner_id,)
    ).fetchall()


def get_dokument_fuer_impfung(impfung_id):
    """Das Dokument einer Impfung (max. 1)."""
    db = get_db()
    return db.execute(
        'SELECT id, dateiname, erstellt_am FROM dokumente '
        'WHERE impfung_id = ? LIMIT 1',
        (impfung_id,)
    ).fetchone()


def delete_dokument(dokument_id):
    db = get_db()
    db.execute('DELETE FROM dokumente WHERE id = ?', (dokument_id,))
    db.commit()


# ============================================================
# Protokoll (Audit Log)
# ============================================================

def log_aktion(benutzer_id, benutzer_name, aktion, entitaet_typ,
               entitaet_id, entitaet_bezeichnung, aenderungen=None):
    """Schreibt einen Protokoll-Eintrag."""
    db = get_db()
    aenderungen_json = json.dumps(aenderungen, ensure_ascii=False) if aenderungen else None
    db.execute(
        'INSERT INTO protokoll (benutzer_id, benutzer_name, aktion, '
        'entitaet_typ, entitaet_id, entitaet_bezeichnung, aenderungen) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        (benutzer_id, benutzer_name, aktion, entitaet_typ,
         entitaet_id, entitaet_bezeichnung, aenderungen_json)
    )
    db.commit()


def get_protokoll(entitaet_typ=None, benutzer_id=None,
                  datum_von=None, datum_bis=None, limit=50, offset=0):
    """Holt Protokoll-Eintraege mit optionalen Filtern."""
    db = get_db()
    query = 'SELECT * FROM protokoll WHERE 1=1'
    params = []

    if entitaet_typ:
        query += ' AND entitaet_typ = ?'
        params.append(entitaet_typ)
    if benutzer_id:
        query += ' AND benutzer_id = ?'
        params.append(benutzer_id)
    if datum_von:
        query += ' AND zeitpunkt >= ?'
        params.append(datum_von)
    if datum_bis:
        query += ' AND zeitpunkt <= ?'
        params.append(datum_bis + ' 23:59:59')

    query += ' ORDER BY zeitpunkt DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    return db.execute(query, params).fetchall()


def count_protokoll(entitaet_typ=None, benutzer_id=None,
                    datum_von=None, datum_bis=None):
    """Zaehlt Protokoll-Eintraege fuer Paginierung."""
    db = get_db()
    query = 'SELECT COUNT(*) FROM protokoll WHERE 1=1'
    params = []

    if entitaet_typ:
        query += ' AND entitaet_typ = ?'
        params.append(entitaet_typ)
    if benutzer_id:
        query += ' AND benutzer_id = ?'
        params.append(benutzer_id)
    if datum_von:
        query += ' AND zeitpunkt >= ?'
        params.append(datum_von)
    if datum_bis:
        query += ' AND zeitpunkt <= ?'
        params.append(datum_bis + ' 23:59:59')

    return db.execute(query, params).fetchone()[0]


# ============================================================
# Export-Hilfsfunktionen
# ============================================================

def get_export_data(pflegeheim_id):
    """Holt alle Daten eines Pflegeheims fuer den Export."""
    db = get_db()
    pflegeheim = get_pflegeheim(pflegeheim_id)
    if not pflegeheim:
        return None

    wohngruppen = get_wohngruppen(pflegeheim_id)
    result = {
        'pflegeheim': dict(pflegeheim),
        'wohngruppen': []
    }

    for wg in wohngruppen:
        bewohner_list = get_bewohner_by_wohngruppe(wg['id'])
        wg_data = {
            'name': wg['name'],
            'bewohner': []
        }
        for bew in bewohner_list:
            impfungen = get_impfungen(bew['id'])
            bew_data = dict(bew)
            bew_data['impfungen'] = [dict(imp) for imp in impfungen]
            wg_data['bewohner'].append(bew_data)
        result['wohngruppen'].append(wg_data)

    return result


# ============================================================
# Dashboard-Statistiken
# ============================================================

def get_dashboard_stats():
    """Zaehlt Pflegeheime, Wohngruppen, Bewohner und offene Impfungen."""
    db = get_db()
    stats = {}
    stats['pflegeheime'] = db.execute(
        'SELECT COUNT(*) FROM pflegeheime'
    ).fetchone()[0]
    stats['wohngruppen'] = db.execute(
        'SELECT COUNT(*) FROM wohngruppen'
    ).fetchone()[0]
    stats['bewohner_aktiv'] = db.execute(
        'SELECT COUNT(*) FROM bewohner WHERE aktiv = 1'
    ).fetchone()[0]
    stats['impfungen_offen'] = db.execute(
        'SELECT COUNT(*) FROM impfungen WHERE status = "OFFEN"'
    ).fetchone()[0]
    stats['impfungen_geplant'] = db.execute(
        'SELECT COUNT(*) FROM impfungen WHERE status = "GEPLANT"'
    ).fetchone()[0]
    stats['impfungen_durchgefuehrt'] = db.execute(
        'SELECT COUNT(*) FROM impfungen WHERE status = "DURCHGEFUEHRT"'
    ).fetchone()[0]
    stats['einverstaendnis_offen'] = db.execute(
        'SELECT COUNT(*) FROM impfungen WHERE einverstaendnis_status = "NICHT_ANGEFRAGT"'
    ).fetchone()[0]
    return stats
