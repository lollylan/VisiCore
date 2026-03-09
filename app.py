"""
VisiCore - Hauptanwendung
Kombiniert Visitenplanung (Visicycle) und Impfmanagement (PieksPlan).
"""

import os
import json
import shutil
from datetime import datetime, date, timedelta
from functools import wraps
from io import BytesIO

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    jsonify, send_file, g, abort
)
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from flask_bcrypt import Bcrypt
from flask_wtf import CSRFProtect
from dotenv import load_dotenv

import database as db
import routing
import export as pdf_export


# Pfad-Helfer (fuer Portable-Betrieb und .exe)
import sys

def get_base_dir():
    """Verzeichnis neben der .exe bzw. neben app.py (fuer Daten, .env)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_dir():
    """Verzeichnis der eingebetteten Ressourcen (templates, static)."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


dotenv_path = os.path.join(get_base_dir(), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    load_dotenv()


def create_app():
    resource_dir = get_resource_dir()
    app = Flask(__name__,
                static_folder=os.path.join(resource_dir, 'static'),
                template_folder=os.path.join(resource_dir, 'templates'))

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-me')
    app.config['DB_KEY'] = os.environ.get('DB_KEY', 'dev-db-key')
    app.config['DB_PATH'] = os.path.join(get_base_dir(), 'data', 'visicore.db')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB Upload-Limit

    bcrypt = Bcrypt(app)
    csrf = CSRFProtect(app)
    login_manager = LoginManager(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Bitte einloggen.'
    login_manager.login_message_category = 'warning'

    db.init_app(app)

    # ── User-Klasse fuer Flask-Login ──────────────────────
    class User(UserMixin):
        def __init__(self, user_row):
            self.id = user_row['id']
            self.benutzername = user_row['benutzername']
            self.rolle = user_row['rolle']

        def is_admin(self):
            return self.rolle == 'admin'

    @login_manager.user_loader
    def load_user(user_id):
        user_row = db.get_user_by_id(int(user_id))
        if user_row:
            return User(user_row)
        return None

    # ── Decorators ────────────────────────────────────────
    def admin_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_admin():
                flash('Nur fuer Administratoren.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated

    # ── Kontext-Injection ─────────────────────────────────
    @app.context_processor
    def inject_globals():
        return {
            'app_name': 'VisiCore',
            'current_year': date.today().year,
            'now': datetime.now
        }

    # ── Jinja-Filter ──────────────────────────────────────
    @app.template_filter('from_json')
    def from_json_filter(value):
        if not value:
            return {}
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}

    @app.template_filter('grippe_saison')
    def grippe_saison_filter(jahr):
        if not jahr:
            return ''
        try:
            j = int(jahr)
            return f"{j}/{j+1}"
        except (ValueError, TypeError):
            return str(jahr)

    @app.template_filter('datum')
    def datum_filter(value):
        """Konvertiert YYYY-MM-DD in DD.MM.YYYY."""
        if not value:
            return ''
        try:
            if isinstance(value, str):
                d = datetime.strptime(value[:10], '%Y-%m-%d')
            elif isinstance(value, (date, datetime)):
                d = value
            else:
                return str(value)
            return d.strftime('%d.%m.%Y')
        except (ValueError, TypeError):
            return str(value)

    @app.template_filter('einverstaendnis_label')
    def einverstaendnis_label_filter(status):
        """Übersetzt technische Stati in benutzerfreundliche Labels."""
        mapping = {
            'JA': 'ok',
            'NEIN': 'nein',
            'JA_JAEHRLICH': 'ok jährlich',
            'JA_JAEHRLICH_NACHFRAGEN': 'ok jährlich nachfragen',
            'NEIN_JAEHRLICH_NACHFRAGEN': 'nein jährlich nachfragen',
            'NICHT_ANGEFRAGT': 'nicht angefragt',
            'ANGEFRAGT': 'angefragt',
        }
        return mapping.get(status, status)

    @app.template_filter('zeitstempel')
    def zeitstempel_filter(value):
        """Konvertiert ISO-Zeitstempel in DD.MM.YYYY HH:MM."""
        if not value:
            return ''
        try:
            if isinstance(value, str):
                d = datetime.fromisoformat(value)
            elif isinstance(value, (date, datetime)):
                d = value
            else:
                return str(value)
            return d.strftime('%d.%m.%Y %H:%M')
        except (ValueError, TypeError):
            return str(value)

    # ── Helfer: Audit-Protokoll ───────────────────────────
    def protokoll(aktion, entitaet_typ, entitaet_id, bezeichnung, aenderungen=None):
        db.log_aktion(
            current_user.id, current_user.benutzername,
            aktion, entitaet_typ, entitaet_id, bezeichnung, aenderungen
        )

    def feld_diff(alt_row, neu_dict, felder):
        """Vergleicht DB-Row mit neuem Dict, gibt Aenderungen zurueck."""
        diff = {}
        for f in felder:
            alt = str(alt_row[f]) if alt_row[f] is not None else ''
            neu = str(neu_dict.get(f, '')) if neu_dict.get(f) is not None else ''
            if alt != neu:
                diff[f] = {'alt': alt, 'neu': neu}
        return diff if diff else None

    # ════════════════════════════════════════════════════════
    # AUTH ROUTES
    # ════════════════════════════════════════════════════════

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        if request.method == 'POST':
            benutzername = request.form.get('benutzername', '').strip()
            passwort = request.form.get('passwort', '')
            user_row = db.get_user_by_name(benutzername)
            if user_row and bcrypt.check_password_hash(user_row['passwort_hash'], passwort):
                login_user(User(user_row))
                protokoll('LOGIN', 'Benutzer', user_row['id'], benutzername)
                return redirect(url_for('dashboard'))
            flash('Benutzername oder Passwort falsch.', 'danger')
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        protokoll('LOGOUT', 'Benutzer', current_user.id, current_user.benutzername)
        logout_user()
        flash('Erfolgreich abgemeldet.', 'success')
        return redirect(url_for('login'))

    # ════════════════════════════════════════════════════════
    # DASHBOARD
    # ════════════════════════════════════════════════════════

    @app.route('/')
    @login_required
    def dashboard():
        db.faelligkeits_check()
        stats = db.get_dashboard_stats()
        return render_template('dashboard.html', stats=stats)

    # ════════════════════════════════════════════════════════
    # EINRICHTUNGEN
    # ════════════════════════════════════════════════════════

    @app.route('/einrichtungen')
    @login_required
    def einrichtungen_liste():
        einrichtungen = db.get_einrichtungen()
        return render_template('einrichtungen/liste.html', einrichtungen=einrichtungen)

    @app.route('/einrichtungen/neu', methods=['GET', 'POST'])
    @login_required
    def einrichtung_neu():
        behandler_liste = db.get_alle_behandler()
        praxis_stadt = db.get_einstellung('praxis_stadt', os.environ.get('PRAXIS_STADT', ''))
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            strasse = request.form.get('strasse', '').strip()
            plz = request.form.get('plz', '').strip()
            stadt = request.form.get('stadt', '').strip()
            adresse = _compose_adresse(strasse, plz, stadt)
            behandler_id = request.form.get('standard_behandler_id') or None
            try:
                bid = int(behandler_id) if behandler_id else None
            except ValueError:
                bid = None

            if not name:
                flash('Name ist erforderlich.', 'danger')
                return _einrichtung_form_render()
            # Geocoding der Einrichtungs-Adresse
            lat, lon = None, None
            if adresse:
                lat, lon, _ = _geocode_adresse(adresse)
                if lat is None:
                    flash('Adresse der Einrichtung konnte nicht geocodiert werden.', 'warning')
            eid = db.create_einrichtung(name, adresse, latitude=lat, longitude=lon, standard_behandler_id=bid)
            protokoll('ERSTELLT', 'Einrichtung', eid, name)
            flash(f'Einrichtung "{name}" erstellt.', 'success')
            return redirect(url_for('einrichtung_detail', id=eid))
        return _einrichtung_form_render()

    @app.route('/einrichtungen/<int:id>')
    @login_required
    def einrichtung_detail(id):
        einrichtung = db.get_einrichtung(id)
        if not einrichtung:
            abort(404)
        stationen = db.get_stationen(id)
        
        stationen_mit_bewohnern = []
        for s in stationen:
            patienten = db.get_patienten_by_station(s['id'])
            bewohner_liste = []
            for p in patienten:
                offene_impfungen = db.get_offene_impfungen(p['id'])
                bewohner_liste.append({
                    'daten': p,
                    'impfungen': offene_impfungen
                })
            stationen_mit_bewohnern.append({
                'station': s,
                'bewohner': bewohner_liste
            })

        return render_template('einrichtungen/detail.html',
                               einrichtung=einrichtung, 
                               stationen=stationen,
                               stationen_mit_bewohnern=stationen_mit_bewohnern)

    @app.route('/einrichtungen/<int:id>/bearbeiten', methods=['GET', 'POST'])
    @login_required
    def einrichtung_bearbeiten(id):
        einrichtung = db.get_einrichtung(id)
        if not einrichtung:
            abort(404)
        behandler_liste = db.get_alle_behandler()
        praxis_stadt = db.get_einstellung('praxis_stadt', os.environ.get('PRAXIS_STADT', ''))
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            strasse = request.form.get('strasse', '').strip()
            plz = request.form.get('plz', '').strip()
            stadt = request.form.get('stadt', '').strip()
            adresse = _compose_adresse(strasse, plz, stadt)
            behandler_id = request.form.get('standard_behandler_id') or None
            try:
                bid = int(behandler_id) if behandler_id else None
            except ValueError:
                bid = None

            if not name:
                flash('Name ist erforderlich.', 'danger')
                return _einrichtung_form_render(einrichtung=einrichtung)
            # Re-Geocoding wenn Adresse sich geändert hat
            lat, lon = einrichtung['latitude'], einrichtung['longitude']
            if adresse and adresse != einrichtung['adresse']:
                lat, lon, _ = _geocode_adresse(adresse)
                if lat is None:
                    flash('Adresse der Einrichtung konnte nicht geocodiert werden.', 'warning')
            elif not adresse:
                lat, lon = None, None
            diff = feld_diff(einrichtung, {'name': name, 'adresse': adresse, 'standard_behandler_id': bid},
                             ['name', 'adresse', 'standard_behandler_id'])
            db.update_einrichtung(id, name, adresse, latitude=lat, longitude=lon, standard_behandler_id=bid)
            protokoll('BEARBEITET', 'Einrichtung', id, name, diff)
            flash('Einrichtung aktualisiert.', 'success')
            return redirect(url_for('einrichtung_detail', id=id))
        return _einrichtung_form_render(einrichtung=einrichtung)

    def _einrichtung_form_render(einrichtung=None):
        behandler_liste = db.get_alle_behandler()
        praxis_stadt = db.get_einstellung('praxis_stadt', os.environ.get('PRAXIS_STADT', ''))
        # Adresse in Einzelteile zerlegen für das Formular
        if einrichtung and einrichtung['adresse']:
            einrichtung = dict(einrichtung)
            einrichtung['strasse'], einrichtung['plz'], einrichtung['stadt'] = _parse_adresse(einrichtung['adresse'])
        return render_template('einrichtungen/form.html',
                               einrichtung=einrichtung, behandler=behandler_liste,
                               praxis_stadt=praxis_stadt)

    @app.route('/einrichtungen/<int:id>/loeschen', methods=['POST'])
    @login_required
    @admin_required
    def einrichtung_loeschen(id):
        einrichtung = db.get_einrichtung(id)
        if einrichtung:
            protokoll('GELOESCHT', 'Einrichtung', id, einrichtung['name'])
            db.delete_einrichtung(id)
            flash('Einrichtung geloescht.', 'success')
        return redirect(url_for('einrichtungen_liste'))

    # ════════════════════════════════════════════════════════
    # STATIONEN
    # ════════════════════════════════════════════════════════

    @app.route('/einrichtungen/<int:e_id>/stationen/neu', methods=['GET', 'POST'])
    @login_required
    def station_neu(e_id):
        einrichtung = db.get_einrichtung(e_id)
        if not einrichtung:
            abort(404)
        behandler_liste = db.get_alle_behandler()
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            intervall = request.form.get('intervall_tage', '28')
            behandler_id = request.form.get('standard_behandler_id') or None
            if not name:
                flash('Name ist erforderlich.', 'danger')
                return render_template('stationen/form.html', einrichtung=einrichtung, behandler=behandler_liste)
            try:
                intervall_tage = int(intervall)
            except ValueError:
                intervall_tage = 28
            letzter_besuch = request.form.get('letzter_besuch') or None
            try:
                bid = int(behandler_id) if behandler_id else None
            except ValueError:
                bid = None

            sid = db.create_station(e_id, name, intervall_tage, standard_behandler_id=bid, letzter_besuch=letzter_besuch)
            protokoll('ERSTELLT', 'Station', sid, f"{einrichtung['name']} / {name}")
            flash(f'Station "{name}" erstellt.', 'success')
            return redirect(url_for('station_detail', id=sid))
        return render_template('stationen/form.html', einrichtung=einrichtung, behandler=behandler_liste)

    @app.route('/stationen/<int:id>')
    @login_required
    def station_detail(id):
        station = db.get_station(id)
        if not station:
            abort(404)
        patienten = db.get_patienten_by_station(id)
        patienten_mit_impfungen = []
        for p in patienten:
            offene_impfungen = db.get_offene_impfungen(p['id'])
            patienten_mit_impfungen.append({
                'daten': p,
                'impfungen': offene_impfungen
            })
        return render_template('stationen/detail.html',
                               station=station, patienten=patienten,
                               patienten_mit_impfungen=patienten_mit_impfungen)

    @app.route('/stationen/<int:id>/bearbeiten', methods=['GET', 'POST'])
    @login_required
    def station_bearbeiten(id):
        station = db.get_station(id)
        if not station:
            abort(404)
        einrichtung = db.get_einrichtung(station['einrichtung_id'])
        behandler_liste = db.get_alle_behandler()
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            intervall = request.form.get('intervall_tage', '28')
            behandler_id = request.form.get('standard_behandler_id') or None
            if not name:
                flash('Name ist erforderlich.', 'danger')
                return render_template('stationen/form.html',
                                       station=station, einrichtung=einrichtung, behandler=behandler_liste)
            try:
                intervall_tage = int(intervall)
            except ValueError:
                intervall_tage = 28
            letzter_besuch = request.form.get('letzter_besuch') or None
            try:
                bid = int(behandler_id) if behandler_id else None
            except ValueError:
                bid = None

            diff = feld_diff(station, {'name': name, 'intervall_tage': str(intervall_tage), 'standard_behandler_id': bid, 'letzter_besuch': letzter_besuch},
                             ['name', 'intervall_tage', 'standard_behandler_id', 'letzter_besuch'])
            db.update_station(id, name, intervall_tage, standard_behandler_id=bid, letzter_besuch=letzter_besuch)
            protokoll('BEARBEITET', 'Station', id, name, diff)
            flash('Station aktualisiert.', 'success')
            return redirect(url_for('station_detail', id=id))
        return render_template('stationen/form.html',
                               station=station, einrichtung=einrichtung, behandler=behandler_liste)

    @app.route('/stationen/<int:id>/loeschen', methods=['POST'])
    @login_required
    @admin_required
    def station_loeschen(id):
        station = db.get_station(id)
        if station:
            einrichtung_id = station['einrichtung_id']
            protokoll('GELOESCHT', 'Station', id, station['name'])
            db.delete_station(id)
            flash('Station geloescht.', 'success')
            return redirect(url_for('einrichtung_detail', id=einrichtung_id))
        return redirect(url_for('einrichtungen_liste'))

    @app.route('/stationen/<int:id>/visite', methods=['POST'])
    @login_required
    def station_visite(id):
        station = db.get_station(id)
        if station:
            db.station_visite_registrieren(id)
            protokoll('VISITE', 'Station', id, station['name'])
            flash(f'Stationsvisite fuer "{station["name"]}" registriert.', 'success')
            return redirect(url_for('station_detail', id=id))
        return redirect(url_for('einrichtungen_liste'))

    # ════════════════════════════════════════════════════════
    # PATIENTEN
    # ════════════════════════════════════════════════════════

    @app.route('/patienten')
    @login_required
    def patienten_liste():
        wohnort = request.args.get('wohnort', None)
        patienten = db.get_patienten(nur_aktive=True, wohnort_typ=wohnort)
        behandler = db.get_alle_behandler()
        return render_template('patienten/liste.html',
                               patienten=patienten, behandler=behandler,
                               wohnort_filter=wohnort)

    @app.route('/patienten/neu', methods=['GET', 'POST'])
    @login_required
    def patient_neu():
        vorwahl_station_id = request.args.get('vorwahl_station_id', type=int)
        if request.method == 'POST':
            nachname = request.form.get('nachname', '').strip()
            vorname = request.form.get('vorname', '').strip()
            if not nachname or not vorname:
                flash('Name ist erforderlich.', 'danger')
                return _patient_form_render(vorwahl_station_id=vorwahl_station_id)

            wohnort_typ = request.form.get('wohnort_typ', 'ZUHAUSE')
            geburtsdatum = request.form.get('geburtsdatum') or None
            # Adresse aus Einzelfeldern zusammensetzen
            strasse = request.form.get('strasse', '').strip()
            plz = request.form.get('plz', '').strip()
            stadt = request.form.get('stadt', '').strip()
            adresse = _compose_adresse(strasse, plz, stadt) if wohnort_typ == 'ZUHAUSE' else None
            station_id = request.form.get('station_id') or None
            intervall = request.form.get('intervall_tage') or None
            besuchsdauer = request.form.get('besuchsdauer_minuten', '30')
            behandler_id = request.form.get('primaer_behandler_id') or None
            cave = request.form.get('cave', '').strip() or None
            notizen = request.form.get('notizen', '').strip() or None
            ist_einmalig = 'ist_einmalig' in request.form
            letzter_besuch = request.form.get('letzter_besuch') or None

            try:
                intervall_tage = int(intervall) if intervall else None
            except ValueError:
                intervall_tage = None
            try:
                besuchsdauer_min = int(besuchsdauer)
            except ValueError:
                besuchsdauer_min = 30
            try:
                station_id_int = int(station_id) if station_id else None
            except ValueError:
                station_id_int = None
            try:
                bid_val = int(behandler_id) if behandler_id else None
            except ValueError:
                bid_val = None

            pid = db.create_patient(
                nachname=nachname, vorname=vorname,
                wohnort_typ=wohnort_typ, geburtsdatum=geburtsdatum,
                adresse=adresse, station_id=station_id_int,
                intervall_tage=intervall_tage,
                besuchsdauer_minuten=besuchsdauer_min,
                primaer_behandler_id=bid_val,
                cave=cave, notizen=notizen, ist_einmalig=ist_einmalig,
                letzter_besuch=letzter_besuch
            )
            # Auto-Geocoding für Zuhause-Patienten
            if wohnort_typ == 'ZUHAUSE' and adresse:
                lat, lon, status = _geocode_adresse(adresse)
                db.update_geocoordinates(pid, lat, lon, status)
                if status == 'FEHLER':
                    flash('Adresse konnte nicht geocodiert werden. Bitte überprüfen.', 'warning')
            protokoll('ERSTELLT', 'Patient', pid, f"{nachname}, {vorname}")
            flash(f'Patient "{nachname}, {vorname}" erstellt.', 'success')
            return redirect(url_for('patient_detail', id=pid))

        return _patient_form_render(vorwahl_station_id=vorwahl_station_id)

    def _compose_adresse(strasse, plz, stadt):
        """Setzt Adresse aus Einzelteilen zusammen."""
        teile = []
        if strasse:
            teile.append(strasse)
        ort = f"{plz} {stadt}".strip() if plz or stadt else ''
        if ort:
            teile.append(ort)
        return ', '.join(teile) if teile else None

    def _geocode_adresse(adresse):
        """Geocodiert eine Adresse via Nominatim. Gibt (lat, lon, status) zurück."""
        if not adresse:
            return None, None, None
        try:
            from geopy.geocoders import Nominatim
            geolocator = Nominatim(user_agent='visicore')
            location = geolocator.geocode(adresse, timeout=5)
            if location:
                return location.latitude, location.longitude, 'OK'
            return None, None, 'FEHLER'
        except Exception:
            return None, None, 'FEHLER'

    def _parse_adresse(adresse):
        """Zerlegt 'Straße Nr., PLZ Stadt' in Einzelteile."""
        if not adresse:
            return '', '', ''
        import re
        # Format: "Straße Nr., PLZ Stadt" oder "Straße Nr., Stadt"
        m = re.match(r'^(.+?),\s*(\d{5})\s+(.+)$', adresse)
        if m:
            return m.group(1).strip(), m.group(2), m.group(3).strip()
        # Fallback: Komma-getrennt ohne PLZ
        m = re.match(r'^(.+?),\s*(.+)$', adresse)
        if m:
            return m.group(1).strip(), '', m.group(2).strip()
        return adresse, '', ''

    def _patient_form_render(patient=None, vorwahl_station_id=None):
        stationen = db.get_alle_stationen()
        behandler = db.get_alle_behandler()
        praxis_stadt = db.get_einstellung('praxis_stadt', os.environ.get('PRAXIS_STADT', ''))
        # Adresse in Einzelteile zerlegen für das Formular
        if patient and patient['adresse']:
            patient = dict(patient)
            patient['strasse'], patient['plz'], patient['stadt'] = _parse_adresse(patient['adresse'])
        return render_template('patienten/form.html',
                               patient=patient, stationen=stationen,
                               behandler=behandler, vorwahl_station_id=vorwahl_station_id,
                               praxis_stadt=praxis_stadt)

    @app.route('/patienten/<int:id>')
    @login_required
    def patient_detail(id):
        patient = db.get_patient(id)
        if not patient:
            abort(404)
        impfungen = db.get_impfungen(id)
        dokumente = db.get_dokumente_fuer_patient(id)
        behandler = db.get_alle_behandler()
        stationen = db.get_alle_stationen()
        return render_template('patienten/detail.html',
                               patient=patient, impfungen=impfungen,
                               dokumente=dokumente, behandler=behandler,
                               stationen=stationen)

    @app.route('/patienten/<int:id>/bearbeiten', methods=['GET', 'POST'])
    @login_required
    def patient_bearbeiten(id):
        patient = db.get_patient(id)
        if not patient:
            abort(404)
        if request.method == 'POST':
            felder = {}
            for key in ['nachname', 'vorname', 'geburtsdatum', 'wohnort_typ',
                         'cave', 'notizen']:
                val = request.form.get(key, '').strip()
                felder[key] = val if val else None

            # Adresse aus Einzelfeldern zusammensetzen
            wohnort_typ = felder.get('wohnort_typ', 'ZUHAUSE')
            if wohnort_typ == 'ZUHAUSE':
                strasse = request.form.get('strasse', '').strip()
                plz = request.form.get('plz', '').strip()
                stadt = request.form.get('stadt', '').strip()
                felder['adresse'] = _compose_adresse(strasse, plz, stadt)
            else:
                felder['adresse'] = None

            for key in ['station_id', 'intervall_tage', 'besuchsdauer_minuten',
                         'primaer_behandler_id']:
                val = request.form.get(key)
                try:
                    felder[key] = int(val) if val else None
                except ValueError:
                    felder[key] = None

            felder['ist_einmalig'] = 'ist_einmalig' in request.form
            felder['letzter_besuch'] = request.form.get('letzter_besuch') or None

            if not felder.get('nachname') or not felder.get('vorname'):
                flash('Name ist erforderlich.', 'danger')
                return _patient_form_render(patient)

            diff = feld_diff(patient, felder,
                             ['nachname', 'vorname', 'wohnort_typ', 'adresse',
                              'cave', 'notizen', 'intervall_tage', 'letzter_besuch'])
            db.update_patient(id, **felder)

            # Re-Geocoding wenn Adresse sich geändert hat
            if wohnort_typ == 'ZUHAUSE' and felder['adresse']:
                alte_adresse = patient['adresse'] if patient else None
                if felder['adresse'] != alte_adresse:
                    lat, lon, status = _geocode_adresse(felder['adresse'])
                    db.update_geocoordinates(id, lat, lon, status)
                    if status == 'FEHLER':
                        flash('Adresse konnte nicht geocodiert werden. Bitte überprüfen.', 'warning')
            elif wohnort_typ == 'HEIM':
                # Koordinaten löschen, da vom Heim vererbt
                db.update_geocoordinates(id, None, None, None)

            protokoll('BEARBEITET', 'Patient', id,
                      f"{felder['nachname']}, {felder['vorname']}", diff)
            flash('Patient aktualisiert.', 'success')
            return redirect(url_for('patient_detail', id=id))
        return _patient_form_render(patient)

    @app.route('/patienten/<int:id>/deaktivieren', methods=['POST'])
    @login_required
    def patient_deaktivieren(id):
        patient = db.get_patient(id)
        if patient:
            db.deaktiviere_patient(id)
            protokoll('DEAKTIVIERT', 'Patient', id,
                      f"{patient['nachname']}, {patient['vorname']}")
            flash('Patient deaktiviert.', 'warning')
        return redirect(url_for('patienten_liste'))

    @app.route('/patienten/<int:id>/aktivieren', methods=['POST'])
    @login_required
    def patient_aktivieren(id):
        patient = db.get_patient(id)
        if patient:
            db.aktiviere_patient(id)
            protokoll('AKTIVIERT', 'Patient', id,
                      f"{patient['nachname']}, {patient['vorname']}")
            flash('Patient aktiviert.', 'success')
        return redirect(url_for('patient_detail', id=id))

    @app.route('/patienten/<int:id>/loeschen', methods=['POST'])
    @login_required
    @admin_required
    def patient_loeschen(id):
        patient = db.get_patient(id)
        if patient:
            protokoll('GELOESCHT', 'Patient', id,
                      f"{patient['nachname']}, {patient['vorname']}")
            db.delete_patient(id)
            flash('Patient geloescht.', 'success')
        return redirect(url_for('patienten_liste'))

    @app.route('/patienten/<int:id>/visite', methods=['POST'])
    @login_required
    def patient_visite(id):
        patient = db.patient_visite_registrieren(id)
        if patient:
            protokoll('VISITE', 'Patient', id,
                      f"{patient['nachname']}, {patient['vorname']}")
            flash('Visite registriert.', 'success')
            return redirect(url_for('patient_detail', id=id))
        abort(404)

    @app.route('/patienten/<int:id>/behandler-wechsel', methods=['POST'])
    @login_required
    def patient_behandler_wechsel(id):
        patient = db.get_patient(id)
        if not patient:
            abort(404)
        behandler_id_raw = request.form.get('behandler_id', '').strip()
        permanent = request.form.get('permanent') == '1'
        datum = request.form.get('datum', date.today().isoformat())

        bid = None
        if behandler_id_raw:
            try:
                bid = int(behandler_id_raw)
            except ValueError:
                abort(400)

        if permanent:
            db.update_patient(id, primaer_behandler_id=bid, override_behandler_id=None)
            aenderung_typ = 'dauerhaft'
        else:
            db.update_patient(id, override_behandler_id=bid)
            aenderung_typ = 'einmalig'

        behandler_name = 'Ohne Zuordnung'
        if bid:
            b = db.get_behandler(bid)
            if b:
                behandler_name = b['name']

        protokoll('BEHANDLER_GEAENDERT', 'Patient', id,
                  f"{patient['nachname']}, {patient['vorname']}",
                  {'typ': aenderung_typ, 'behandler': behandler_name})
        flash(
            f'Behandler {"dauerhaft" if permanent else "für diesen Besuch"} geändert: {behandler_name}',
            'success'
        )
        return redirect(url_for('tagesplan', datum=datum))

    @app.route('/patienten/<int:id>/umziehen', methods=['POST'])
    @login_required
    def patient_umziehen(id):
        patient = db.get_patient(id)
        if not patient:
            abort(404)
        neue_station_id = request.form.get('neue_station_id')
        if neue_station_id:
            try:
                sid = int(neue_station_id)
                neue_station = db.get_station(sid)
                if neue_station:
                    db.umziehen_patient(id, sid)
                    protokoll('UMGEZOGEN', 'Patient', id,
                              f"{patient['nachname']}, {patient['vorname']}",
                              {'neue_station': neue_station['name']})
                    flash(f'Patient umgezogen nach "{neue_station["name"]}".', 'success')
            except ValueError:
                pass
        return redirect(url_for('patient_detail', id=id))

    @app.route('/patienten/inaktive')
    @login_required
    def inaktive_patienten():
        patienten = db.get_inaktive_patienten()
        return render_template('patienten/inaktive.html', patienten=patienten)

    # ════════════════════════════════════════════════════════
    # IMPFUNGEN
    # ════════════════════════════════════════════════════════

    @app.route('/patienten/<int:p_id>/impfungen/neu', methods=['GET', 'POST'])
    @login_required
    def impfung_neu(p_id):
        patient = db.get_patient(p_id)
        if not patient:
            abort(404)
        if request.method == 'POST':
            impftyp = request.form.get('impftyp', '').strip()
            if not impftyp:
                flash('Impftyp ist erforderlich.', 'danger')
                return render_template('impfungen/form.html', patient=patient)

            ist_standard = 'ist_standardimpfung' in request.form
            intervall = request.form.get('wiederholung_intervall_jahre')
            try:
                intervall_jahre = int(intervall) if intervall else None
            except ValueError:
                intervall_jahre = None
                
            reset_m = request.form.get('wiederholung_reset_monat')
            try:
                reset_monat = int(reset_m) if reset_m else None
            except ValueError:
                reset_monat = None

            iid = db.create_impfung(p_id, impftyp, ist_standard, intervall_jahre, reset_monat)
            protokoll('ERSTELLT', 'Impfung', iid,
                      f"{impftyp} ({patient['nachname']})")
            flash(f'Impfung "{impftyp}" erstellt.', 'success')
            return redirect(url_for('patient_detail', id=p_id))
        return render_template('impfungen/form.html', patient=patient)

    @app.route('/impfungen/<int:id>/bearbeiten', methods=['GET', 'POST'])
    @login_required
    def impfung_bearbeiten(id):
        impfung = db.get_impfung(id)
        if not impfung:
            abort(404)
        patient = db.get_patient(impfung['patient_id'])
        dokument = db.get_dokument_fuer_impfung(id)

        if request.method == 'POST':
            updates = {}

            # Einverstaendnis
            ev_status = request.form.get('einverstaendnis_status', 'NICHT_ANGEFRAGT')
            ev_jahr = request.form.get('einverstaendnis_jahr')
            updates['einverstaendnis_status'] = ev_status
            try:
                updates['einverstaendnis_jahr'] = int(ev_jahr) if ev_jahr else None
            except ValueError:
                updates['einverstaendnis_jahr'] = None

            # Status + Termine
            status = request.form.get('status', 'OFFEN')
            plan_datum = request.form.get('plan_datum') or None
            durchfuehrung_datum = request.form.get('durchfuehrung_datum') or None

            updates['status'] = status
            updates['plan_datum'] = plan_datum
            updates['durchfuehrung_datum'] = durchfuehrung_datum

            # Wiederholung
            intervall = request.form.get('wiederholung_intervall_jahre')
            try:
                updates['wiederholung_intervall_jahre'] = int(intervall) if intervall else None
            except ValueError:
                updates['wiederholung_intervall_jahre'] = None
                
            reset_m = request.form.get('wiederholung_reset_monat')
            try:
                updates['wiederholung_reset_monat'] = int(reset_m) if reset_m else None
            except ValueError:
                updates['wiederholung_reset_monat'] = None

            # Naechste Faelligkeit berechnen (bei Reset-Monat asynchron)
            if status == 'DURCHGEFUEHRT' and durchfuehrung_datum and updates.get('wiederholung_intervall_jahre'):
                try:
                    d = datetime.strptime(durchfuehrung_datum, '%Y-%m-%d').date()
                    nf = date(d.year + updates['wiederholung_intervall_jahre'],
                              d.month, d.day)
                    updates['naechste_faelligkeit'] = nf.isoformat()
                except (ValueError, TypeError):
                    updates['naechste_faelligkeit'] = None
            elif status != 'DURCHGEFUEHRT' or updates.get('wiederholung_reset_monat'):
                updates['naechste_faelligkeit'] = None

            db.update_impfung(id, **updates)
            protokoll('BEARBEITET', 'Impfung', id,
                      f"{impfung['impftyp']} ({patient['nachname']})")
            flash('Impfung aktualisiert.', 'success')
            return redirect(url_for('patient_detail', id=impfung['patient_id']))

        return render_template('impfungen/form.html',
                               patient=patient, impfung=impfung, dokument=dokument)

    @app.route('/impfungen/<int:id>/loeschen', methods=['POST'])
    @login_required
    def impfung_loeschen(id):
        impfung = db.get_impfung(id)
        if impfung:
            patient_id = impfung['patient_id']
            protokoll('GELOESCHT', 'Impfung', id, impfung['impftyp'])
            db.delete_impfung(id)
            flash('Impfung geloescht.', 'success')
            return redirect(url_for('patient_detail', id=patient_id))
        return redirect(url_for('patienten_liste'))

    # ════════════════════════════════════════════════════════
    # DOKUMENTE
    # ════════════════════════════════════════════════════════

    @app.route('/dokumente/upload', methods=['POST'])
    @login_required
    def dokument_upload():
        patient_id = request.form.get('patient_id')
        impfung_id = request.form.get('impfung_id') or None
        datei = request.files.get('datei')

        if not patient_id or not datei or not datei.filename:
            flash('Patient und Datei sind erforderlich.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))

        try:
            pid = int(patient_id)
            iid = int(impfung_id) if impfung_id else None
        except ValueError:
            flash('Ungueltige IDs.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))

        daten = datei.read()
        dateiname = datei.filename

        did = db.save_dokument(pid, dateiname, daten, iid)
        protokoll('HOCHGELADEN', 'Dokument', did, dateiname)
        flash(f'Dokument "{dateiname}" hochgeladen.', 'success')
        return redirect(url_for('patient_detail', id=pid))

    @app.route('/dokumente/<int:id>/download')
    @login_required
    def dokument_download(id):
        dok = db.get_dokument(id)
        if not dok:
            abort(404)
        return send_file(
            BytesIO(dok['daten']),
            download_name=dok['dateiname'],
            as_attachment=True
        )

    @app.route('/dokumente/<int:id>/loeschen', methods=['POST'])
    @login_required
    def dokument_loeschen(id):
        dok = db.get_dokument(id)
        if dok:
            patient_id = dok['patient_id']
            protokoll('GELOESCHT', 'Dokument', id, dok['dateiname'])
            db.delete_dokument(id)
            flash('Dokument geloescht.', 'success')
            return redirect(url_for('patient_detail', id=patient_id))
        return redirect(url_for('patienten_liste'))

    # ════════════════════════════════════════════════════════
    # BEHANDLER
    # ════════════════════════════════════════════════════════

    @app.route('/behandler')
    @login_required
    def behandler_liste():
        behandler = db.get_alle_behandler()
        return render_template('behandler/liste.html', behandler=behandler)

    @app.route('/behandler/neu', methods=['GET', 'POST'])
    @login_required
    def behandler_neu():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            if not name:
                flash('Name ist erforderlich.', 'danger')
                return render_template('behandler/form.html')
            rolle = request.form.get('rolle', '').strip()
            farbe = request.form.get('farbe', '#33656E')
            max_min = request.form.get('max_taegliche_minuten', '240')
            try:
                max_minuten = int(max_min)
            except ValueError:
                max_minuten = 240
            bid = db.create_behandler(name, rolle, farbe, max_minuten)
            protokoll('ERSTELLT', 'Behandler', bid, name)
            flash(f'Behandler "{name}" erstellt.', 'success')
            return redirect(url_for('behandler_liste'))
        return render_template('behandler/form.html')

    @app.route('/behandler/<int:id>/bearbeiten', methods=['GET', 'POST'])
    @login_required
    def behandler_bearbeiten(id):
        behandler = db.get_behandler(id)
        if not behandler:
            abort(404)
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            if not name:
                flash('Name ist erforderlich.', 'danger')
                return render_template('behandler/form.html', behandler=behandler)
            rolle = request.form.get('rolle', '').strip()
            farbe = request.form.get('farbe', '#33656E')
            max_min = request.form.get('max_taegliche_minuten', '240')
            try:
                max_minuten = int(max_min)
            except ValueError:
                max_minuten = 240
            diff = feld_diff(behandler,
                             {'name': name, 'rolle': rolle, 'farbe': farbe},
                             ['name', 'rolle', 'farbe'])
            db.update_behandler(id, name, rolle, farbe, max_minuten)
            protokoll('BEARBEITET', 'Behandler', id, name, diff)
            flash('Behandler aktualisiert.', 'success')
            return redirect(url_for('behandler_liste'))
        return render_template('behandler/form.html', behandler=behandler)

    @app.route('/behandler/<int:id>/loeschen', methods=['POST'])
    @login_required
    @admin_required
    def behandler_loeschen(id):
        behandler = db.get_behandler(id)
        if behandler:
            protokoll('GELOESCHT', 'Behandler', id, behandler['name'])
            db.delete_behandler(id)
            flash('Behandler geloescht.', 'success')
        return redirect(url_for('behandler_liste'))

    # ════════════════════════════════════════════════════════
    # ADMIN
    # ════════════════════════════════════════════════════════

    @app.route('/admin/nutzer')
    @login_required
    @admin_required
    def admin_nutzer():
        nutzer = db.get_all_users()
        return render_template('admin/nutzer.html', nutzer=nutzer)

    @app.route('/admin/nutzer/neu', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def admin_nutzer_neu():
        if request.method == 'POST':
            benutzername = request.form.get('benutzername', '').strip()
            passwort = request.form.get('passwort', '')
            rolle = request.form.get('rolle', 'nutzer')

            if not benutzername or not passwort:
                flash('Benutzername und Passwort sind erforderlich.', 'danger')
                return render_template('admin/nutzer_form.html')

            if db.get_user_by_name(benutzername):
                flash('Benutzername existiert bereits.', 'danger')
                return render_template('admin/nutzer_form.html')

            pw_hash = bcrypt.generate_password_hash(passwort).decode('utf-8')
            db.create_user(benutzername, pw_hash, rolle)
            protokoll('ERSTELLT', 'Benutzer', None, benutzername)
            flash(f'Benutzer "{benutzername}" erstellt.', 'success')
            return redirect(url_for('admin_nutzer'))
        return render_template('admin/nutzer_form.html')

    @app.route('/admin/nutzer/<int:id>/loeschen', methods=['POST'])
    @login_required
    @admin_required
    def admin_nutzer_loeschen(id):
        if id == current_user.id:
            flash('Eigenen Account nicht loeschbar.', 'danger')
            return redirect(url_for('admin_nutzer'))
        user = db.get_user_by_id(id)
        if user:
            protokoll('GELOESCHT', 'Benutzer', id, user['benutzername'])
            db.delete_user(id)
            flash('Benutzer geloescht.', 'success')
        return redirect(url_for('admin_nutzer'))

    @app.route('/admin/protokoll')
    @login_required
    @admin_required
    def admin_protokoll():
        seite = request.args.get('seite', 1, type=int)
        typ = request.args.get('typ', '')
        pro_seite = 50
        offset = (seite - 1) * pro_seite

        eintraege = db.get_protokoll(
            entitaet_typ=typ if typ else None,
            limit=pro_seite, offset=offset
        )
        gesamt = db.count_protokoll(entitaet_typ=typ if typ else None)
        seiten = (gesamt + pro_seite - 1) // pro_seite

        return render_template('admin/protokoll.html',
                               eintraege=eintraege, seite=seite,
                               seiten=seiten, typ=typ, gesamt=gesamt)

    @app.route('/admin/backup', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def admin_backup():
        if request.method == 'POST':
            aktion = request.form.get('aktion')

            if aktion == 'backup':
                db_path = app.config['DB_PATH']
                if os.path.exists(db_path):
                    backup_dir = os.path.join(get_base_dir(), 'backups')
                    os.makedirs(backup_dir, exist_ok=True)
                    ts = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                    backup_name = f'visicore_backup_{ts}.db'
                    backup_path = os.path.join(backup_dir, backup_name)

                    # DB-Verbindung schliessen fuer sicheren Kopiervorgang
                    close_db_temp = g.pop('db', None)
                    if close_db_temp:
                        close_db_temp.close()
                    shutil.copy2(db_path, backup_path)

                    protokoll('ERSTELLT', 'Backup', None, backup_name)
                    flash(f'Backup erstellt: {backup_name}', 'success')

            elif aktion == 'restore':
                datei = request.files.get('backup_datei')
                if datei and datei.filename:
                    db_path = app.config['DB_PATH']

                    close_db_temp = g.pop('db', None)
                    if close_db_temp:
                        close_db_temp.close()

                    datei.save(db_path)
                    flash('Datenbank wiederhergestellt. Bitte neu einloggen.', 'success')
                    return redirect(url_for('login'))
                else:
                    flash('Keine Backup-Datei ausgewaehlt.', 'danger')

            return redirect(url_for('admin_backup'))

        # Vorhandene Backups auflisten
        backup_dir = os.path.join(get_base_dir(), 'backups')
        backups = []
        if os.path.exists(backup_dir):
            for f in sorted(os.listdir(backup_dir), reverse=True):
                if f.endswith('.db'):
                    pfad = os.path.join(backup_dir, f)
                    groesse = os.path.getsize(pfad)
                    backups.append({'name': f, 'groesse': groesse})

        return render_template('admin/backup.html', backups=backups)

    @app.route('/admin/backup/<dateiname>/download')
    @login_required
    @admin_required
    def admin_backup_download(dateiname):
        backup_dir = os.path.join(get_base_dir(), 'backups')
        pfad = os.path.join(backup_dir, dateiname)
        if os.path.exists(pfad):
            return send_file(pfad, download_name=dateiname, as_attachment=True)
        abort(404)

    # ════════════════════════════════════════════════════════
    # EINSTELLUNGEN (Admin)
    # ════════════════════════════════════════════════════════

    @app.route('/admin/einstellungen', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def admin_einstellungen():
        if request.method == 'POST':
            form_type = request.form.get('_form', 'adresse')

            if form_type == 'radius':
                radius_fussweg = request.form.get('radius_fussweg', '1.0').strip()
                radius_fahrrad = request.form.get('radius_fahrrad', '5.0').strip()
                db.set_einstellung('radius_fussweg', radius_fussweg)
                db.set_einstellung('radius_fahrrad', radius_fahrrad)
                flash('Radius-Einstellungen gespeichert.', 'success')
                protokoll('BEARBEITET', 'Einstellungen', None, 'Hausbesuch-Radius')
                return redirect(url_for('admin_einstellungen'))

            praxis_name = request.form.get('praxis_name', '').strip()
            praxis_strasse = request.form.get('praxis_strasse', '').strip()
            praxis_plz = request.form.get('praxis_plz', '').strip()
            praxis_stadt = request.form.get('praxis_stadt', '').strip()

            db.set_einstellung('praxis_name', praxis_name)
            db.set_einstellung('praxis_strasse', praxis_strasse)
            db.set_einstellung('praxis_plz', praxis_plz)
            db.set_einstellung('praxis_stadt', praxis_stadt)

            # Adresse zusammensetzen und geocodieren
            adresse = f"{praxis_strasse}, {praxis_plz} {praxis_stadt}"
            db.set_einstellung('praxis_adresse', adresse)

            try:
                from geopy.geocoders import Nominatim
                geolocator = Nominatim(user_agent='visicore')
                location = geolocator.geocode(adresse, timeout=5)
                if location:
                    db.set_einstellung('praxis_lat', str(location.latitude))
                    db.set_einstellung('praxis_lon', str(location.longitude))
                    flash(f'Praxis-Adresse gespeichert und geocodiert.', 'success')
                else:
                    flash('Adresse gespeichert, aber Geocoding fehlgeschlagen. Koordinaten nicht aktualisiert.', 'warning')
            except Exception as e:
                flash(f'Adresse gespeichert, aber Geocoding-Fehler: {e}', 'warning')

            protokoll('BEARBEITET', 'Einstellungen', None, 'Praxis-Adresse')
            return redirect(url_for('admin_einstellungen'))

        return render_template('admin/einstellungen.html',
                               praxis_name=db.get_einstellung('praxis_name'),
                               praxis_strasse=db.get_einstellung('praxis_strasse'),
                               praxis_plz=db.get_einstellung('praxis_plz'),
                               praxis_stadt=db.get_einstellung('praxis_stadt'),
                               praxis_lat=db.get_einstellung('praxis_lat'),
                               praxis_lon=db.get_einstellung('praxis_lon'),
                               radius_fussweg=db.get_einstellung('radius_fussweg'),
                               radius_fahrrad=db.get_einstellung('radius_fahrrad'))

    # ════════════════════════════════════════════════════════
    # TAGESPLANER
    # ════════════════════════════════════════════════════════

    @app.route('/tagesplan')
    @login_required
    def tagesplan():
        datum = request.args.get('datum', date.today().isoformat())
        # Transportmodi pro Behandler: tm_<behandler_id>=auto|fahrrad|fuss
        transportmodi = {}
        for key, val in request.args.items():
            if key.startswith('tm_') and val in ('auto', 'fahrrad', 'fuss'):
                try:
                    bid = int(key[3:])
                    transportmodi[bid] = val
                except ValueError:
                    pass
        plan = db.get_tagesplan(stichtag=datum, transportmodi=transportmodi)
        faellige_stationen = db.get_faellige_stationen(stichtag=datum)
        alle_behandler = db.get_alle_behandler()
        return render_template('tagesplan.html',
                               plan=plan, datum=datum,
                               transportmodi=transportmodi,
                               faellige_stationen=faellige_stationen,
                               alle_behandler=alle_behandler)

    @app.route('/tagesplan/pdf')
    @login_required
    def tagesplan_pdf():
        datum = request.args.get('datum', date.today().isoformat())
        transportmodi = {}
        for key, val in request.args.items():
            if key.startswith('tm_') and val in ('auto', 'fahrrad', 'fuss'):
                try:
                    bid = int(key[3:])
                    transportmodi[bid] = val
                except ValueError:
                    pass
        plan = db.get_tagesplan(stichtag=datum, transportmodi=transportmodi)
        praxis_name = db.get_einstellung('praxis_name') or db.get_einstellung('praxis_stadt') or os.environ.get('PRAXIS_STADT', 'Praxis')
        buf = pdf_export.generate_tagesplan_pdf(plan, praxis_name)
        return send_file(
            buf,
            download_name=f'tagesplan_{datum}.pdf',
            mimetype='application/pdf',
            as_attachment=True
        )

    @app.route('/tagesplan/behandler_wechseln', methods=['POST'])
    @login_required
    def tagesplan_behandler_wechseln():
        entitaet = request.form.get('entitaet', 'patient')  # 'patient' or 'station'
        entitaet_id = request.form.get('entitaet_id', type=int)
        behandler_id_str = request.form.get('behandler_id', '')
        typ = request.form.get('typ', 'einmalig')
        datum = request.form.get('datum', date.today().isoformat())

        if not entitaet_id:
            abort(400)

        bid = int(behandler_id_str) if behandler_id_str else None
        behandler_name = 'Ohne Zuordnung'
        if bid:
            b_obj = db.get_behandler(bid)
            if b_obj:
                behandler_name = b_obj['name']

        dauerhaft = (typ == 'generell')

        if entitaet == 'station':
            station = db.get_station(entitaet_id)
            if not station:
                abort(404)
            sname = f"{station['einrichtung_name']} / {station['name']}"
            db.update_station_behandler(entitaet_id, bid, dauerhaft=dauerhaft)
            protokoll('BEARBEITET', 'Station', entitaet_id, sname,
                      {'behandler': f'{behandler_name} ({"dauerhaft" if dauerhaft else "einmalig"})'})
            flash(f'Behandler für {sname} {"dauerhaft" if dauerhaft else "einmalig"} auf „{behandler_name}“ geändert.', 'success')
        else:
            patient = db.get_patient(entitaet_id)
            if not patient:
                abort(404)
            pname = f"{patient['nachname']}, {patient['vorname']}"
            if dauerhaft:
                db.update_patient(entitaet_id, primaer_behandler_id=bid,
                                  override_behandler_id=None, override_kein_behandler=0)
                protokoll('BEARBEITET', 'Patient', entitaet_id, pname,
                          {'primaer_behandler_id': behandler_name})
                flash(f'Primärbehandler für {pname} dauerhaft auf „{behandler_name}” gesetzt.', 'success')
            elif bid is None:
                # Explizit “Ohne Zuordnung” für heute
                db.update_patient(entitaet_id, override_behandler_id=None, override_kein_behandler=1)
                protokoll('BEARBEITET', 'Patient', entitaet_id, pname,
                          {'override_behandler_id': 'Ohne Zuordnung (einmalig)'})
                flash(f'Behandler für {pname} einmalig auf „Ohne Zuordnung” gesetzt.', 'success')
            else:
                db.update_patient(entitaet_id, override_behandler_id=bid, override_kein_behandler=0)
                protokoll('BEARBEITET', 'Patient', entitaet_id, pname,
                          {'override_behandler_id': f'{behandler_name} (einmalig)'})
                flash(f'Behandler für {pname} einmalig auf „{behandler_name}” geändert.', 'success')

        redirect_args = {'datum': datum}
        for key, val in request.form.items():
            if key.startswith('tm_') and val in ('auto', 'fahrrad', 'fuss'):
                redirect_args[key] = val
        return redirect(url_for('tagesplan', **redirect_args))
    # ════════════════════════════════════════════════════════
    # EXPORT
    # ════════════════════════════════════════════════════════

    @app.route('/einrichtungen/<int:id>/export/pdf')
    @login_required
    def einrichtung_export_pdf(id):
        data = db.get_export_data(id)
        if not data:
            abort(404)
        buf = pdf_export.generate_einrichtung_pdf(data)
        name = data['einrichtung']['name'].replace(' ', '_')
        return send_file(
            buf,
            download_name=f'{name}_export.pdf',
            mimetype='application/pdf',
            as_attachment=True
        )

    @app.route('/stationen/<int:id>/export/pdf/liste')
    @login_required
    def station_export_liste_pdf(id):
        station = db.get_station(id)
        if not station:
            abort(404)
        patienten = db.get_patienten_by_station(id)
        buf = pdf_export.generate_station_liste_pdf(dict(station), [dict(p) for p in patienten])
        name = f"{station['einrichtung_name']}_{station['name']}".replace(' ', '_')
        return send_file(
            buf,
            download_name=f'{name}_liste.pdf',
            mimetype='application/pdf',
            as_attachment=True
        )

    @app.route('/stationen/<int:id>/export/pdf/erweitert')
    @login_required
    def station_export_erweitert_pdf(id):
        station = db.get_station(id)
        if not station:
            abort(404)
        patienten = db.get_patienten_by_station(id)
        patienten_mit_impfungen = []
        for p in patienten:
            offene_impfungen = db.get_offene_impfungen(p['id'])
            patienten_mit_impfungen.append({
                'daten': dict(p),
                'impfungen': [dict(i) for i in offene_impfungen]
            })
        buf = pdf_export.generate_station_erweitert_pdf(dict(station), patienten_mit_impfungen)
        name = f"{station['einrichtung_name']}_{station['name']}".replace(' ', '_')
        return send_file(
            buf,
            download_name=f'{name}_erweitert.pdf',
            mimetype='application/pdf',
            as_attachment=True
        )

    # ════════════════════════════════════════════════════════
    # GEOCODING (API)
    # ════════════════════════════════════════════════════════

    @app.route('/api/geocode', methods=['POST'])
    @login_required
    def api_geocode():
        """Geocodiert eine Adresse und speichert Koordinaten."""
        patient_id = request.json.get('patient_id')
        adresse = request.json.get('adresse', '')

        if not patient_id or not adresse:
            return jsonify({'error': 'patient_id und adresse erforderlich'}), 400

        try:
            lat, lon, status = _geocode_adresse(adresse)
            db.update_geocoordinates(int(patient_id), lat, lon, status)
            if lat is not None:
                return jsonify({
                    'success': True,
                    'latitude': lat,
                    'longitude': lon,
                })
            return jsonify({'error': 'Adresse nicht gefunden'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/geocode/batch', methods=['POST'])
    @login_required
    @admin_required
    def api_geocode_batch():
        """Geocodiert alle Patienten ohne Koordinaten."""
        import time

        patienten = db.get_patienten(nur_aktive=True, wohnort_typ='ZUHAUSE')
        erfolge = 0
        fehler = 0

        for p in patienten:
            if p['latitude'] and p['longitude']:
                continue
            if not p['adresse']:
                continue

            lat, lon, status = _geocode_adresse(p['adresse'])
            db.update_geocoordinates(p['id'], lat, lon, status)
            if status == 'OK':
                erfolge += 1
            else:
                fehler += 1
            time.sleep(1)  # Rate Limiting

        return jsonify({'erfolge': erfolge, 'fehler': fehler})

    # ════════════════════════════════════════════════════════
    # RECHTLICHES
    # ════════════════════════════════════════════════════════

    @app.route('/rechtliches')
    def rechtliches():
        return render_template('rechtliches.html')

    # ════════════════════════════════════════════════════════
    # INITIALISIERUNG: Erster Admin-Benutzer
    # ════════════════════════════════════════════════════════

    with app.app_context():
        db.init_db()
        # Standard-Admin erstellen falls keine Benutzer existieren
        if not db.get_all_users():
            pw_hash = bcrypt.generate_password_hash('admin').decode('utf-8')
            db.create_user('admin', pw_hash, 'admin')

    return app


# ════════════════════════════════════════════════════════════
# Startpunkt
# ════════════════════════════════════════════════════════════

if __name__ == '__main__':
    app = create_app()
    # Im Entwicklungsmodus mit Flask-Dev-Server
    app_port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=app_port, debug=True)
