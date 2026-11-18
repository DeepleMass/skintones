"""
test_app.py — Tests für den Flask-Server (ohne laufenden Port, via test_client).

Aufruf (zwei Varianten):
    # 1) als Repo-Paket vom Elternordner des Repos (skintones/):
    cd .. && python3 -m unittest skintones.webapp.flask_app.test_app -v
    # 2) klassisch aus webapp/ heraus (sys.path-Fallback unten):
    cd webapp && python3 -m unittest flask_app.test_app -v
    oder: python3 -m pytest flask_app/test_app.py
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Bevorzugt: Import als Repo-Paket (skintones.webapp.flask_app.app) —
# funktioniert, wenn das Repo als Verzeichnis "skintones" auf dem sys.path
# liegt (z. B. Aufruf vom Elternordner des Repos).
try:
    from skintones.webapp.flask_app.app import app, WEBAPP_ROOT, setup_logging, get_log_dir
except ModuleNotFoundError:
    # Fallback: webapp/ auf den sys.path legen, dann direkter Import
    # (funktioniert bei Aufruf aus webapp/: python3 -m unittest flask_app.test_app)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from flask_app.app import app, WEBAPP_ROOT, setup_logging, get_log_dir


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
            ("/src/i18n.js", "javascript"),
            ("/src/logger.js", "javascript"),
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

    def test_images_route_liefert_default_image(self):
        """GET /images/default-image.jpg -> 200 als JPEG (Auto-Load-Bild der App)."""
        resp = self.client.get("/images/default-image.jpg")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("image/jpeg", resp.content_type)
        self.assertGreater(len(resp.get_data()), 1000)  # echtes JPEG, kein Fehlertext

    def test_images_route_erlaubt_kein_path_traversal(self):
        """/images/..%2F..%2Fetc — send_from_directory muss das ablehnen (404)."""
        resp = self.client.get("/images/..%2F..%2Fstart.py")
        self.assertEqual(resp.status_code, 404)

    def test_webapp_root_zeigt_auf_index_html(self):
        """Sanity: das konfigurierte Root enthält index.html."""
        self.assertTrue((WEBAPP_ROOT / "index.html").is_file())


class LoggingTest(unittest.TestCase):
    """Prüft das Log-System: /api/log schreibt nach webapplogs/, Requests landen im server.log."""

    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()

    def setUp(self):
        # Log-Verzeichnis für jeden Test in ein frisches tmp-Verzeichnis legen
        self._tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self._tmp.name)
        setup_logging(self.log_dir)

    def tearDown(self):
        setup_logging()  # wieder auf den Default-Logordner (webapplogs/) zurück
        self._tmp.cleanup()

    def test_api_log_nimmt_browser_log_an_und_schreibt_browser_log(self):
        """POST /api/log mit gültigem JSON -> 204, Eintrag landet in browser.log."""
        resp = self.client.post("/api/log", json={
            "level": "error",
            "message": "pipeline.invalidParams",
            "data": {"error": "undefined is not an object (evaluating 'el.hue.value')",
                     "rawInputs": {"hue": "25"}},
            "timestamp": "2026-11-18T01:02:03.000Z",
            "url": "http://127.0.0.1:5824/",
            "userAgent": "UnitTestUA",
        })
        self.assertEqual(resp.status_code, 204)
        files = list(self.log_dir.glob("browser*.log"))
        self.assertTrue(files, "browser.log wurde nicht geschrieben")
        content = files[0].read_text(encoding="utf-8")
        self.assertIn("ERROR", content)
        self.assertIn("pipeline.invalidParams", content)
        self.assertIn("el.hue.value", content)   # Stack/Details des Fehlers im Log
        self.assertIn("UnitTestUA", content)
        # app.log: kombinierte Datei bekommt den Browser-Eintrag ebenfalls fortlaufend
        app_log = (self.log_dir / "app.log").read_text(encoding="utf-8")
        self.assertIn("pipeline.invalidParams", app_log)
        self.assertIn("webapp.browser", app_log)

    def test_api_log_unbekannter_level_faellt_auf_info(self):
        resp = self.client.post("/api/log", json={"level": "laut", "message": "hallo"})
        self.assertEqual(resp.status_code, 204)
        content = list(self.log_dir.glob("browser*.log"))[0].read_text(encoding="utf-8")
        self.assertIn("INFO", content)
        self.assertIn("hallo", content)

    def test_api_log_lehnt_ungueltigen_body_ab(self):
        """Kein JSON -> 400, kein Absturz."""
        resp = self.client.post("/api/log", data="kein json", content_type="text/plain")
        self.assertEqual(resp.status_code, 400)

    def test_requests_werden_im_server_log_protokolliert(self):
        """GET / und GET /api/health erscheinen mit Status und Dauer in server.log."""
        self.client.get("/")
        self.client.get("/api/health")
        self.client.get("/gibt-es-nicht")  # 404
        content = list(self.log_dir.glob("server*.log"))[0].read_text(encoding="utf-8")
        self.assertIn("GET / -> 200", content)
        self.assertIn("GET /api/health -> 200", content)
        self.assertIn("404", content)
        # app.log: Server-Requests landen dort ebenfalls fortlaufend
        app_log = (self.log_dir / "app.log").read_text(encoding="utf-8")
        self.assertIn("GET / -> 200", app_log)
        self.assertIn("skintone.server", app_log)

    def test_default_log_dir_ist_webapplogs_im_repo_root(self):
        """Ohne Env-Variable liegt das Log-Verzeichnis im Repo-Root als webapplogs/."""
        os.environ.pop("SKINTONE_LOG_DIR", None)
        log_dir = get_log_dir()
        self.assertEqual(log_dir.name, "webapplogs")
        self.assertEqual(log_dir.parent.name, WEBAPP_ROOT.parent.name)


if __name__ == "__main__":
    unittest.main()
