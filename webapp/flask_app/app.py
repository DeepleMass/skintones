"""
app.py — Flask-Server für die Skintone-Web-App.

Aufgabe: Die reine JavaScript-App (index.html + src/) wird statisch
ausgeliefert, damit sie im Browser läuft. Es gibt keine serverseitige
Bildverarbeitung — die Pipeline läuft komplett im Browser (Canvas).

Logging: Alle Komponenten schreiben nach <Repo-Root>/webapplogs/
(übersteuerbar über Umgebungsvariable SKINTONE_LOG_DIR):
    app.log      — ALLE Logs fortlaufend in einer Datei (Kombination aus allem)
    server.log   — dieser Flask-Server: Requests, Antworten, Fehler (mit Stacktrace)
    browser.log  — Frontend-Logs, die der Browser per POST /api/log schickt
                   (inkl. window.onerror / unhandledrejection mit Stacktrace)
Tägliche Rotation (TimedRotatingFileHandler, 14 Backups) + Konsolen-Ausgabe.

Start (Varianten):
    python3 flask_app/app.py                 # direkt, Port 5824
    flask --app flask_app/app run --port 5824 # über die Flask-CLI
    python3 ../start.py                       # aus webapp/ (Repo-Root: python3 start.py)
    python3 ../server_gui.py                  # tkinter-GUI im Repo-Root

Getestet mit: python3 -m unittest flask_app.test_app        (aus webapp/)
           oder: python3 -m unittest skintones.webapp.flask_app.test_app  (vom Repo-Elternordner)
"""

import json
import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory

# Projekt-Root = das Verzeichnis, in dem index.html liegt (ein Ebene höher)
WEBAPP_ROOT = Path(__file__).resolve().parent.parent
# Repo-Root = eine Ebene über webapp/ (dort liegen start.py, server_gui.py, webapplogs/, images/)
REPO_ROOT = Path(__file__).resolve().parents[2]
# Default-/Beispielbilder liegen im Repo-Root unter images/ (z. B. default-image.jpg)
IMAGES_DIR = REPO_ROOT / "images"

# Log-Verzeichnis: webapplogs/ im Repo-Root, für Tests umschaltbar per Env-Variable
DEFAULT_LOG_DIR = REPO_ROOT / "webapplogs"

LOG_FORMAT = "%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)s | %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

SERVER_LOGGER_NAME = "skintone.server"
BROWSER_LOGGER_NAME = "webapp.browser"

# Erlaubte Log-Level für den Browser-Endpunkt
BROWSER_LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}


def get_log_dir() -> Path:
    """Aktuelles Log-Verzeichnis (Env SKINTONE_LOG_DIR schlägt den Default)."""
    return Path(os.environ.get("SKINTONE_LOG_DIR") or DEFAULT_LOG_DIR)


def _make_file_handler(log_dir: Path, filename: str) -> logging.Handler:
    """Tägliche Rotation, 14 Backups; legt das Log-Verzeichnis bei Bedarf an."""
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / filename, when="midnight", backupCount=14, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT))
    return handler


def setup_logging(log_dir: Path | None = None) -> tuple[logging.Logger, logging.Logger]:
    """
    Richtet Server- und Browser-Logger ein (idempotent: vorhandene Handler
    werden ersetzt, damit Tests das Log-Verzeichnis umschalten können).
    Liefert (server_logger, browser_logger).
    """
    log_dir = Path(log_dir) if log_dir else get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    server_log = logging.getLogger(SERVER_LOGGER_NAME)
    browser_log = logging.getLogger(BROWSER_LOGGER_NAME)
    for lg in (server_log, browser_log):
        lg.setLevel(logging.DEBUG)
        lg.propagate = False
        for h in list(lg.handlers):  # alte Handler entfernen (wichtig für Tests)
            lg.removeHandler(h)
            h.close()

    # app.log: ein Handler, von beiden Loggern geteilt -> eine fortlaufende Datei mit allem
    app_handler = _make_file_handler(log_dir, "app.log")
    server_log.addHandler(_make_file_handler(log_dir, "server.log"))
    server_log.addHandler(app_handler)
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT))
    server_log.addHandler(stream)

    browser_log.addHandler(_make_file_handler(log_dir, "browser.log"))
    browser_log.addHandler(app_handler)

    server_log.info("Logging initialisiert: log_dir=%s python=%s", log_dir, sys.version.split()[0])
    return server_log, browser_log


