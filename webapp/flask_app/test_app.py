"""
test_app.py — Tests für den Flask-Server (ohne laufenden Port, via test_client).

Aufruf (aus dem webapp/-Verzeichnis):
    python3 -m unittest flask_app/test_app.py -v
    oder: python3 -m pytest flask_app/test_app.py
"""

import unittest
from pathlib import Path

# app.py liegt im selben Verzeichnis -> direkter Import möglich,
# wenn das Modul von webapp/ aus gestartet wird (sys.path enthält webapp/).
from skintones.webapp.flask_app.app import app, WEBAPP_ROOT


class FlaskAppTest(unittest.TestCase):
    """Prüft Auslieferung der Web-App und den Health-Endpunkt."""

    @classmethod
    def setUpClass(cls):
        # Flask-Testclient: echter Request-Stack, aber kein Netzwerk-Port
        app.config["TESTING"] = True
        cls.client = app.test_client()

    def test_index_liefert_html(self):
        """GET / liefert 200 und die index.html mit Modul-Script."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.content_type)
        body = resp.get_data(as_text=True)
        self.assertIn('<script type="module" src="./src/app.js"></script>', body)

    def test_statische_dateien_werden_ausgeliefert(self):
        """Kernmodule und Stylesheet sind erreichbar, JS mit JS-MIME-Typ."""
        for path, needle in [
            ("/styles.css", "text/css"),
            ("/src/app.js", "javascript"),      # Wichtig für ES-Module im Browser
            ("/src/pipeline.js", "javascript"),
            ("/src/hsv.js", "javascript"),
            ("/src/blur.js", "javascript"),
            ("/src/demo.js", "javascript"),
        ]:
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 200, path)
                self.assertIn(needle, resp.content_type, path)

    def test_health_endpoint(self):
        """GET /api/health liefert JSON mit status=ok (nutzt start.py zum Pollen)."""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok", "app": "skintone-webapp"})

    def test_unbekannter_pfad_liefert_404(self):
        resp = self.client.get("/gibt-es-nicht.js")
        self.assertEqual(resp.status_code, 404)

    def test_webapp_root_zeigt_auf_index_html(self):
        """Sanity: das konfigurierte Root enthält index.html."""
        self.assertTrue((WEBAPP_ROOT / "index.html").is_file())


if __name__ == "__main__":
    unittest.main()
