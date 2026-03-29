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


def get_local_ips():
    """Ermittelt lokale Netzwerk-IPs fuer die Anzeige."""
    ips = []
    import socket
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith('127.'):
                ips.append(ip)
    except Exception:
        pass
    return list(set(ips)) or ['(nicht ermittelt)']


def main():
    base_dir = get_base_dir()
    os.chdir(base_dir)

    print()
    print('  =============================')
    print('         VisiCore')
    print('  =============================')
    print()

    try:
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
        # TLS-Zertifikat sicherstellen
        from tls import ensure_certificate
        data_dir = os.path.join(base_dir, 'data')
        cert_path, key_path = ensure_certificate(data_dir)

        url = f'https://localhost:{port}'

        # App importieren und erstellen
        from app import create_app
        app = create_app()

        # Browser nach kurzer Verzoegerung oeffnen
        def open_browser():
            time.sleep(2.0)
            webbrowser.open(url)

        threading.Thread(target=open_browser, daemon=True).start()

        ips = get_local_ips()
        print(f'  Server laeuft: {url}')
        for ip in ips:
            print(f'  Im Netzwerk:   https://{ip}:{port}')
        print()
        print('  WICHTIG: Immer https:// verwenden (nicht http://)')
        print()
        if first_run:
            print('  +-------------------------------+')
            print('  |  Erster Login:                 |')
            print('  |  Benutzer: admin               |')
            print('  |  Passwort: admin               |')
            print('  |  (Passwortwechsel erforderlich) |')
            print('  +-------------------------------+')
            print()
        print('  Dieses Fenster offen lassen,')
        print('  solange VisiCore benutzt wird.')
        print()

        # HTTP→HTTPS Redirect-Server starten (gleicher Port ohne TLS)
        # Faengt Nutzer ab, die http:// statt https:// eingeben
        from flask import Flask as _Flask, redirect as _redirect, request as _request
        redirect_app = _Flask('redirect')

        @redirect_app.route('/', defaults={'path': ''})
        @redirect_app.route('/<path:path>')
        def _http_redirect(path):
            host = _request.host.split(':')[0]
            return _redirect(f'https://{host}:{port}/{path}', code=301)

        def run_http_redirect(http_port):
            try:
                from werkzeug.serving import run_simple as _run
                _run('0.0.0.0', http_port, redirect_app,
                     threaded=True, use_reloader=False)
            except Exception:
                pass  # Port nicht verfuegbar – kein Problem

        # Port 80 und Port 5000 (port-1) als Redirect
        for hp in [80, port - 1]:
            if hp > 0 and hp != port:
                threading.Thread(target=run_http_redirect, args=(hp,),
                                 daemon=True).start()

        # HTTPS-Server starten (werkzeug mit TLS)
        from werkzeug.serving import run_simple
        run_simple('0.0.0.0', port, app,
                   ssl_context=(cert_path, key_path),
                   threaded=True,
                   use_reloader=False)

    except Exception as e:
        print()
        print('  !!  FEHLER  !!')
        print(f'  {e}')
        print()
        input('  Druecken Sie Enter zum Beenden...')
        sys.exit(1)


if __name__ == '__main__':
    main()
