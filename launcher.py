"""
VisiCore Launcher
Startet den Server und oeffnet automatisch den Browser.
Wird mit PyInstaller zur .exe kompiliert.
"""

import os
import sys
import threading
import webbrowser
import time


def get_base_dir():
    """Gibt das Basisverzeichnis zurueck - funktioniert als .py und als .exe."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def main():
    base_dir = get_base_dir()
    os.chdir(base_dir)

    # .env laden
    from dotenv import load_dotenv
    dotenv_path = os.path.join(base_dir, '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)

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

    print()
    print('  =============================')
    print('   VisiCore laeuft!')
    print(f'   {url}')
    print('  =============================')
    print()
    print('  Fenster offen lassen, solange')
    print('  VisiCore benutzt wird.')
    print()

    serve(app, host='0.0.0.0', port=port, threads=4)


if __name__ == '__main__':
    main()
