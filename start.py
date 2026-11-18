#!/usr/bin/env python3
"""
start.py — Start-Skript: Projekt im Webbrowser öffnen.

Lliegt im Repo-Root (neben webapp/). Ablauf:
    1. webapp/-Verzeichnis finden (Repo-Root -> ./webapp, Fallback: Skript
       liegt selbst in webapp/).
    2. Flask-Server (webapp/flask_app/app.py) als Subprozess starten.
    3. Poll auf /api/health, bis der Server antwortet (max. ~10 s).
    4. Standard-Browser per webbrowser.open() auf http://127.0.0.1:<port>/ öffnen.
    5. Warten, bis der User Strg+C drückt, dann Server sauber beenden.

Aufruf (aus dem Repo-Root):
    python3 start.py                 # Port 5824, Browser öffnet automatisch
    ./start.sh                       # dasselbe als Shell-Wrapper
    python3 start.py --port 8080     # anderer Port
    python3 start.py --no-browser    # nur Server, kein Browser öffnen

Logging: Start/Stop, Health-Poll und Fehler landen in <Repo-Root>/webapplogs/
(launcher.log + app.log — alle Komponenten fortlaufend in einer Datei;
tägliche Rotation; für Tests umschaltbar über SKINTONE_LOG_DIR).

Voraussetzung: Flask installiert (pip install -r webapp/flask_app/requirements.txt).
Hinweis Webcam: getUserMedia braucht einen "secure context" —
http://127.0.0.1 und http://localhost gelten als sicher, daher klappt die
Webcam ohne HTTPS.
"""

import argparse
import logging
import logging.handlers
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"

# Skript-Verzeichnis; webapp/ liegt normalerweise daneben (Repo-Root).
SCRIPT_DIR = Path(__file__).resolve().parent
if (SCRIPT_DIR / "webapp" / "index.html").is_file():
    WEBAPP_DIR = SCRIPT_DIR / "webapp"
elif (SCRIPT_DIR / "index.html").is_file():
    WEBAPP_DIR = SCRIPT_DIR  # Fallback: Skript liegt direkt in webapp/
else:
    raise SystemExit(
        f"[start] FEHLER: webapp/index.html nicht gefunden (gesucht ab {SCRIPT_DIR})."
    )

# Log-Verzeichnis: webapplogs/ im Repo-Root (für Tests umschaltbar per Env-Variable)
LOG_DIR = Path(os.environ.get("SKINTONE_LOG_DIR") or (SCRIPT_DIR / "webapplogs"))

