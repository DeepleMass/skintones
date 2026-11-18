"""
test_server_gui.py — Tests für server_gui.py (ServerController), ohne GUI/Display.

Der ServerController (start/stop/restart/Health-Poll) ist bewusst tkinter-frei,
damit er headless getestet werden kann. Aufruf aus dem Repo-Root:

    python3 -m unittest test_server_gui -v

Jeder Test startet einen echten Flask-Subprozess auf einem freien Port und
schreibt seine Logs in ein temporäres Verzeichnis (nicht nach webapplogs/).
Voraussetzung: Flask im verwendeten Python installiert (venv wird erkannt).
"""

import re
import socket
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from server_gui import ServerController, find_python_with_flask, setup_logging  # noqa: E402


def free_port() -> int:
    """Findet einen freien TCP-Port auf 127.0.0.1."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerControllerTest(unittest.TestCase):
    """Start/Stop/Restart des echten Flask-Servers + Health-Poll + Logging."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log_dir = Path(self._tmp.name)
        self.log = setup_logging(self.log_dir)  # gui.log landet im tmp-Verzeichnis
        self.port = free_port()
        self.ctrl = ServerController(
            port=self.port,
            python_exe=find_python_with_flask(),
            log=self.log,
        )

    def tearDown(self):
        self.ctrl.stop()
        self._tmp.cleanup()

    def _get(self, url: str) -> int:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status

    def test_start_healthy_serve_stop(self):
        """start -> health OK -> liefert index.html -> stop -> Port zu."""
        self.assertFalse(self.ctrl.is_running())
        self.assertTrue(self.ctrl.start(), "Start sollte gelingen")
        self.assertTrue(self.ctrl.is_running())
        self.assertTrue(self.ctrl.wait_healthy(20), "Health-Poll sollte durchkommen")
        self.assertEqual(self._get(self.ctrl.url), 200)
        self.assertEqual(self._get(self.ctrl.health_url), 200)
        self.ctrl.stop()
        self.assertFalse(self.ctrl.is_running())
        with self.assertRaises(OSError):
            urllib.request.urlopen(self.ctrl.health_url, timeout=1)  # Port wieder zu

    def test_restart_startet_neuen_prozess(self):
        """restart beendet den alten Prozess und startet einen neuen."""
        self.assertTrue(self.ctrl.start())
        self.assertTrue(self.ctrl.wait_healthy(20))
        pid_alt = self.ctrl.proc.pid
        self.assertTrue(self.ctrl.restart())
        self.assertTrue(self.ctrl.wait_healthy(20))
        self.assertNotEqual(pid_alt, self.ctrl.proc.pid, "neuer Prozess nach Restart")
        self.assertEqual(self._get(self.ctrl.url), 200)

    def test_start_while_running_returns_false(self):
        """Doppelter Start wird abgelehnt (GUI-Button 'start/restart' nutzt restart())."""
        self.assertTrue(self.ctrl.start())
        self.assertTrue(self.ctrl.wait_healthy(20))
        self.assertFalse(self.ctrl.start(), "läuft schon -> False")
        self.assertTrue(self.ctrl.is_running())

    def test_gui_log_wird_geschrieben(self):
        """Alle Controller-Aktionen landen in gui.log UND in der kombinierten app.log."""
        self.assertTrue(self.ctrl.start())
        self.assertTrue(self.ctrl.wait_healthy(20))
        self.ctrl.stop()
        files = list(self.log_dir.glob("gui*.log"))
        self.assertTrue(files, "gui.log fehlt")
        content = files[0].read_text(encoding="utf-8")
        self.assertIn("Starte Server", content)
        self.assertIn("Health-Poll OK", content)
        self.assertIn("sauber beendet", content)
        # app.log: eine fortlaufende Datei mit allem (GUI schreibt dort ebenfalls hinein)
        app_log = self.log_dir / "app.log"
        self.assertTrue(app_log.is_file(), "app.log fehlt")
        self.assertIn("Starte Server", app_log.read_text(encoding="utf-8"))

    def test_start_mit_falschem_python_schlägt_fehl_und_loggt(self):
        """Unbrauchbares Python -> start() liefert False, Fehler steht im Log."""
        ctrl = ServerController(port=free_port(), python_exe="/gibt/es/nicht/python",
                                log=self.log)
        self.assertFalse(ctrl.start())
        self.assertFalse(ctrl.is_running())
        content = list(self.log_dir.glob("gui*.log"))[0].read_text(encoding="utf-8")
        self.assertIn("fehlgeschlagen", content)


class ServerGuiSourceTest(unittest.TestCase):
    """Source-Level-Regression für die GUI (kann headless kein Tk-Fenster bauen).

    Bug war: _refresh() lief per root.after() sofort und griff auf self._busy zu,
    das erst in _set_busy() (Button-Klick) angelegt wurde -> AttributeError jede Sekunde.
    """

    def test_busy_wird_im_init_vor_dem_ersten_refresh_gesetzt(self):
        import server_gui
        src = Path(server_gui.__file__).read_text(encoding="utf-8")
        gui_cls = src.split("class ServerGui", 1)[1]
        init = gui_cls.split("def __init__", 1)[1].split("def _on_start", 1)[0]
        self.assertIn("self._busy = False", init)
        self.assertLess(init.index("self._busy = False"), init.index("root.after"),
                        "_busy muss vor dem ersten after()-Refresh initialisiert sein")

    def test_refresh_nutzt_getattr_statt_direktem_attributzugriff(self):
        import server_gui
        src = Path(server_gui.__file__).read_text(encoding="utf-8")
        refresh = src.split("def _refresh", 1)[1].split("def _load_log_tail", 1)[0]
        self.assertIn('getattr(self, "_busy", False)', refresh)

    def test_gui_log_schrift_ist_gross_genug_und_tail_liegt_app_log(self):
        """GUI-Log-Anzeige: größere Schrift (>= 11pt) und Tail der kombinierten app.log."""
        import server_gui
        src = Path(server_gui.__file__).read_text(encoding="utf-8")
        m = re.search(r'font=\("Menlo",\s*(\d+)\)', src)
        self.assertIsNotNone(m, "Log-Schriftart nicht gefunden")
        self.assertGreaterEqual(int(m.group(1)), 11, "Log-Schrift im GUI zu klein")
        tail = src.split("def _load_log_tail", 1)[1]
        self.assertIn('"app.log"', tail, "GUI soll die kombinierte app.log anzeigen")


if __name__ == "__main__":
    unittest.main()
