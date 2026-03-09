"""
VisiCore Launcher
Startet den Server und oeffnet automatisch den Browser.
Erstellt beim ersten Start automatisch alle benoetigten Dateien.
Wird mit PyInstaller zur .exe kompiliert.
"""

import os
import sys
import secrets
import threading
import webbrowser
import time


def get_base_dir():
    """Gibt das Basisverzeichnis zurueck - funktioniert als .py und als .exe."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def ensure_setup(base_dir):
    """Erstellt alle benoetigten Dateien und Ordner beim ersten Start."""
    first_run = False

    # data/ Ordner erstellen
    data_dir = os.path.join(base_dir, 'data')
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        first_run = True

    # .env erstellen mit sicheren Zufallsschluesseln
    env_path = os.path.join(base_dir, '.env')
    if not os.path.exists(env_path):
        db_key = secrets.token_hex(32)
        secret_key = secrets.token_hex(32)
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write('# VisiCore Konfiguration (automatisch erstellt)\n')
            f.write(f'DB_KEY={db_key}\n')
            f.write(f'SECRET_KEY={secret_key}\n')
            f.write('PORT=5001\n')
            f.write('PRAXIS_STADT=Wuerzburg\n')
        first_run = True

    return first_run


def main():
    base_dir = get_base_dir()
    os.chdir(base_dir)

    print()
    print('  =============================')
    print('         VisiCore')
    print('  =============================')
    print()

    # Ersteinrichtung
    first_run = ensure_setup(base_dir)
    if first_run:
        print('  Ersteinrichtung abgeschlossen!')
        print('  Konfiguration: .env')
        print('  Datenbank:     data/visicore.db')
        print()

    # .env laden
    from dotenv import load_dotenv
    load_dotenv(os.path.join(base_dir, '.env'))

    port = int(os.environ.get('PORT', 5001))
    url = f'http://localhost:{port}'

    # App importieren und erstellen
    from app import create_app
    app = create_app()

    # Browser nach kurzer Verzoegerung oeffnen
    def open_browser():
        time.sleep(1.5)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()

    # Waitress-Server starten (Produktion)
    from waitress import serve

    print(f'  Server laeuft: {url}')
    print()
    if first_run:
        print('  +-----------------------------+')
        print('  |  Erster Login:               |')
        print('  |  Benutzer: admin             |')
        print('  |  Passwort: admin             |')
        print('  |  Bitte sofort aendern!       |')
        print('  +-----------------------------+')
        print()
    print('  Dieses Fenster offen lassen,')
    print('  solange VisiCore benutzt wird.')
    print()

    serve(app, host='0.0.0.0', port=port, threads=4)


if __name__ == '__main__':
    main()
