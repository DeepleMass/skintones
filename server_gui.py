#!/usr/bin/env python3
"""
server_gui.py — Mini-Tkinter-App im Repo-Root: steuert den Flask-Webserver per Klick.

Damit muss nicht jedes Mal die Shell bemüht werden: ein Button startet den
Server bzw. startet ihn neu (Restart), einer stoppt ihn, einer öffnet den
Browser. Unten im Fenster sieht man live das Neueste aus webapplogs/.

Aufruf (aus dem Repo-Root):
    python3 server_gui.py              # Port 5824
    python3 server_gui.py --port 8080  # anderer Port

Aufbau:
    - ServerController: start/stop/restart/is_running/wait_healthy — komplett
      ohne GUI, daher in test_server_gui.py headless getestet.
    - ServerGui: Tk-Fenster (Port-Wahl, Start/Restart-, Stop-, Browser-Button,
      Statuszeile, Log-Tail mit Auto-Refresh).
    - Logging: gui.log + app.log in webapplogs/ (app.log = alle Komponenten
      fortlaufend in einer Datei, das GUI zeigt deren Tail; täglich rotiert;
      SKINTONE_LOG_DIR zum Umschalten für Tests). tkinter wird erst in main()
      gebraucht, damit das Modul auch ohne tkinter (z. B. headless in CI)
      importierbar bleibt.

Voraussetzung: Flask im verwendeten Python installiert (venv wird automatisch
erkannt: ../.venv/bin/python relativ zum Repo-Root, sonst sys.executable).
"""

import argparse
import logging
import logging.handlers
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

# tkinter optional importieren — ohne Display/Modul bleibt das Modul importierbar
try:
    import tkinter as tk
    from tkinter import scrolledtext
except ImportError:  # z. B. headless oder _tkinter nicht gebaut
    tk = None
    scrolledtext = None

ROOT = Path(__file__).resolve().parent
WEBAPP_DIR = ROOT / "webapp"
HOST = "127.0.0.1"
LOG_DIR = Path(os.environ.get("SKINTONE_LOG_DIR") or (ROOT / "webapplogs"))

LOG_FORMAT = "%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)s | %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_dir: Path | None = None) -> logging.Logger:
    """Logger 'skintone.gui': gui.log (täglich rotiert) + Konsole. Idempotent."""
    log_dir = Path(log_dir) if log_dir else LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("skintone.gui")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    for h in list(log.handlers):
        log.removeHandler(h)
        h.close()
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / "gui.log", when="midnight", backupCount=14, encoding="utf-8",
    )
    fmt = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)
    file_handler.setFormatter(fmt)
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(fmt)
    app_handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / "app.log", when="midnight", backupCount=14, encoding="utf-8",
    )  # kombinierte Datei: alle Komponenten (server/browser/launcher/gui) schreiben hier fortlaufend
    app_handler.setFormatter(fmt)
    log.addHandler(file_handler)
    log.addHandler(app_handler)
    log.addHandler(stream)
    return log


