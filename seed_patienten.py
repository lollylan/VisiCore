"""
Fügt 20 fiktive Testpatienten (Herr-der-Ringe-Charaktere) in die VisiCore-DB ein.
Einmalig ausführen, danach kann die Datei gelöscht werden.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
import database as db
from datetime import date, timedelta

app = create_app()

patienten = [
    ("Beutlin",    "Frodo",     "1968-09-22", "Mergentheimer Str. 12, 97082 Würzburg",   14, "Hobbit, sehr kooperativ"),
    ("Beutlin",    "Bilbo",     "1942-09-22", "Mergentheimer Str. 14, 97082 Würzburg",   14, "Hohes Alter, CAVE: Ringsucht"),
    ("Gamdschie",  "Samweis",   "1970-04-06", "Rottendorfer Str. 3, 97074 Würzburg",     21, None),
    ("Tuk",        "Peregrin",  "1980-01-01", "Zellerauer Str. 7, 97082 Würzburg",       30, "Impulsiv, schwierige Compliance"),
    ("Brandybock", "Meridoc",   "1978-11-02", "Heidingsfelder Str. 22, 97084 Würzburg",  30, None),
    ("Graurock",   "Gandalf",   "1920-01-01", "Sanderglacis 5, 97072 Würzburg",           7, "Sehr alt, gelegentlich abwesend"),
    ("Klingenfels","Aragorn",   "1969-03-01", "Domerpfarrgasse 8, 97070 Würzburg",       14, None),
    ("Halbelf",    "Arwen",     "1975-06-10", "Juliuspromenade 11, 97070 Würzburg",      21, None),
    ("Goldfuß",    "Gimli",     "1966-01-13", "Haugerring 4, 97072 Würzburg",            14, "Taubt auf dem linken Ohr"),
    ("Grünblatt",  "Legolas",   "1973-07-28", "Spiegelstr. 9, 97072 Würzburg",           21, None),
    ("Weiß",       "Saruman",   "1930-05-05", "Pleichertorstr. 6, 97070 Würzburg",       14, "CAVE: Ablehnung von Empfehlungen"),
    ("Sackheim",   "Boromir",   "1972-06-01", "Frankfurter Str. 18, 97082 Würzburg",     14, None),
    ("Baumdorn",   "Faramir",   "1975-07-15", "Veitshöchheimer Str. 12, 97080 Würzburg", 30, None),
    ("Goldfaden",  "Galadriel", "1945-08-20", "Äußere Pleichertorstr. 3, 97070 Würzburg",21, None),
    ("Halbelbe",   "Elrond",    "1940-10-03", "Röntgenring 7, 97070 Würzburg",           30, "Benötigt Dolmetscher"),
    ("Schwarzhand","Sauron",    "1910-12-01", "Bahnhofstr. 2, 97070 Würzburg",           14, "CAVE: Sehr schwieriger Patient"),
    ("Stiefmoos",  "Treebeard", "1902-03-03", "Beethovenstr. 31, 97074 Würzburg",        60, "Extrem langsam in Entscheidungen"),
    ("Nagelmann",  "Pippin",    "1982-02-22", "Ludwigstr. 15, 97070 Würzburg",           21, None),
    ("Düsterwald",  "Éowyn",   "1977-09-14", "Eichhornstr. 5, 97072 Würzburg",          14, None),
    ("Reitermark", "Théoden",   "1950-08-11", "Bismarckstr. 20, 97074 Würzburg",         14, "Herzinsuffizienz bekannt"),
]

impfungen = [
    # (patient_index, impftyp, intervall_jahre, reset_monat)
    (0,  "Influenza",    1, 9),
    (0,  "COVID-19",     1, None),
    (1,  "Influenza",    1, 9),
    (1,  "Pneumokokken", 5, None),
    (1,  "COVID-19",     1, None),
    (2,  "Influenza",    1, 9),
    (5,  "Influenza",    1, 9),
    (5,  "Pneumokokken", 5, None),
    (6,  "Tetanus",      10, None),
    (6,  "COVID-19",     1, None),
    (8,  "Influenza",    1, 9),
    (8,  "Tetanus",      10, None),
    (14, "Influenza",    1, 9),
    (14, "Pneumokokken", 5, None),
    (16, "Influenza",    1, 9),
    (19, "Influenza",    1, 9),
    (19, "COVID-19",     1, None),
]

heute = date.today()

with app.app_context():
    db.init_db()
    conn = db.get_db()

    patient_ids = []
    for p in patienten:
        nachname, vorname, geb, adresse, intervall, cave = p
        # letzter_besuch: zufällig zwischen 0 und intervall*2 Tagen zurück
        import random
        random.seed(nachname + vorname)
        tage_zurueck = random.randint(0, intervall * 2)
        letzter = (heute - timedelta(days=tage_zurueck)).isoformat()

        pid = db.create_patient(
            nachname=nachname,
            vorname=vorname,
            geburtsdatum=geb,
            wohnort_typ='ZUHAUSE',
            adresse=adresse,
            intervall_tage=intervall,
            besuchsdauer_minuten=15,
            cave=cave,
            letzter_besuch=letzter,
        )
        patient_ids.append(pid)
        print(f"  ✅ {nachname}, {vorname} (ID {pid})")

    for pat_idx, impftyp, intervall_j, reset_m in impfungen:
        pid = patient_ids[pat_idx]
        iid = db.create_impfung(pid, impftyp, False, intervall_j, reset_m)
        print(f"     💉 {impftyp} für Patient-ID {pid}")

    print(f"\n✅ {len(patienten)} Patienten und {len(impfungen)} Impfungen angelegt.")
