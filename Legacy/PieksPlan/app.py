"""
PieksPlan - Hauptanwendung
Impfplanungs-Tool fuer Pflegeheime.
"""

import os
import json
import shutil
from datetime import datetime, date
from functools import wraps

from io import BytesIO
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_file, g
)
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from flask_bcrypt import Bcrypt
from flask_wtf import CSRFProtect
from dotenv import load_dotenv
import sqlcipher3

import database as db

# Helper for paths
def get_base_dir():
    import sys
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

# .env laden from base_dir so it persists/is read outside the bundled exe
dotenv_path = os.path.join(get_base_dir(), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    load_dotenv()


def create_app():
    # Helper for bundle dir (templates/static stay in _MEIPASS)
    import sys
    bundle_dir = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
    app = Flask(__name__, template_folder=os.path.join(bundle_dir, 'templates'), static_folder=os.path.join(bundle_dir, 'static'))
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-unsicher')
    app.config['DB_PATH'] = os.path.join(
        get_base_dir(), os.getenv('DB_PATH', 'data/pieksplan.db')
    )
    app.config['DB_ENCRYPTION_KEY'] = os.getenv('DB_ENCRYPTION_KEY', 'dev-passwort')
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5 MB max Upload

    # Extensions
    bcrypt = Bcrypt(app)
    csrf = CSRFProtect(app)
    login_manager = LoginManager(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Bitte melden Sie sich an.'

    # Datenbank registrieren
    db.init_app(app)

    # ============================================================
    # User-Klasse fuer Flask-Login
    # ============================================================

    class User(UserMixin):
        def __init__(self, user_row):
            self.id = user_row['id']
            self.benutzername = user_row['benutzername']
            self.rolle = user_row['rolle']

        @property
        def is_admin(self):
            return self.rolle == 'admin'

    @login_manager.user_loader
    def load_user(user_id):
        user_row = db.get_user_by_id(int(user_id))
        if user_row:
            return User(user_row)
        return None

    # Admin-only Decorator
    def admin_required(f):
        @wraps(f)
        @login_required
        def decorated(*args, **kwargs):
            if not current_user.is_admin:
                flash('Nur Administratoren haben Zugriff auf diese Seite.', 'error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated

    # ============================================================
    # Kontext-Prozessor (Template-Variablen)
    # ============================================================

    @app.context_processor
    def inject_globals():
        return {
            'current_year': datetime.now().year,
            'app_name': 'PieksPlan'
        }

    @app.template_filter('from_json')
    def from_json_filter(value):
        """Parst einen JSON-String fuer Template-Nutzung."""
        if not value:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None

    @app.template_filter('grippe_saison')
    def grippe_saison_filter(jahr):
        """Wandelt ein Jahr in Grippe-Saison-Format um: 2025 -> '2025/2026'"""
        if not jahr:
            return '-'
        return f'{jahr}/{jahr + 1}'

    # ============================================================
    # Erster Start: Admin-Konto + DB initialisieren
    # ============================================================

    with app.app_context():
        db.init_db()
        # Admin-Konto erstellen falls nicht vorhanden
        admin_user = db.get_user_by_name(os.getenv('ADMIN_USERNAME', 'admin'))
        if not admin_user:
            pw_hash = bcrypt.generate_password_hash(
                os.getenv('ADMIN_PASSWORD', 'admin')
            ).decode('utf-8')
            db.create_user(
                os.getenv('ADMIN_USERNAME', 'admin'),
                pw_hash,
                'admin'
            )

    # ============================================================
    # Protokoll-Hilfsfunktion
    # ============================================================

    def protokoll(aktion, entitaet_typ, entitaet_id, bezeichnung, aenderungen=None):
        """Loggt eine Aktion ins Protokoll mit aktuellem Benutzer."""
        db.log_aktion(
            current_user.id, current_user.benutzername,
            aktion, entitaet_typ, entitaet_id, bezeichnung, aenderungen
        )

    def feld_diff(alt_row, neu_dict, felder):
        """Vergleicht DB-Row mit neuem Dict, gibt Aenderungen zurueck."""
        diff = {}
        for feld in felder:
            alter_wert = str(alt_row[feld]) if alt_row[feld] is not None else None
            neuer_wert = str(neu_dict[feld]) if neu_dict.get(feld) is not None else None
            if alter_wert != neuer_wert:
                diff[feld] = {'alt': alter_wert, 'neu': neuer_wert}
        return diff if diff else None

    # ============================================================
    # Auth-Routen
    # ============================================================

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
                flash(f'Willkommen, {benutzername}!', 'success')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('dashboard'))
            else:
                flash('Benutzername oder Passwort falsch.', 'error')

        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('Sie wurden abgemeldet.', 'info')
        return redirect(url_for('login'))

    # ============================================================
    # Dashboard
    # ============================================================

    @app.route('/')
    @login_required
    def dashboard():
        db.faelligkeits_check()
        stats = db.get_dashboard_stats()
        pflegeheime = db.get_pflegeheime()
        return render_template('dashboard.html', stats=stats, pflegeheime=pflegeheime)

    # ============================================================
    # Pflegeheime
    # ============================================================

    @app.route('/pflegeheime')
    @login_required
    def pflegeheime_liste():
        pflegeheime = db.get_pflegeheime()
        return render_template('pflegeheime.html', pflegeheime=pflegeheime)

    @app.route('/pflegeheime/neu', methods=['GET', 'POST'])
    @login_required
    def pflegeheim_neu():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            adresse = request.form.get('adresse', '').strip()
            if name:
                db.create_pflegeheim(name, adresse)
                # ID des neu erstellten Pflegeheims ermitteln
                neue_ph = db.get_pflegeheime()
                ph_id = neue_ph[-1]['id'] if neue_ph else None
                protokoll('ERSTELLT', 'pflegeheim', ph_id, name)
                flash(f'Pflegeheim "{name}" wurde angelegt.', 'success')
                return redirect(url_for('pflegeheime_liste'))
            flash('Bitte geben Sie einen Namen ein.', 'error')
        return render_template('pflegeheim_form.html', pflegeheim=None)

    @app.route('/pflegeheime/<int:id>')
    @login_required
    def pflegeheim_detail(id):
        db.faelligkeits_check()
        pflegeheim = db.get_pflegeheim(id)
        if not pflegeheim:
            flash('Pflegeheim nicht gefunden.', 'error')
            return redirect(url_for('pflegeheime_liste'))
        wohngruppen = db.get_wohngruppen(id)

        # Bewohner + Impfungen pro Wohngruppe laden
        wg_data = []
        impfung_dokumente = {}
        for wg in wohngruppen:
            bewohner_list = db.get_bewohner_by_wohngruppe(wg['id'])
            bewohner_data = []
            for bew in bewohner_list:
                impfungen = db.get_impfungen(bew['id'])
                for imp in impfungen:
                    dok = db.get_dokument_fuer_impfung(imp['id'])
                    if dok:
                        impfung_dokumente[imp['id']] = dok
                bewohner_data.append({
                    'bewohner': bew,
                    'impfungen': impfungen
                })
            wg_data.append({
                'wohngruppe': wg,
                'bewohner_count': len(bewohner_list),
                'bewohner_data': bewohner_data
            })

        return render_template('pflegeheim_detail.html',
                               pflegeheim=pflegeheim, wg_data=wg_data,
                               impfung_dokumente=impfung_dokumente)

    @app.route('/pflegeheime/<int:id>/bearbeiten', methods=['GET', 'POST'])
    @login_required
    def pflegeheim_bearbeiten(id):
        pflegeheim = db.get_pflegeheim(id)
        if not pflegeheim:
            flash('Pflegeheim nicht gefunden.', 'error')
            return redirect(url_for('pflegeheime_liste'))

        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            adresse = request.form.get('adresse', '').strip()
            if name:
                aenderungen = feld_diff(pflegeheim, {'name': name, 'adresse': adresse}, ['name', 'adresse'])
                db.update_pflegeheim(id, name, adresse)
                protokoll('GEAENDERT', 'pflegeheim', id, name, aenderungen)
                flash(f'Pflegeheim "{name}" wurde aktualisiert.', 'success')
                return redirect(url_for('pflegeheim_detail', id=id))
            flash('Bitte geben Sie einen Namen ein.', 'error')

        return render_template('pflegeheim_form.html', pflegeheim=pflegeheim)

    @app.route('/pflegeheime/<int:id>/loeschen', methods=['POST'])
    @login_required
    def pflegeheim_loeschen(id):
        pflegeheim = db.get_pflegeheim(id)
        if pflegeheim:
            protokoll('GELOESCHT', 'pflegeheim', id, pflegeheim['name'])
            db.delete_pflegeheim(id)
            flash(f'Pflegeheim "{pflegeheim["name"]}" wurde geloescht.', 'success')
        return redirect(url_for('pflegeheime_liste'))

    # ============================================================
    # Wohngruppen
    # ============================================================

    @app.route('/pflegeheime/<int:ph_id>/wohngruppen/neu', methods=['GET', 'POST'])
    @login_required
    def wohngruppe_neu(ph_id):
        pflegeheim = db.get_pflegeheim(ph_id)
        if not pflegeheim:
            flash('Pflegeheim nicht gefunden.', 'error')
            return redirect(url_for('pflegeheime_liste'))

        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            if name:
                db.create_wohngruppe(ph_id, name)
                wgs = db.get_wohngruppen(ph_id)
                wg_id = wgs[-1]['id'] if wgs else None
                protokoll('ERSTELLT', 'wohngruppe', wg_id,
                          f'{name} ({pflegeheim["name"]})')
                flash(f'Wohngruppe "{name}" wurde angelegt.', 'success')
                return redirect(url_for('pflegeheim_detail', id=ph_id))
            flash('Bitte geben Sie einen Namen ein.', 'error')

        return render_template('wohngruppe_form.html',
                               pflegeheim=pflegeheim, wohngruppe=None)

    @app.route('/wohngruppen/<int:id>')
    @login_required
    def wohngruppe_detail(id):
        wohngruppe = db.get_wohngruppe(id)
        if not wohngruppe:
            flash('Wohngruppe nicht gefunden.', 'error')
            return redirect(url_for('pflegeheime_liste'))

        bewohner = db.get_bewohner_by_wohngruppe(id)

        # Impfungen pro Bewohner laden
        bewohner_data = []
        impfung_dokumente = {}
        for bew in bewohner:
            impfungen = db.get_impfungen(bew['id'])
            for imp in impfungen:
                dok = db.get_dokument_fuer_impfung(imp['id'])
                if dok:
                    impfung_dokumente[imp['id']] = dok
            bewohner_data.append({
                'bewohner': bew,
                'impfungen': impfungen
            })

        return render_template('wohngruppe_detail.html',
                               wohngruppe=wohngruppe,
                               bewohner_data=bewohner_data,
                               impfung_dokumente=impfung_dokumente)

    @app.route('/wohngruppen/<int:id>/bearbeiten', methods=['GET', 'POST'])
    @login_required
    def wohngruppe_bearbeiten(id):
        wohngruppe = db.get_wohngruppe(id)
        if not wohngruppe:
            flash('Wohngruppe nicht gefunden.', 'error')
            return redirect(url_for('pflegeheime_liste'))

        pflegeheim = db.get_pflegeheim(wohngruppe['pflegeheim_id'])

        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            if name:
                aenderungen = feld_diff(wohngruppe, {'name': name}, ['name'])
                db.update_wohngruppe(id, name)
                protokoll('GEAENDERT', 'wohngruppe', id, name, aenderungen)
                flash(f'Wohngruppe "{name}" wurde aktualisiert.', 'success')
                return redirect(url_for('wohngruppe_detail', id=id))
            flash('Bitte geben Sie einen Namen ein.', 'error')

        return render_template('wohngruppe_form.html',
                               pflegeheim=pflegeheim, wohngruppe=wohngruppe)

    @app.route('/wohngruppen/<int:id>/loeschen', methods=['POST'])
    @login_required
    def wohngruppe_loeschen(id):
        wohngruppe = db.get_wohngruppe(id)
        if wohngruppe:
            ph_id = wohngruppe['pflegeheim_id']
            protokoll('GELOESCHT', 'wohngruppe', id, wohngruppe['name'])
            db.delete_wohngruppe(id)
            flash(f'Wohngruppe "{wohngruppe["name"]}" wurde geloescht.', 'success')
            return redirect(url_for('pflegeheim_detail', id=ph_id))
        return redirect(url_for('pflegeheime_liste'))

    # ============================================================
    # Bewohner
    # ============================================================

    @app.route('/wohngruppen/<int:wg_id>/bewohner/neu', methods=['GET', 'POST'])
    @login_required
    def bewohner_neu(wg_id):
        wohngruppe = db.get_wohngruppe(wg_id)
        if not wohngruppe:
            flash('Wohngruppe nicht gefunden.', 'error')
            return redirect(url_for('pflegeheime_liste'))

        if request.method == 'POST':
            nachname = request.form.get('nachname', '').strip()
            vorname = request.form.get('vorname', '').strip()
            geburtsdatum = request.form.get('geburtsdatum', '').strip() or None

            if nachname and vorname:
                db.create_bewohner(wg_id, nachname, vorname, geburtsdatum)
                bew_list = db.get_bewohner_by_wohngruppe(wg_id)
                bew_id = bew_list[-1]['id'] if bew_list else None
                protokoll('ERSTELLT', 'bewohner', bew_id,
                          f'{nachname}, {vorname}')
                flash(f'Bewohner "{nachname}, {vorname}" wurde angelegt.', 'success')
                return redirect(url_for('wohngruppe_detail', id=wg_id))
            flash('Bitte geben Sie Nachname und Vorname ein.', 'error')

        return render_template('bewohner_form.html',
                               wohngruppe=wohngruppe, bewohner=None)

    @app.route('/bewohner/<int:id>')
    @login_required
    def bewohner_detail(id):
        bewohner = db.get_bewohner(id)
        if not bewohner:
            flash('Bewohner nicht gefunden.', 'error')
            return redirect(url_for('pflegeheime_liste'))

        impfungen = db.get_impfungen(id)
        alle_wohngruppen = db.get_alle_wohngruppen()
        bewohner_dokumente = db.get_dokumente_fuer_bewohner(id)

        # Dokument-Status pro Impfung ermitteln
        impfung_dokumente = {}
        for imp in impfungen:
            dok = db.get_dokument_fuer_impfung(imp['id'])
            if dok:
                impfung_dokumente[imp['id']] = dok

        return render_template('bewohner_detail.html',
                               bewohner=bewohner,
                               impfungen=impfungen,
                               alle_wohngruppen=alle_wohngruppen,
                               bewohner_dokumente=bewohner_dokumente,
                               impfung_dokumente=impfung_dokumente,
                               current_year=datetime.now().year)

    @app.route('/bewohner/<int:id>/bearbeiten', methods=['GET', 'POST'])
    @login_required
    def bewohner_bearbeiten(id):
        bewohner = db.get_bewohner(id)
        if not bewohner:
            flash('Bewohner nicht gefunden.', 'error')
            return redirect(url_for('pflegeheime_liste'))

        wohngruppe = db.get_wohngruppe(bewohner['wohngruppe_id'])

        if request.method == 'POST':
            nachname = request.form.get('nachname', '').strip()
            vorname = request.form.get('vorname', '').strip()
            geburtsdatum = request.form.get('geburtsdatum', '').strip() or None

            if nachname and vorname:
                aenderungen = feld_diff(bewohner,
                    {'nachname': nachname, 'vorname': vorname, 'geburtsdatum': geburtsdatum},
                    ['nachname', 'vorname', 'geburtsdatum'])
                db.update_bewohner(id, nachname, vorname, geburtsdatum)
                protokoll('GEAENDERT', 'bewohner', id,
                          f'{nachname}, {vorname}', aenderungen)
                flash(f'Bewohner wurde aktualisiert.', 'success')
                return redirect(url_for('bewohner_detail', id=id))
            flash('Bitte geben Sie Nachname und Vorname ein.', 'error')

        return render_template('bewohner_form.html',
                               wohngruppe=wohngruppe, bewohner=bewohner)

    @app.route('/bewohner/<int:id>/deaktivieren', methods=['POST'])
    @login_required
    def bewohner_deaktivieren(id):
        bewohner = db.get_bewohner(id)
        if bewohner:
            db.deaktiviere_bewohner(id)
            protokoll('ARCHIVIERT', 'bewohner', id,
                      f'{bewohner["nachname"]}, {bewohner["vorname"]}')
            flash(f'Bewohner "{bewohner["nachname"]}, {bewohner["vorname"]}" '
                  f'wurde deaktiviert.', 'info')
            return redirect(url_for('wohngruppe_detail',
                                    id=bewohner['wohngruppe_id']))
        return redirect(url_for('pflegeheime_liste'))

    @app.route('/bewohner/<int:id>/aktivieren', methods=['POST'])
    @login_required
    def bewohner_aktivieren(id):
        bewohner = db.get_bewohner(id)
        if bewohner:
            db.aktiviere_bewohner(id)
            protokoll('WIEDERHERGESTELLT', 'bewohner', id,
                      f'{bewohner["nachname"]}, {bewohner["vorname"]}')
            flash(f'Bewohner "{bewohner["nachname"]}, {bewohner["vorname"]}" '
                  f'wurde reaktiviert.', 'success')
        return redirect(url_for('inaktive_bewohner'))

    @app.route('/bewohner/<int:id>/loeschen', methods=['POST'])
    @login_required
    def bewohner_loeschen(id):
        bewohner = db.get_bewohner(id)
        if bewohner:
            protokoll('GELOESCHT', 'bewohner', id,
                      f'{bewohner["nachname"]}, {bewohner["vorname"]}')
            db.delete_bewohner(id)
            flash(f'Bewohner "{bewohner["nachname"]}, {bewohner["vorname"]}" '
                  f'wurde endgueltig geloescht.', 'success')
        return redirect(url_for('inaktive_bewohner'))

    @app.route('/bewohner/<int:id>/umziehen', methods=['POST'])
    @login_required
    def bewohner_umziehen(id):
        neue_wg_id = request.form.get('neue_wohngruppe_id', type=int)
        if neue_wg_id:
            bewohner = db.get_bewohner(id)
            alte_wg = db.get_wohngruppe(bewohner['wohngruppe_id']) if bewohner else None
            neue_wg = db.get_wohngruppe(neue_wg_id)
            db.umziehen_bewohner(id, neue_wg_id)
            if bewohner:
                aenderungen = {'wohngruppe': {
                    'alt': alte_wg['name'] if alte_wg else None,
                    'neu': neue_wg['name'] if neue_wg else None
                }}
                protokoll('GEAENDERT', 'bewohner', id,
                          f'{bewohner["nachname"]}, {bewohner["vorname"]}',
                          aenderungen)
            flash('Bewohner wurde umgezogen.', 'success')
        return redirect(url_for('bewohner_detail', id=id))

    @app.route('/bewohner/inaktive')
    @login_required
    def inaktive_bewohner():
        bewohner = db.get_inaktive_bewohner()
        return render_template('inaktive_bewohner.html', bewohner=bewohner)

    # ============================================================
    # Impfungen
    # ============================================================

    STANDARD_IMPFUNGEN = [
        {'name': 'Grippe (Influenza)', 'intervall': 1},
        {'name': 'Corona (COVID-19)', 'intervall': 1},
    ]

    @app.route('/bewohner/<int:b_id>/impfung/neu', methods=['GET', 'POST'])
    @login_required
    def impfung_neu(b_id):
        bewohner = db.get_bewohner(b_id)
        if not bewohner:
            flash('Bewohner nicht gefunden.', 'error')
            return redirect(url_for('pflegeheime_liste'))

        if request.method == 'POST':
            impftyp_auswahl = request.form.get('impftyp_auswahl', '')
            impftyp_freitext = request.form.get('impftyp_freitext', '').strip()

            if impftyp_auswahl == 'freitext':
                impftyp = impftyp_freitext
                ist_standard = False
                intervall = request.form.get('intervall', type=int)
            else:
                # Standard-Impfung
                impftyp = impftyp_auswahl
                ist_standard = True
                # Intervall aus Standard-Liste
                intervall = next(
                    (s['intervall'] for s in STANDARD_IMPFUNGEN
                     if s['name'] == impftyp), None
                )

            if impftyp:
                db.create_impfung(b_id, impftyp, ist_standard, intervall)
                imps = db.get_impfungen(b_id)
                imp_id = imps[-1]['id'] if imps else None
                protokoll('ERSTELLT', 'impfung', imp_id,
                          f'{impftyp} ({bewohner["nachname"]}, {bewohner["vorname"]})')
                flash(f'Impfung "{impftyp}" wurde angelegt.', 'success')
                return redirect(url_for('bewohner_detail', id=b_id))
            flash('Bitte waehlen Sie eine Impfung aus oder geben Sie eine ein.',
                  'error')

        return render_template('impfung_form.html',
                               bewohner=bewohner,
                               standard_impfungen=STANDARD_IMPFUNGEN,
                               impfung=None)

    @app.route('/impfung/<int:id>/bearbeiten', methods=['GET', 'POST'])
    @login_required
    def impfung_bearbeiten(id):
        impfung = db.get_impfung(id)
        if not impfung:
            flash('Impfung nicht gefunden.', 'error')
            return redirect(url_for('pflegeheime_liste'))

        bewohner = db.get_bewohner(impfung['bewohner_id'])

        if request.method == 'POST':
            updates = {}

            # Einverstaendnis
            einverstaendnis = request.form.get('einverstaendnis_status', '')
            if einverstaendnis:
                updates['einverstaendnis_status'] = einverstaendnis
            # Einverstaendnis-Jahr (aus Formularfeld oder automatisch)
            ev_jahr = request.form.get('einverstaendnis_jahr', '').strip()
            if ev_jahr:
                updates['einverstaendnis_jahr'] = int(ev_jahr)
            elif einverstaendnis in ('JA_JAEHRLICH', 'JA_JAEHRLICH_NACHFRAGEN',
                                     'NEIN_JAEHRLICH_NACHFRAGEN', 'JA', 'NEIN'):
                updates['einverstaendnis_jahr'] = datetime.now().year

            # Status
            status = request.form.get('status', '')
            if status:
                updates['status'] = status

            # Plan-Datum
            plan_datum = request.form.get('plan_datum', '').strip() or None
            updates['plan_datum'] = plan_datum
            if plan_datum and status != 'DURCHGEFUEHRT':
                updates['status'] = 'GEPLANT'

            # Durchfuehrung
            durchfuehrung_datum = request.form.get(
                'durchfuehrung_datum', ''
            ).strip() or None
            if durchfuehrung_datum:
                updates['durchfuehrung_datum'] = durchfuehrung_datum
                updates['status'] = 'DURCHGEFUEHRT'

                # Naechste Faelligkeit berechnen
                intervall = request.form.get(
                    'wiederholung_intervall_jahre', type=int
                )
                if intervall:
                    updates['wiederholung_intervall_jahre'] = intervall
                    d = datetime.strptime(durchfuehrung_datum, '%Y-%m-%d')
                    # Grippe: Naechste Faelligkeit ist 1. September
                    if 'Grippe' in impfung['impftyp']:
                        naechstes_jahr = d.year + 1
                        naechste = datetime(naechstes_jahr, 9, 1)
                    else:
                        naechste = d.replace(year=d.year + intervall)
                    updates['naechste_faelligkeit'] = naechste.strftime(
                        '%Y-%m-%d'
                    )

            # Protokoll: Aenderungen ermitteln
            imp_aenderungen = feld_diff(impfung, updates,
                [k for k in updates.keys() if k in (
                    'einverstaendnis_status', 'einverstaendnis_jahr',
                    'status', 'plan_datum', 'durchfuehrung_datum',
                    'wiederholung_intervall_jahre', 'naechste_faelligkeit'
                )])
            db.update_impfung(id, **updates)
            protokoll('GEAENDERT', 'impfung', id,
                      f'{impfung["impftyp"]} ({impfung["nachname"]}, {impfung["vorname"]})',
                      imp_aenderungen)

            # Warnung bei NEIN + Planung/Durchfuehrung
            ev_status = updates.get('einverstaendnis_status',
                                    impfung['einverstaendnis_status'])
            hat_plan = updates.get('plan_datum') or impfung['plan_datum']
            hat_durchfuehrung = updates.get('durchfuehrung_datum') or \
                impfung['durchfuehrung_datum']
            if ev_status in ('NEIN', 'NEIN_JAEHRLICH_NACHFRAGEN'):
                if hat_durchfuehrung:
                    flash('ACHTUNG: Diese Impfung wurde ENTGEGEN der '
                          'Einverstaendniserklaerung durchgefuehrt! '
                          'Bitte dokumentieren Sie den Grund.', 'error')
                elif hat_plan:
                    flash('Hinweis: Fuer diese Impfung liegt kein '
                          'Einverstaendnis vor. Bitte klaeren Sie '
                          'die Zustimmung vor der Durchfuehrung.', 'error')
            else:
                flash('Impfung wurde aktualisiert.', 'success')
            return redirect(url_for('bewohner_detail',
                                    id=impfung['bewohner_id']))

        dokument = db.get_dokument_fuer_impfung(id) if impfung else None
        return render_template('impfung_form.html',
                               bewohner=bewohner,
                               standard_impfungen=STANDARD_IMPFUNGEN,
                               impfung=impfung,
                               dokument=dokument)

    @app.route('/impfung/<int:id>/loeschen', methods=['POST'])
    @login_required
    def impfung_loeschen(id):
        impfung = db.get_impfung(id)
        if impfung:
            bewohner_id = impfung['bewohner_id']
            protokoll('GELOESCHT', 'impfung', id,
                      f'{impfung["impftyp"]} ({impfung["nachname"]}, {impfung["vorname"]})')
            db.delete_impfung(id)
            flash('Impfung wurde geloescht.', 'success')
            return redirect(url_for('bewohner_detail', id=bewohner_id))
        return redirect(url_for('pflegeheime_liste'))

    # ============================================================
    # Dokumente (verschluesselte PDF-Uploads)
    # ============================================================

    @app.route('/dokument/upload', methods=['POST'])
    @login_required
    def dokument_upload():
        if 'datei' not in request.files:
            flash('Keine Datei ausgewaehlt.', 'error')
            return redirect(request.referrer or url_for('pflegeheime_liste'))

        datei = request.files['datei']
        if datei.filename == '' or not datei.filename.lower().endswith('.pdf'):
            flash('Nur PDF-Dateien sind erlaubt.', 'error')
            return redirect(request.referrer or url_for('pflegeheime_liste'))

        bewohner_id = request.form.get('bewohner_id', type=int)
        impfung_id = request.form.get('impfung_id', type=int) or None

        if not bewohner_id:
            flash('Bewohner nicht gefunden.', 'error')
            return redirect(url_for('pflegeheime_liste'))

        # Bei Impfung-Dokument: altes Dokument ersetzen
        if impfung_id:
            altes_dok = db.get_dokument_fuer_impfung(impfung_id)
            if altes_dok:
                db.delete_dokument(altes_dok['id'])

        daten = datei.read()
        db.save_dokument(bewohner_id, datei.filename, daten, impfung_id)
        bew = db.get_bewohner(bewohner_id)
        protokoll('ERSTELLT', 'dokument', None,
                  f'{datei.filename} ({bew["nachname"]}, {bew["vorname"]})'
                  if bew else datei.filename)
        flash('Dokument wurde hochgeladen.', 'success')
        return redirect(url_for('bewohner_detail', id=bewohner_id))

    @app.route('/dokument/<int:id>/download')
    @login_required
    def dokument_download(id):
        dok = db.get_dokument(id)
        if not dok:
            flash('Dokument nicht gefunden.', 'error')
            return redirect(url_for('pflegeheime_liste'))

        return send_file(
            BytesIO(dok['daten']),
            mimetype='application/pdf',
            as_attachment=False,
            download_name=dok['dateiname']
        )

    @app.route('/dokument/<int:id>/loeschen', methods=['POST'])
    @login_required
    def dokument_loeschen(id):
        dok = db.get_dokument(id)
        if dok:
            bew = db.get_bewohner(dok['bewohner_id'])
            protokoll('GELOESCHT', 'dokument', id,
                      f'{dok["dateiname"]} ({bew["nachname"]}, {bew["vorname"]})'
                      if bew else dok['dateiname'])
            db.delete_dokument(id)
            flash('Dokument wurde geloescht.', 'success')
            return redirect(url_for('bewohner_detail', id=dok['bewohner_id']))
        return redirect(url_for('pflegeheime_liste'))

    # ============================================================
    # Export
    # ============================================================

    @app.route('/export/pdf/<int:ph_id>')
    @login_required
    def export_pdf(ph_id):
        from export import generate_pdf
        data = db.get_export_data(ph_id)
        if not data:
            flash('Pflegeheim nicht gefunden.', 'error')
            return redirect(url_for('pflegeheime_liste'))

        pdf_path = generate_pdf(data)
        return send_file(pdf_path, as_attachment=True,
                         download_name=f'impfplan_{data["pflegeheim"]["name"]}.pdf')

    @app.route('/export/txt/<int:ph_id>')
    @login_required
    def export_txt(ph_id):
        from export import generate_txt
        data = db.get_export_data(ph_id)
        if not data:
            flash('Pflegeheim nicht gefunden.', 'error')
            return redirect(url_for('pflegeheime_liste'))

        txt_path = generate_txt(data)
        return send_file(txt_path, as_attachment=True,
                         download_name=f'impfplan_{data["pflegeheim"]["name"]}.txt')

    # ============================================================
    # Admin
    # ============================================================

    @app.route('/admin/nutzer')
    @admin_required
    def admin_nutzer():
        users = db.get_all_users()
        return render_template('admin_nutzer.html', users=users)

    @app.route('/admin/nutzer/neu', methods=['GET', 'POST'])
    @admin_required
    def admin_nutzer_neu():
        if request.method == 'POST':
            benutzername = request.form.get('benutzername', '').strip()
            passwort = request.form.get('passwort', '')
            rolle = request.form.get('rolle', 'nutzer')

            if benutzername and passwort:
                existing = db.get_user_by_name(benutzername)
                if existing:
                    flash('Benutzername existiert bereits.', 'error')
                else:
                    pw_hash = bcrypt.generate_password_hash(
                        passwort
                    ).decode('utf-8')
                    db.create_user(benutzername, pw_hash, rolle)
                    protokoll('ERSTELLT', 'benutzer', None,
                              f'{benutzername} ({rolle})')
                    flash(f'Benutzer "{benutzername}" wurde angelegt.', 'success')
                    return redirect(url_for('admin_nutzer'))
            else:
                flash('Bitte alle Felder ausfuellen.', 'error')

        return render_template('admin_nutzer_form.html')

    @app.route('/admin/nutzer/<int:id>/loeschen', methods=['POST'])
    @admin_required
    def admin_nutzer_loeschen(id):
        if id == current_user.id:
            flash('Sie koennen sich nicht selbst loeschen.', 'error')
        else:
            user = db.get_user_by_id(id)
            protokoll('GELOESCHT', 'benutzer', id,
                      user['benutzername'] if user else str(id))
            db.delete_user(id)
            flash('Benutzer wurde geloescht.', 'success')
        return redirect(url_for('admin_nutzer'))

    @app.route('/admin/protokoll')
    @admin_required
    def admin_protokoll():
        # Filter aus Query-Parametern
        entitaet_typ = request.args.get('entitaet_typ', '')
        benutzer_id = request.args.get('benutzer_id', type=int)
        datum_von = request.args.get('datum_von', '')
        datum_bis = request.args.get('datum_bis', '')
        seite = request.args.get('seite', 1, type=int)
        pro_seite = 50

        total = db.count_protokoll(
            entitaet_typ=entitaet_typ or None,
            benutzer_id=benutzer_id,
            datum_von=datum_von or None,
            datum_bis=datum_bis or None
        )
        eintraege = db.get_protokoll(
            entitaet_typ=entitaet_typ or None,
            benutzer_id=benutzer_id,
            datum_von=datum_von or None,
            datum_bis=datum_bis or None,
            limit=pro_seite,
            offset=(seite - 1) * pro_seite
        )
        seiten_gesamt = (total + pro_seite - 1) // pro_seite if total > 0 else 1
        users = db.get_all_users()

        return render_template('admin_protokoll.html',
                               eintraege=eintraege,
                               total=total,
                               seite=seite,
                               seiten_gesamt=seiten_gesamt,
                               users=users,
                               filter_entitaet=entitaet_typ,
                               filter_benutzer=benutzer_id,
                               filter_von=datum_von,
                               filter_bis=datum_bis)

    @app.route('/admin/backup')
    @admin_required
    def admin_backup():
        db_path = app.config['DB_PATH']
        if os.path.exists(db_path):
            backup_name = f'pieksplan_backup_{date.today().isoformat()}.db'
            backup_path = os.path.join(
                get_base_dir(), '.tmp', backup_name
            )
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            shutil.copy2(db_path, backup_path)
            return send_file(backup_path, as_attachment=True,
                             download_name=backup_name)
        flash('Datenbankdatei nicht gefunden.', 'error')
        return redirect(url_for('dashboard'))

    @app.route('/admin/backup/import', methods=['GET', 'POST'])
    @admin_required
    def admin_backup_import():
        if request.method == 'POST':
            if 'backup_file' not in request.files:
                flash('Keine Datei ausgewaehlt.', 'error')
                return redirect(url_for('admin_backup_import'))

            file = request.files['backup_file']
            if file.filename == '':
                flash('Keine Datei ausgewaehlt.', 'error')
                return redirect(url_for('admin_backup_import'))

            if not file.filename.endswith('.db'):
                flash('Nur .db Dateien sind erlaubt.', 'error')
                return redirect(url_for('admin_backup_import'))

            # Aktuelle DB sichern
            db_path = app.config['DB_PATH']
            if os.path.exists(db_path):
                sicherung = db_path + '.vor_import'
                shutil.copy2(db_path, sicherung)

            # DB-Verbindung schliessen
            db.close_db()

            # Neue DB speichern
            try:
                file.save(db_path)
                # Testen ob die DB gueltig ist
                test_conn = sqlcipher3.connect(db_path)
                test_conn.execute(
                    f"PRAGMA key='{app.config['DB_ENCRYPTION_KEY']}'"
                )
                test_conn.execute('SELECT COUNT(*) FROM users')
                test_conn.close()
                flash('Backup erfolgreich importiert! '
                      'Die alte Datenbank wurde als Sicherung aufbewahrt.',
                      'success')
            except Exception as e:
                # Bei Fehler: Alte DB wiederherstellen
                if os.path.exists(db_path + '.vor_import'):
                    shutil.copy2(db_path + '.vor_import', db_path)
                flash(f'Import fehlgeschlagen: {str(e)}. '
                      'Die alte Datenbank wurde wiederhergestellt.', 'error')

            return redirect(url_for('dashboard'))

        return render_template('admin_backup_import.html')

    # ============================================================
    # Rechtliches
    # ============================================================

    @app.route('/rechtliches')
    def rechtliches():
        return render_template('rechtliches.html')

    return app


# ============================================================
# Startpunkt
# ============================================================

app = create_app()

if __name__ == '__main__':
    import waitress
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5555))
    print(f'PieksPlan laeuft auf http://{host}:{port}')
    waitress.serve(app, host=host, port=port)