def find_python_with_flask() -> str:
    """Bevorzugt das venv neben dem Repo (../.venv), prüft, dass flask importierbar ist."""
    candidates = [ROOT.parent / ".venv" / "bin" / "python", sys.executable]
    for exe in candidates:
        if not Path(exe).is_file():
            continue
        try:
            result = subprocess.run(
                [str(exe), "-c", "import flask; print(flask.__version__)"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                return str(exe)
        except (OSError, subprocess.TimeoutExpired):
            continue
    return sys.executable  # Fallback — Fehlermeldung kommt beim Start


class ServerController:
    """Steuert den Flask-Subprozess der Webapp (start/stop/restart + Health-Poll)."""

    def __init__(self, port: int = 5824, python_exe: str | None = None,
                 webapp_dir: Path = WEBAPP_DIR, log: logging.Logger | None = None):
        self.port = port
        self.python_exe = python_exe or sys.executable
        self.webapp_dir = Path(webapp_dir)
        self.log = log or logging.getLogger("skintone.gui")
        self.proc: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}/"

    @property
    def health_url(self) -> str:
        return f"http://{HOST}:{self.port}/api/health"

    def is_running(self) -> bool:
        """True, wenn der Subprozess existiert und noch nicht beendet ist."""
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> bool:
        """Startet den Flask-Subprozess. False, wenn er schon läuft oder der Start fehlschlägt."""
        if self.is_running():
            self.log.warning("start() aufgerufen, Server läuft aber schon (pid=%d) — ignoriert", self.proc.pid)
            return False
        cmd = [
            self.python_exe, "-m", "flask",
            "--app", "flask_app.app:app",
            "run", "--host", HOST, "--port", str(self.port),
        ]
        self.log.info("Starte Server: %s (cwd=%s, port=%d, python=%s)",
                      " ".join(cmd), self.webapp_dir, self.port, self.python_exe)
        try:
            self.proc = subprocess.Popen(cmd, cwd=self.webapp_dir)
        except (FileNotFoundError, PermissionError) as err:
            self.log.error("Server-Start fehlgeschlagen: %s — ist Flask installiert? "
                           "(pip install -r webapp/flask_app/requirements.txt)", err, exc_info=True)
            self.proc = None
            return False
        self.log.info("Subprozess gestartet: pid=%d url=%s", self.proc.pid, self.url)
        return True

    def stop(self) -> None:
        """Beendet den Subprozess sauber (terminate, notfalls kill)."""
        if self.proc is None:
            self.log.debug("stop() aufgerufen, aber kein Subprocess vorhanden")
            return
        pid = self.proc.pid
        if self.proc.poll() is None:
            self.log.info("Stoppe Server pid=%d (terminate)", pid)
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
                self.log.info("Server pid=%d sauber beendet", pid)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
                self.log.warning("Server pid=%d musste gekillt werden (terminate reichte nicht)", pid)
        else:
            self.log.info("Server pid=%d war schon beendet (Rückgabecode %s)", pid, self.proc.returncode)
        self.proc = None

    def restart(self) -> bool:
        """Stop + Start. Liefert True, wenn der neue Prozess gestartet werden konnte."""
        self.log.info("Restart angefordert (port=%d)", self.port)
        self.stop()
        return self.start()

    def wait_healthy(self, timeout_s: float = 10.0) -> bool:
        """Pollt /api/health, bis der Server antwortet. True bei Erfolg."""
        self.log.info("Health-Poll: %s (Timeout %.0f s)", self.health_url, timeout_s)
        deadline = time.time() + timeout_s
        attempts = 0
        while time.time() < deadline:
            attempts += 1
            try:
                with urllib.request.urlopen(self.health_url, timeout=1) as resp:
                    if resp.status == 200:
                        self.log.info("Health-Poll OK nach %d Versuch(en): %s", attempts, resp.read(200).decode("utf-8", "replace"))
                        return True
            except OSError as err:
                self.log.debug("Health-Poll Versuch %d: %s", attempts, err)
                time.sleep(0.2)
        self.log.error("Health-Poll fehlgeschlagen nach %d Versuchen: %s antwortet nicht", attempts, self.health_url)
        return False


class ServerGui:
    """Tk-Fenster: Start/Restart-Button, Stop, Browser öffnen, Status, Log-Tail."""

    def __init__(self, root, controller: ServerController, log: logging.Logger, log_dir: Path = LOG_DIR):
        self.root = root
        self.ctrl = controller
        self.log = log
        self.log_dir = Path(log_dir)
        root.title("Skintone-Lab — Server-Steuerung")
        root.minsize(680, 600)

        top = tk.Frame(root, padx=8, pady=8)
        top.pack(fill="x")

        tk.Label(top, text="Port:").pack(side="left")
        self.port_var = tk.StringVar(value=str(controller.port))
        self.port_entry = tk.Spinbox(top, from_=1024, to=65535, width=7, textvariable=self.port_var)
        self.port_entry.pack(side="left", padx=(4, 12))

        self.btn_start = tk.Button(top, text="Server starten / neu starten", command=self._on_start)
        self.btn_start.pack(side="left", padx=4)
        self.btn_stop = tk.Button(top, text="Stoppen", command=self._on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=4)
        self.btn_browser = tk.Button(top, text="Browser öffnen", command=self._on_browser, state="disabled")
        self.btn_browser.pack(side="left", padx=4)

        self.auto_browser_var = tk.BooleanVar(value=True)
        tk.Checkbutton(top, text="Browser automatisch öffnen", variable=self.auto_browser_var).pack(side="left", padx=(12, 0))

        self.status_var = tk.StringVar(value="Status: gestoppt")
        status_bar = tk.Label(root, textvariable=self.status_var, anchor="w",
                              relief="sunken", padx=8, pady=4, font=("TkDefaultFont", 10, "bold"))
        status_bar.pack(fill="x", padx=8)

        tk.Label(root, text=f"Log-Tail ({self.log_dir}/app.log — alle Logs fortlaufend in einer Datei):",
                 anchor="w", padx=8).pack(fill="x")
        self.log_text = scrolledtext.ScrolledText(root, height=24, state="disabled",
                                                   font=("Menlo", 12), wrap="none", padx=6, pady=6)
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.log.info("GUI-Fenster aufgebaut (port=%d, auto_browser=%s)", controller.port, self.auto_browser_var.get())
        self._busy = False  # muss vor dem ersten _refresh existieren (läuft per after() sofort)
        self._refresh_job = root.after(1000, self._refresh)

    # ---------- Button-Handler ----------

    def _on_start(self) -> None:
        """Start/Restart im Worker-Thread, damit die GUI nicht einfriert."""
        try:
            self.ctrl.port = int(self.port_var.get())
        except ValueError:
            self.log.error("Ungültiger Port: %r", self.port_var.get())
            self.status_var.set(f"Status: ungültiger Port „{self.port_var.get()}“")
            return
        self.log.info("GUI-Klick: Start/Restart (port=%d, läuft bereits=%s)", self.ctrl.port, self.ctrl.is_running())
        self._set_busy(True)
        threading.Thread(target=self._start_worker, daemon=True).start()

    def _start_worker(self) -> None:
        restart = self.ctrl.is_running()
        ok = self.ctrl.restart() if restart else self.ctrl.start()
        healthy = ok and self.ctrl.wait_healthy(15)
        self.root.after(0, lambda: self._after_start(restart, ok, healthy))

    def _after_start(self, restart: bool, ok: bool, healthy: bool) -> None:
        self._set_busy(False)
        if healthy:
            self.status_var.set(f"Status: läuft auf {self.ctrl.url} (pid={self.ctrl.proc.pid})")
            self.btn_stop.config(state="normal")
            self.btn_browser.config(state="normal")
            self.log.info("Server bereit: %s", self.ctrl.url)
            if self.auto_browser_var.get():
                self.log.info("Browser automatisch öffnen: %s", self.ctrl.url)
                webbrowser.open(self.ctrl.url)
        else:
            action = "Restart" if restart else "Start"
            self.status_var.set(f"Status: {action} fehlgeschlagen — Details in webapplogs/gui.log")
            self.log.error("GUI: %s fehlgeschlagen (ok=%s healthy=%s)", action, ok, healthy)
            self.btn_stop.config(state="normal" if self.ctrl.is_running() else "disabled")
            self.btn_browser.config(state="normal" if self.ctrl.is_running() else "disabled")

    def _on_stop(self) -> None:
        self.log.info("GUI-Klick: Stoppen")
        self._set_busy(True)
        threading.Thread(target=self._stop_worker, daemon=True).start()

    def _stop_worker(self) -> None:
        self.ctrl.stop()
        self.root.after(0, self._after_stop)

    def _after_stop(self) -> None:
        self._set_busy(False)
        self.status_var.set("Status: gestoppt")
        self.btn_stop.config(state="disabled")
        self.btn_browser.config(state="disabled")
        self.log.info("GUI: Server gestoppt")

    def _on_browser(self) -> None:
        self.log.info("GUI-Klick: Browser öffnen -> %s", self.ctrl.url)
        webbrowser.open(self.ctrl.url)

    # ---------- Periodisches Refresh (Status + Log-Tail) ----------

    def _refresh(self) -> None:
        try:
            if self.ctrl.is_running():
                self.status_var.set(f"Status: läuft auf {self.ctrl.url} (pid={self.ctrl.proc.pid})")
                self.btn_stop.config(state="normal")
                self.btn_browser.config(state="normal")
            elif not getattr(self, "_busy", False):
                self.status_var.set("Status: gestoppt")
                self.btn_stop.config(state="disabled")
                self.btn_browser.config(state="disabled")
            self._load_log_tail()
        except Exception as err:  # Refresh darf die GUI nie killen
            self.log.error("GUI-Refresh fehlgeschlagen: %s", err, exc_info=True)
        self._refresh_job = self.root.after(1000, self._refresh)

    def _load_log_tail(self, max_lines: int = 300) -> None:
        """Zeigt die letzten max_lines Zeilen der kombinierten app.log (alle Komponenten
        schreiben fortlaufend in diese eine Datei). Fallback: neueste *.log-Datei."""
        target = self.log_dir / "app.log"
        if not target.is_file():
            files = sorted(self.log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
            target = files[0] if files else None
        if target is None:
            text = "(noch keine Log-Dateien in webapplogs/)"
        else:
            with open(target, encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()[-max_lines:]
            text = f"— {target.name} —\n" + "".join(lines)
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", text)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.btn_start.config(state="disabled" if busy else "normal")

    def _on_close(self) -> None:
        self.log.info("GUI wird geschlossen — Server wird gestoppt")
        try:
            self.root.after_cancel(self._refresh_job)
        except Exception:
            pass
        self.ctrl.stop()
        self.log.info("GUI beendet.")
        self.root.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description="Tkinter-GUI: Skintone-Webserver starten/stoppen")
    parser.add_argument("--port", type=int, default=5824, help="Port des Flask-Servers (Default: 5824)")
    args = parser.parse_args()

    log = setup_logging()
    log.info("server_gui.py gestartet: port=%d display=%s tk=%s",
             args.port, os.environ.get("DISPLAY", "(kein DISPLAY)"), "verfügbar" if tk else "NICHT verfügbar")

    if tk is None:
        log.error("tkinter ist nicht verfügbar — GUI kann nicht starten. "
                  "Alternative: python3 start.py --port %d", args.port)
        print("FEHLER: tkinter nicht verfügbar. Alternative: python3 start.py")
        return 1

    python_exe = find_python_with_flask()
    log.info("Verwendetes Python für den Server: %s", python_exe)

    root = tk.Tk()
    controller = ServerController(port=args.port, python_exe=python_exe, log=log)
    ServerGui(root, controller, log)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
