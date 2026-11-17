"""
app.py — Flask-Server für die Skintone-Web-App.

Aufgabe: Die reine JavaScript-App (index.html + src/) wird statisch
ausgeliefert, damit sie im Browser läuft. Es gibt keine serverseitige
Bildverarbeitung — die Pipeline läuft komplett im Browser (Canvas).

Start (Varianten):
    python3 flask_app/app.py                 # direkt, Port 5824
    flask --app flask_app/app run --port 5824 # über die Flask-CLI
    python3 start.py                          # startet Server UND öffnet Browser

Getestet mit: python3 -m unittest flask_app/test_app.py  (von webapp/ aus)
"""

from pathlib import Path

from flask import Flask, jsonify, send_from_directory

# Projekt-Root = das Verzeichnis, in dem index.html liegt (ein Ebene höher)
WEBAPP_ROOT = Path(__file__).resolve().parent.parent

# static_folder auf das Webapp-Root legen und static_url_path leeren,
# damit "/" direkt index.html ausliefert und "/src/app.js" unter /src/ liegt.
app = Flask(__name__, static_folder=str(WEBAPP_ROOT), static_url_path="")


@app.route("/")
def index():
    """Startseite: index.html aus dem Webapp-Root."""
    return send_from_directory(WEBAPP_ROOT, "index.html")


@app.route("/api/health")
def health():
    """Health-Check für das Start-Skript und Tests (JSON)."""
    return jsonify({"status": "ok", "app": "skintone-webapp"})


@app.after_request
def no_cache(response):
    """Während der Entwicklung keine Caches (aktuelle JS-Dateien ausliefern)."""
    response.headers["Cache-Control"] = "no-store"
    return response


if __name__ == "__main__":
    # debug=True nur lokal; Host 127.0.0.1 -> Webcam (getUserMedia) ist auf
    # localhost ein "secure context" und funktioniert daher ohne HTTPS.
    app.run(host="127.0.0.1", port=5824, debug=True)