LOG_FORMAT = "%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)s | %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> logging.Logger:
    """Logger 'skintone.launcher': launcher.log (täglich rotiert) + Konsole."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("skintone.launcher")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    for h in list(log.handlers):
        log.removeHandler(h)
        h.close()
    file_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_DIR / "launcher.log", when="midnight", backupCount=14, encoding="utf-8",
    )
    fmt = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)
    file_handler.setFormatter(fmt)
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(fmt)
    app_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_DIR / "app.log", when="midnight", backupCount=14, encoding="utf-8",
    )  # kombinierte Datei: alle Komponenten schreiben fortlaufend hier hinein
    app_handler.setFormatter(fmt)
    log.addHandler(file_handler)
    log.addHandler(app_handler)
    log.addHandler(stream)
    return log


log = setup_logging()


def wait_for_health(port: int, timeout_s: float = 10.0) -> bool:
    """Pollt /api/health, bis der Server antwortet. True bei Erfolg."""
    url = f"http://{HOST}:{port}/api/health"
    log.info("Health-Poll gestartet: %s (Timeout %.0f s)", url, timeout_s)
    deadline = time.time() + timeout_s
    attempts = 0
    while time.time() < deadline:
        attempts += 1
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                body = resp.read(200).decode("utf-8", "replace")
                if resp.status == 200:
                    log.info("Health-Poll OK nach %d Versuch(en): %s -> %s", attempts, url, body)
                    return True
                log.debug("Health-Poll: unerwarteter Status %s", resp.status)
        except OSError as err:
            log.debug("Health-Poll Versuch %d: %s", attempts, err)
            time.sleep(0.2)  # Server startet noch -> weiter warten
    log.error("Health-Poll FEHLGESCHLAGEN nach %d Versuchen: %s antwortet nicht", attempts, url)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Skintone-Web-App starten und im Browser öffnen")
    parser.add_argument("--port", type=int, default=5824, help="Port des Flask-Servers (Default: 5824)")
    parser.add_argument("--no-browser", action="store_true", help="Server starten, aber keinen Browser öffnen")
    args = parser.parse_args()

    url = f"http://{HOST}:{args.port}/"

    log.info("start.py aufgerufen: port=%d no_browser=%s python=%s log_dir=%s",
             args.port, args.no_browser, sys.executable, LOG_DIR)
    log.info("Webapp-Verzeichnis: %s", WEBAPP_DIR)

    # 1) Flask als Subprozess starten (cwd = webapp/, damit das App-Modul
    #    flask_app.app:app aufgelöst wird; nicht debug, damit kein
    #    Reloader-Workaround nötig ist)
    cmd = [
        sys.executable, "-m", "flask",
        "--app", "flask_app.app:app",
        "run", "--host", HOST, "--port", str(args.port),
    ]
    print(f"[start] Webapp-Verzeichnis: {WEBAPP_DIR}")
    print(f"[start] Flask starten: {' '.join(cmd)} (cwd={WEBAPP_DIR})")
    log.info("Flask-Kommando: %s (cwd=%s)", " ".join(cmd), WEBAPP_DIR)
    try:
        proc = subprocess.Popen(cmd, cwd=WEBAPP_DIR)
    except FileNotFoundError:
        req = WEBAPP_DIR / "flask_app" / "requirements.txt"
        log.error("Flask nicht installiert (FileNotFoundError). Bitte: pip install -r %s", req)
        print(f"[start] FEHLER: Flask nicht installiert. Bitte: pip install -r {req}")
        return 1
    log.info("Flask-Subprozess gestartet: pid=%d", proc.pid)

    # 2) Warten, bis der Server erreichbar ist
    print(f"[start] Warte auf {url}api/health ...")
    if not wait_for_health(args.port):
        log.error("Server antwortet nicht auf /api/health — Subprozess pid=%d wird beendet", proc.pid)
        print("[start] FEHLER: Server antwortet nicht — siehe Flask-Ausgabe oben.")
        proc.terminate()
        return 1
    print(f"[start] Server läuft: {url}")
    log.info("Server läuft: %s (pid=%d)", url, proc.pid)

    # 3) Browser öffnen
    if not args.no_browser:
        print(f"[start] Browser öffnen: {url}")
        opened = webbrowser.open(url)
        log.info("Browser öffnen: %s -> %s", url, opened)
    else:
        print(f"[start] --no-browser gesetzt, Browser wird nicht geöffnet. URL: {url}")
        log.info("--no-browser gesetzt, Browser bleibt geschlossen. URL: %s", url)

    # 4) Laufen lassen, bis Strg+C; dann Subprozess sauber beenden
    print("[start] Läuft. Beenden mit Strg+C.")
    log.info("Warte auf Subprozess pid=%d (Strg+C zum Beenden)", proc.pid)
    try:
        proc.wait()
        log.info("Subprozess pid=%d endete von selbst mit Code %s", proc.pid, proc.returncode)
    except KeyboardInterrupt:
        print("\n[start] Strg+C — Server wird beendet.")
        log.info("Strg+C empfangen — Server wird beendet (pid=%d)", proc.pid)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
            log.info("Subprozess pid=%d sauber beendet (terminate)", proc.pid)
        except subprocess.TimeoutExpired:
            proc.kill()
            log.warning("Subprozess pid=%d musste gekillt werden (terminate reichte nicht)", proc.pid)
    print("[start] Fertig.")
    log.info("start.py fertig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