server_log, browser_log = setup_logging()

# static_folder auf das Webapp-Root legen und static_url_path leeren,
# damit "/" direkt index.html ausliefert und "/src/app.js" unter /src/ liegt.
app = Flask(__name__, static_folder=str(WEBAPP_ROOT), static_url_path="")

server_log.info("Flask-App geladen: webapp_root=%s", WEBAPP_ROOT)


@app.route("/")
def index():
    """Startseite: index.html aus dem Webapp-Root."""
    return send_from_directory(WEBAPP_ROOT, "index.html")


@app.route("/api/health")
def health():
    """Health-Check für das Start-Skript und Tests (JSON)."""
    return jsonify({"status": "ok", "app": "skintone-webapp"})


@app.route("/images/<path:filename>")
def images(filename):
    """Bilder aus <Repo-Root>/images/ ausliefern — z. B. /images/default-image.jpg,
    das die App beim Start automatisch lädt (Auto-Load)."""
    server_log.debug("GET /images/%s", filename)
    return send_from_directory(IMAGES_DIR, filename)


@app.route("/api/log", methods=["POST"])
def receive_browser_log():
    """
    Empfängt Frontend-Logs (src/logger.js) und schreibt sie nach browser.log.

    Erwartet JSON: {"level": "debug|info|warning|error", "message": str,
    "data": any, "timestamp": str, "url": str, "userAgent": str}.
    Antwort: 204 bei Erfolg, 400 bei ungültigem Body.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        server_log.warning("POST /api/log: ungültiger Body (%s Bytes, content-type=%s)",
                           request.content_length, request.content_type)
        return jsonify({"error": "JSON-Objekt erwartet"}), 400

    level_name = str(payload.get("level", "info")).lower()
    level = BROWSER_LEVELS.get(level_name, logging.INFO)
    message = str(payload.get("message", ""))[:4000]
    data = payload.get("data")
    try:
        data_str = "-" if data is None else json.dumps(data, ensure_ascii=False, default=str)[:4000]
    except (TypeError, ValueError):
        data_str = repr(data)[:4000]
    browser_log.log(
        level,
        "browser | %s | ts=%s url=%s ua=%s | data=%s",
        message,
        payload.get("timestamp", "-"),
        str(payload.get("url", "-"))[:500],
        str(payload.get("userAgent", "-"))[:300],
        data_str,
    )
    server_log.debug("POST /api/log empfangen: level=%s message=%r", level_name, message[:200])
    return "", 204


@app.before_request
def _request_start():
    """Startzeit merken, um die Dauer in after_request loggen zu können."""
    g.request_start = time.perf_counter()


@app.after_request
def _log_request_and_no_cache(response):
    """Jeden Request mit Methode, Pfad, Status, Dauer und Client loggen +
    während der Entwicklung keine Caches (aktuelle JS-Dateien ausliefern)."""
    duration_ms = (time.perf_counter() - g.request_start) * 1000 if hasattr(g, "request_start") else 0.0
    # /api/health wird im Poll minütlich abgefragt -> nur auf DEBUG loggen
    level = logging.DEBUG if request.path == "/api/health" else logging.INFO
    server_log.log(level, "%s %s -> %s (%.1f ms) from %s ua=%s",
                   request.method, request.path, response.status_code, duration_ms,
                   request.remote_addr, (request.user_agent.string or "-")[:120])
    response.headers["Cache-Control"] = "no-store"
    return response


@app.errorhandler(404)
def _not_found(err):
    server_log.debug("404: %s %s (von %s)", request.method, request.path, request.remote_addr)
    return jsonify({"error": "not found", "path": request.path}), 404


@app.errorhandler(Exception)
def _unhandled_error(err):
    """Jeder unbehandelte Fehler landet mit vollem Stacktrace im server.log."""
    server_log.exception("500 bei %s %s (von %s): %s", request.method, request.path,
                         request.remote_addr, err)
    return jsonify({"error": "internal server error", "message": str(err)}), 500


if __name__ == "__main__":
    # debug=True nur lokal; Host 127.0.0.1 -> Webcam (getUserMedia) ist auf
    # localhost ein "secure context" und funktioniert daher ohne HTTPS.
    server_log.info("Starte Flask direkt: host=127.0.0.1 port=5824 debug=True log_dir=%s", get_log_dir())
    app.run(host="127.0.0.1", port=5824, debug=True)
