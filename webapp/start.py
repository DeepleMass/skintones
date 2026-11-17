#!/usr/bin/env python3
"""
start.py — Start-Skript: Projekt im Webbrowser öffnen.

Ablauf:
    1. Flask-Server (flask_app/app.py) als Subprozess starten.
    2. Poll auf /api/health, bis der Server antwortet (max. ~10 s).
    3. Standard-Browser per webbrowser.open() auf http://127.0.0.1:<port>/ öffnen.
    4. Warten, bis der User Strg+C drückt, dann Server sauber beenden.

Aufruf (aus dem webapp/-Verzeichnis):
    python3 start.py                 # Port 5824, Browser öffnet automatisch
    python3 start.py --port 8080     # anderer Port
    python3 start.py --no-browser    # nur Server, kein Browser öffnen

Voraussetzung: Flask installiert (pip install -r flask_app/requirements.txt).
Hinweis Webcam: getUserMedia braucht einen "secure context" —
http://127.0.0.1 und http://localhost gelten als sicher, daher klappt die
Webcam ohne HTTPS.
"""

import argparse
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # webapp/
HOST = "127.0.0.1"


def wait_for_health(port: int, timeout_s: float = 10.0) -> bool:
    """Pollt /api/health, bis der Server antwortet. True bei Erfolg."""
    url = f"http://{HOST}:{port}/api/health"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except OSError:
            time.sleep(0.2)  # Server startet noch -> weiter warten
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Skintone-Web-App starten und im Browser öffnen")
    parser.add_argument("--port", type=int, default=5824, help="Port des Flask-Servers (Default: 5824)")
    parser.add_argument("--no-browser", action="store_true", help="Server starten, aber keinen Browser öffnen")
    args = parser.parse_args()

    url = f"http://{HOST}:{args.port}/"

    # 1) Flask als Subprozess starten (nicht debug, damit kein Reloader-Workaround nötig)
    cmd = [
        sys.executable, "-m", "flask",
        "--app", "flask_app.app:app",
        "run", "--host", HOST, "--port", str(args.port),
    ]
    print(f"[start] Flask starten: {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(cmd, cwd=ROOT)
    except FileNotFoundError:
        print("[start] FEHLER: Flask nicht installiert. Bitte: pip install -r flask_app/requirements.txt")
        return 1

    # 2) Warten, bis der Server erreichbar ist
    print(f"[start] Warte auf {url}api/health ...")
    if not wait_for_health(args.port):
        print("[start] FEHLER: Server antwortet nicht — siehe Flask-Ausgabe oben.")
        proc.terminate()
        return 1
    print(f"[start] Server läuft: {url}")

    # 3) Browser öffnen
    if not args.no_browser:
        print(f"[start] Browser öffnen: {url}")
        webbrowser.open(url)
    else:
        print(f"[start] --no-browser gesetzt, Browser wird nicht geöffnet. URL: {url}")

    # 4) Laufen lassen, bis Strg+C; dann Subprozess sauber beenden
    print("[start] Läuft. Beenden mit Strg+C.")
    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n[start] Strg+C — Server wird beendet.")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    print("[start] Fertig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
