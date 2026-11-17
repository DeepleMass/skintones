#!/usr/bin/env python3
"""Skintone Lab — grafische Oberfläche für das Rust-Experiment.

Aufbau (Standard-Elemente für diese Art Anwendung):
- Menü und Werkzeugknöpfe: Bild laden, Beispielbild laden (skintones/sample-images),
  Demo-Portrait, Webcam, Verarbeiten, Zurücksetzen (Restart), Ergebnis speichern
- Parameter-Leiste: Hue, Toleranz, Blur, Abdunkeln, Feather als Slider+Spinbox
  plus Farbvorschau (Swatch + Hue/Hex-Anzeige als Kontrolle für den User)
- Zwei Bildbereiche (Original und Ergebnis), deren Anordnung per Button/Menü
  zwischen horizontal (nebeneinander) und vertikal (untereinander) wechselt
- Helles Theme (unabhängig vom System-Darkmode)
- Statusleiste unten, Auto-Vorschau (Verarbeiten nach jeder Änderung)

Alle Pixelarbeit macht das Rust-Binary `skintone-lab` (siehe rust_bridge.py);
diese GUI ruft es nur als Subprozess auf.

Start:  python3 skintone_gui.py [--binary PFAD_ZUM_RUST_BINARY]
"""

from __future__ import annotations

import argparse
import colorsys
import json
import queue
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import rust_bridge
from rust_bridge import ProcessParams

# Pillow ist der Standard für Bildanzeige/Skalierung in tkinter;
# ohne Pillow klappt die Anzeige nur für PNG direkt über tkinter.
try:
    from PIL import Image, ImageTk

    HAS_PIL = True
except ImportError:  # pragma: no cover - abhängig von der Installation
    HAS_PIL = False

# Maximale Größe der Vorschau (Bild wird proportional hinein skaliert)
PREVIEW_MAX = (560, 560)
# Dateitypen für den Öffnen-Dialog
IMAGE_FILETYPES = [
    ("Bilddateien", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp"),
    ("Alle Dateien", "*.*"),
]

# Unterstützte Bild-Endungen (z. B. für die Beispielbild-Suche)
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp"}

# Layout-Modi der Bildanzeige: Original/Ergebnis nebeneinander oder untereinander
LAYOUT_MODES = ("horizontal", "vertikal")
DEFAULT_LAYOUT = "horizontal"


def hue_to_hex(hue: float, saturation: float = 0.65, value: float = 0.9) -> str:
    """Wandelt einen Hue-Wert (Grad) in '#rrggbb' um — für die Farbvorschau."""
    r, g, b = colorsys.hsv_to_rgb((hue % 360.0) / 360.0, saturation, value)
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))


def strip_jsonc(text: str) -> str:
    """Entfernt //-Kommentare aus JSONC (z. B. .vscode/settings.json) außerhalb von Strings."""
    out: list[str] = []
    i, n, in_str = 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def workspace_root() -> Path:
    """Root-Ordner des Workspaces: skintone_gui.py liegt in <root>/skintones/python/."""
    return Path(__file__).resolve().parents[2]


def find_sample_image() -> Path | None:
    """Sucht das Default-Beispielbild (skintones/sample-images/default-image.jpg).

    Konfiguration in .vscode/settings.json (Pfade relativ zum Workspace-Root):
    - 'skintones.defaultSampleImage': konkrete Default-Datei
      (Fallback: skintones/sample-images/default-image.jpg)
    - 'skintones.sampleImagesDir':    Fallback-Verzeichnis — falls das Default-Bild
      fehlt, wird dort die erste unterstützte Bilddatei (sortiert) genommen
    Liefert None, wenn kein Bild gefunden wird.
    """
    root = workspace_root()
    settings_data: dict = {}
    settings = root / ".vscode" / "settings.json"
    if settings.is_file():
        try:
            settings_data = json.loads(strip_jsonc(settings.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            settings_data = {}

    # 1. explizit konfiguriertes Default-Bild
    rel_image = settings_data.get("skintones.defaultSampleImage") or "skintones/sample-images/default-image.jpg"
    candidate = root / rel_image
    if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES:
        return candidate

    # 2. Fallback: erstes Bild im konfigurierten sample-images-Verzeichnis
    rel_dir = settings_data.get("skintones.sampleImagesDir") or "skintones/sample-images"
    sample_dir = root / rel_dir
    if sample_dir.is_dir():
        for f in sorted(sample_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES:
                return f
    return None


class SkintoneApp(tk.Tk):
    """Hauptfenster der Anwendung."""

    def __init__(self, binary: Path | None) -> None:
        super().__init__()
        self.title("Skintone Lab — HSV-Hue-Selektion")
        self.geometry("1280x800")
        self.minsize(960, 600)

        # ----- Zustand -----------------------------------------------------
        self.binary = binary  # Pfad zum Rust-Binary (None = automatisch suchen)
        self.source_path: Path | None = None   # aktuell geladenes Original
        self.result_path: Path | None = None   # letzte Ergebnisdatei
        self._tmp_dir = tempfile.TemporaryDirectory(prefix="skintone-gui-")
        self._result_file = Path(self._tmp_dir.name) / "ergebnis.png"
        self._photo_orig: ImageTk.PhotoImage | tk.PhotoImage | None = None
        self._photo_result: ImageTk.PhotoImage | tk.PhotoImage | None = None
        self._busy = False
        # Worker-Thread -> Hauptthread (GUI-Updates nur im Hauptthread!)
        self._events: queue.Queue = queue.Queue()

        # Layout-Modus (horizontal = nebeneinander, vertikal = untereinander)
        self.layout_mode = tk.StringVar(value=DEFAULT_LAYOUT)
        # explizit helles Theme, unabhängig vom System-Darkmode
        self._apply_light_theme()
        self._build_menu()
        self._build_widgets()
        self._poll_events()
        self._set_status("Bereit. Bitte ein Bild laden, Beispielbild laden oder Demo-Portrait erzeugen.")

    # ------------------------------------------------------------------ UI
    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        datei = tk.Menu(menubar, tearoff=0)
        datei.add_command(label="Bild öffnen …", accelerator="Strg+O", command=self.on_open_image)
        datei.add_command(label="Beispielbild laden …", accelerator="Strg+B", command=self.on_load_sample)
        datei.add_command(label="Demo-Portrait erzeugen …", command=self.on_demo)
        datei.add_command(label="Webcam aufnehmen …", accelerator="Strg+W", command=self.on_webcam)
        datei.add_separator()
        datei.add_command(label="Ergebnis speichern unter …", accelerator="Strg+S", command=self.on_save_result)
        datei.add_separator()
        datei.add_command(label="Beenden", accelerator="Strg+Q", command=self.on_quit)
        menubar.add_cascade(label="Datei", menu=datei)
        ansicht = tk.Menu(menubar, tearoff=0)
        ansicht.add_radiobutton(label="Layout: horizontal (nebeneinander)", variable=self.layout_mode, value="horizontal", command=self._apply_layout)
        ansicht.add_radiobutton(label="Layout: vertikal (untereinander)", variable=self.layout_mode, value="vertikal", command=self._apply_layout)
        menubar.add_cascade(label="Ansicht", menu=ansicht)
        hilfe = tk.Menu(menubar, tearoff=0)
        hilfe.add_command(label="Über …", command=self.on_about)
        menubar.add_cascade(label="Hilfe", menu=hilfe)
        self.config(menu=menubar)

        self.bind("<Control-o>", lambda _e: self.on_open_image())
        self.bind("<Control-b>", lambda _e: self.on_load_sample())
        self.bind("<Control-w>", lambda _e: self.on_webcam())
        self.bind("<Control-s>", lambda _e: self.on_save_result())
        self.bind("<Control-q>", lambda _e: self.on_quit())

    def _build_widgets(self) -> None:
        # Hauptspalte: links Parameter, rechts Bilder
        main = ttk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # --- Linke Seite: Parameter + Aktionen -----------------------------
        left = ttk.Frame(main, width=300)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 6))
        left.pack_propagate(False)

        params = ttk.LabelFrame(left, text="Parameter")
        params.pack(fill=tk.X, pady=(0, 6))

        # Jede Zeile: Slider + Spinbox, über eine Variable synchronisiert
        self.var_hue = tk.DoubleVar(value=rust_bridge.DEFAULT_HUE)
        self.var_tolerance = tk.DoubleVar(value=rust_bridge.DEFAULT_TOLERANCE)
        self.var_blur = tk.DoubleVar(value=rust_bridge.DEFAULT_BLUR_SIGMA)
        self.var_darken = tk.DoubleVar(value=rust_bridge.DEFAULT_DARKEN * 100)  # Anzeige in %
        self.var_feather = tk.DoubleVar(value=rust_bridge.DEFAULT_FEATHER)

        self._add_slider_row(params, "Hue (Grad)", self.var_hue, 0, 359, 1)
        self._add_slider_row(params, "Toleranz ± (Grad)", self.var_tolerance, 0, 180, 1)
        self._add_slider_row(params, "Blur-Sigma (px)", self.var_blur, 0, 30, 0.5)
        self._add_slider_row(params, "Abdunkeln (%)", self.var_darken, 0, 100, 1)
        self._add_slider_row(params, "Kante weich (px)", self.var_feather, 0, 20, 1)

        # Farbvorschau: Swatch + numerische Anzeige des aktuellen Hue-Werts
        swatch_row = ttk.Frame(params)
        swatch_row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(swatch_row, text="Aktuelle Farbe:", width=18, anchor=tk.W).pack(side=tk.LEFT)
        self.swatch = tk.Label(swatch_row, width=6, relief=tk.SUNKEN, bd=2)
        self.swatch.pack(side=tk.LEFT, padx=2)
        self.color_readout = ttk.Label(swatch_row, text="")
        self.color_readout.pack(side=tk.LEFT, padx=4)
        self.var_hue.trace_add("write", lambda *_: self._update_color_preview())
        self.var_tolerance.trace_add("write", lambda *_: self._update_color_preview())
        self._update_color_preview()

        self.var_auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            left, text="Auto-Vorschau (sofort neu rechnen)", variable=self.var_auto
        ).pack(anchor=tk.W, pady=(0, 6))

        actions = ttk.LabelFrame(left, text="Aktionen")
        actions.pack(fill=tk.X)
        ttk.Button(actions, text="Bild laden …", command=self.on_open_image).pack(fill=tk.X, pady=1)
        ttk.Button(actions, text="Beispielbild laden", command=self.on_load_sample).pack(fill=tk.X, pady=1)
        ttk.Button(actions, text="Demo-Portrait", command=self.on_demo).pack(fill=tk.X, pady=1)
        ttk.Button(actions, text="Layout wechseln (horizontal/vertikal)", command=self.on_toggle_layout).pack(fill=tk.X, pady=1)
        ttk.Button(actions, text="Webcam …", command=self.on_webcam).pack(fill=tk.X, pady=1)
        ttk.Button(actions, text="Verarbeiten", command=self.on_process).pack(fill=tk.X, pady=1)
        ttk.Button(actions, text="Zurücksetzen (Restart)", command=self.on_reset).pack(fill=tk.X, pady=1)
        ttk.Button(actions, text="Ergebnis speichern …", command=self.on_save_result).pack(fill=tk.X, pady=1)

        # --- Rechte Seite: Original vs. Ergebnis ----------------------------
        # Die Anordnung (nebeneinander / untereinander) ist umschaltbar,
        # damit sie zum Seitenverhältnis des Bildes/Fensters passt.
        self.panes = ttk.Frame(main)
        self.panes.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.pane_orig = ttk.LabelFrame(self.panes, text="Original")
        self.label_orig = ttk.Label(self.pane_orig, text="(kein Bild geladen)", anchor=tk.CENTER)
        self.label_orig.pack(fill=tk.BOTH, expand=True)

        self.pane_result = ttk.LabelFrame(self.panes, text="Ergebnis (Hue selektiert, Rest geblurt + abgedunkelt)")
        self.label_result = ttk.Label(self.pane_result, text="(noch nicht verarbeitet)", anchor=tk.CENTER)
        self.label_result.pack(fill=tk.BOTH, expand=True)

        self._apply_layout()

        # --- Statusleiste ----------------------------------------------------
        self.var_status = tk.StringVar()
        ttk.Label(self, textvariable=self.var_status, relief=tk.SUNKEN, anchor=tk.W).pack(
            fill=tk.X, side=tk.BOTTOM, padx=6, pady=(0, 4)
        )

    def _add_slider_row(
        self, parent: ttk.Frame, text: str, var: tk.DoubleVar, lo: float, hi: float, step: float
    ) -> None:
        """Erzeugt eine Zeile aus Label, Slider und Spinbox (synchron über `var`).

        Slider feuert bei jeder Bewegung; die eigentliche Verarbeitung hängt am
        Loslassen (`<ButtonRelease-1>`) bzw. am Spinbox, damit es nicht ruckelt.
        """
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(row, text=text, width=18, anchor=tk.W).pack(side=tk.LEFT)
        slider = ttk.Scale(row, from_=lo, to=hi, variable=var, orient=tk.HORIZONTAL)
        slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        spin = ttk.Spinbox(row, from_=lo, to=hi, increment=step, width=7, textvariable=var)
        spin.pack(side=tk.LEFT)
        # Bei Loslassen der Maus oder Änderung in der Spinbox: auto-vorschau
        slider.bind("<ButtonRelease-1>", lambda _e: self.on_params_changed())
        spin.bind("<Return>", lambda _e: self.on_params_changed())
        spin.bind("<FocusOut>", lambda _e: self.on_params_changed())

    # ------------------------------------------------------- Theme & Layout
    def _apply_light_theme(self) -> None:
        """Setzt ein explizit helles Theme (unabhängig vom System-Darkmode)."""
        bg, fg, field, accent = "#f2f2f2", "#1a1a1a", "#ffffff", "#dcdcdc"
        self.configure(bg=bg)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")  # plattformübergreifend verfügbar und hell
        except tk.TclError:
            pass  # Fallback: Standard-Theme, die Farben unten greifen trotzdem
        for name in ("TFrame", "TLabel", "TLabelframe", "TCheckbutton", "TButton"):
            style.configure(name, background=bg, foreground=fg)
        style.configure("TLabelframe.Label", background=bg, foreground=fg)
        style.configure("TEntry", fieldbackground=field, foreground=fg)
        style.configure("Horizontal.TScale", background=bg, troughcolor="#cfcfcf")
        style.map("TButton", background=[("active", accent)])
        # klassische tk-Widgets (Menüs) explizit hell
        self.option_add("*Menu.background", field)
        self.option_add("*Menu.foreground", fg)
        self.option_add("*Menu.activeBackground", accent)

    def _apply_layout(self) -> None:
        """Packt Original/Ergebnis je nach layout_mode horizontal oder vertikal."""
        for pane in (self.pane_orig, self.pane_result):
            pane.pack_forget()
        if self.layout_mode.get() == "vertikal":
            self.pane_orig.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 3))
            self.pane_result.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(3, 0))
        else:
            self.pane_orig.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))
            self.pane_result.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3, 0))

    def on_toggle_layout(self) -> None:
        """Button: zwischen horizontaler und vertikaler Anordnung wechseln."""
        self.layout_mode.set("vertikal" if self.layout_mode.get() == "horizontal" else "horizontal")
        self._apply_layout()
        self._set_status(f"Layout: {self.layout_mode.get()}")

    def _update_color_preview(self) -> None:
        """Farbvorschau: Swatch + Text mit Hue/Toleranz/Hex als Kontrolle für den User."""
        hue, tol = self.var_hue.get(), self.var_tolerance.get()
        hexcol = hue_to_hex(hue)
        self.swatch.configure(bg=hexcol)
        self.color_readout.configure(text=f"Hue {hue:.0f}° ± {tol:.0f}° · {hexcol}")

    # ------------------------------------------------------------- Hilfsfunktionen
    def _set_status(self, msg: str) -> None:
        self.var_status.set(msg)

    def _load_image_into(self, path: Path, label: ttk.Label, attr: str) -> None:
        """Lädt `path` und zeigt eine skalierte Vorschau im Label an."""
        if HAS_PIL:
            img = Image.open(path)
            img.thumbnail(PREVIEW_MAX)  # proportional skalieren, Original bleibt
            photo = ImageTk.PhotoImage(img)
        else:
            # Fallback ohne Pillow: tkinter kann PNG/GIF direkt lesen
            photo = tk.PhotoImage(file=str(path))
        setattr(self, attr, photo)  # Referenz halten, sonst wird das Bild weggeworfen
        label.configure(image=photo, text="")

    def _current_params(self) -> ProcessParams:
        """Liest die Slider-Werte aus und baut ein validiertes ProcessParams."""
        return ProcessParams(
            hue=self.var_hue.get(),
            tolerance=self.var_tolerance.get(),
            blur_sigma=self.var_blur.get(),
            darken=self.var_darken.get() / 100.0,  # GUI zeigt %, Rust will Anteil
            feather=self.var_feather.get(),
        )

    def _resolve_binary(self) -> Path:
        if self.binary is not None:
            return self.binary
        return rust_bridge.find_binary()

    def _poll_events(self) -> None:
        """Holt fertige Ergebnisse aus dem Worker-Thread (nur Hauptthread malt)."""
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "done":
                    self._on_process_done(payload)
                elif kind == "error":
                    self._on_process_error(payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    # ------------------------------------------------------------- Aktionen
    def on_open_image(self) -> None:
        path = filedialog.askopenfilename(title="Bild öffnen", filetypes=IMAGE_FILETYPES)
        if not path:
            return
        self.source_path = Path(path)
        self._load_image_into(self.source_path, self.label_orig, "_photo_orig")
        self._set_status(f"Bild geladen: {self.source_path}")
        self.on_params_changed()  # Auto-Vorschau direkt mitlaufen lassen

    def on_load_sample(self) -> None:
        """Lädt das Beispielbild aus skintones/sample-images."""
        sample = find_sample_image()
        if sample is None:
            messagebox.showinfo(
                "Kein Beispielbild",
                "In skintones/sample-images wurde kein Bild gefunden.",
            )
            return
        self.source_path = sample
        self._load_image_into(sample, self.label_orig, "_photo_orig")
        self._set_status(f"Beispielbild geladen: {sample.name}")
        self.on_params_changed()  # Auto-Vorschau direkt mitlaufen lassen

    def on_demo(self) -> None:
        """Erzeugt über das Rust-Binary ein synthetisches Demo-Portrait."""
        try:
            binary = self._resolve_binary()
        except FileNotFoundError as e:
            messagebox.showerror("Binary fehlt", str(e))
            return
        demo_path = Path(self._tmp_dir.name) / "demo.png"
        result = rust_bridge.run_demo(binary, demo_path, 640, 480)
        if not result.ok:
            messagebox.showerror("Demo fehlgeschlagen", result.stderr)
            return
        self.source_path = demo_path
        self._load_image_into(demo_path, self.label_orig, "_photo_orig")
        self._set_status("Demo-Portrait erzeugt (640x480).")
        self.on_params_changed()

    def on_webcam(self) -> None:
        """Nimmt ein Einzelbild über die Webcam auf (optional via OpenCV).

        OpenCV (`pip install opencv-python`) ist der Python-Standard für
        Webcam-Zugriff. Ohne cv2 erscheint ein Hinweis; die Frame-Datei wird
        als normales Bild weiterverarbeitet.
        """
        try:
            import cv2  # type: ignore
        except ImportError:
            messagebox.showinfo(
                "Webcam nicht verfügbar",
                "Für die Webcam-Funktion bitte OpenCV installieren:\n"
                "pip install opencv-python\n\n"
                "Alternativ ein Foto als Datei laden (Bild laden …).",
            )
            return

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showerror("Webcam", "Keine Webcam gefunden (Index 0).")
            return

        win = tk.Toplevel(self)
        win.title("Webcam — Leertaste = aufnehmen, Esc = schließen")
        lbl = ttk.Label(win)
        lbl.pack()
        state = {"frame": None}

        def update_preview() -> None:
            ok, frame = cap.read()
            if ok:
                state["frame"] = frame
                # BGR -> RGB, dann über PIL für tkinter aufbereiten
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb)
                img.thumbnail((640, 480))
                photo = ImageTk.PhotoImage(img)
                lbl.configure(image=photo)
                lbl.image = photo  # Referenz halten
            if win.winfo_exists():
                win.after(30, update_preview)

        def take() -> None:
            if state["frame"] is not None:
                path = Path(self._tmp_dir.name) / "webcam.png"
                cv2.imwrite(str(path), state["frame"])
                cap.release()
                win.destroy()
                self.source_path = path
                self._load_image_into(path, self.label_orig, "_photo_orig")
                self._set_status(f"Webcam-Frame gespeichert: {path}")
                self.on_params_changed()

        def close() -> None:
            cap.release()
            win.destroy()

        ttk.Button(win, text="Aufnehmen", command=take).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(win, text="Abbrechen", command=close).pack(side=tk.LEFT, padx=4, pady=4)
        win.bind("<space>", lambda _e: take())
        win.bind("<Escape>", lambda _e: close())
        win.protocol("WM_DELETE_WINDOW", close)
        update_preview()

    def on_params_changed(self) -> None:
        """Auto-Vorschau: nur neu rechnen, wenn aktiv und ein Bild geladen ist."""
        if self.var_auto.get() and self.source_path is not None:
            self.on_process()

    def on_process(self) -> None:
        """Startet die Verarbeitung im Hintergrund-Thread (GUI bleibt bedienbar)."""
        if self._busy:
            return
        if self.source_path is None:
            messagebox.showinfo("Kein Bild", "Bitte zuerst ein Bild laden oder Demo-Portrait erzeugen.")
            return
        try:
            params = self._current_params()
            params.validate()
            binary = self._resolve_binary()
        except (ValueError, FileNotFoundError) as e:
            messagebox.showerror("Ungültig", str(e))
            return

        self._busy = True
        self._set_status("Verarbeite …")
        args = (binary, params, self.source_path, self._result_file)

        def worker() -> None:
            try:
                result = rust_bridge.run_process(*args)
                self._events.put(("done", result))
            except Exception as e:  # z. B. Timeout, fehlendes Binary
                self._events.put(("error", e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_process_done(self, result: rust_bridge.ProcessResult) -> None:
        self._busy = False
        if result.ok and self._result_file.exists():
            self.result_path = self._result_file
            self._load_image_into(self._result_file, self.label_result, "_photo_result")
            self._set_status(
                f"Fertig in {result.elapsed_s:.2f}s — {result.ok_line or 'OK'}"
            )
        else:
            self._set_status(f"Fehler (Exit {result.returncode}): {result.stderr.strip()}")
            messagebox.showerror("Verarbeitung fehlgeschlagen", result.stderr.strip() or "unbekannter Fehler")

    def _on_process_error(self, exc: Exception) -> None:
        self._busy = False
        self._set_status(f"Fehler: {exc}")
        messagebox.showerror("Fehler", str(exc))

    def on_reset(self) -> None:
        """Restart: Parameter auf Standard zurücksetzen und neu rechnen."""
        self.var_hue.set(rust_bridge.DEFAULT_HUE)
        self.var_tolerance.set(rust_bridge.DEFAULT_TOLERANCE)
        self.var_blur.set(rust_bridge.DEFAULT_BLUR_SIGMA)
        self.var_darken.set(rust_bridge.DEFAULT_DARKEN * 100)
        self.var_feather.set(rust_bridge.DEFAULT_FEATHER)
        self.label_result.configure(image="", text="(noch nicht verarbeitet)")
        self._photo_result = None
        self._set_status("Parameter zurückgesetzt.")
        if self.source_path is not None:
            self.on_process()

    def on_save_result(self) -> None:
        if self.result_path is None or not self.result_path.exists():
            messagebox.showinfo("Kein Ergebnis", "Es gibt noch kein gespeichertes Ergebnis.")
            return
        dest = filedialog.asksaveasfilename(
            title="Ergebnis speichern unter …",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("Alle Dateien", "*.*")],
        )
        if not dest:
            return
        try:
            if HAS_PIL:
                # Über Pillow speichern, damit auch jpg etc. geht
                Image.open(self.result_path).save(dest)
            else:
                Path(dest).write_bytes(self.result_path.read_bytes())
        except Exception as e:
            messagebox.showerror("Speichern fehlgeschlagen", str(e))
            return
        self._set_status(f"Ergebnis gespeichert: {dest}")

    def on_about(self) -> None:
        messagebox.showinfo(
            "Über Skintone Lab",
            "HSV-Hue-Selektion (Hautfarb-Experiment)\n\n"
            "Bildverarbeitung: Rust (`skintone-lab`, siehe ../rust)\n"
            "Oberfläche: Python/tkinter (dieses Programm)\n\n"
            "Der gewählte Hue-Bereich bleibt scharf und hell, alle anderen\n"
            "Bereiche werden geblurt und in ihrem HSV-Value abgesenkt.",
        )

    def on_quit(self) -> None:
        self._tmp_dir.cleanup()
        self.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description="Skintone Lab — GUI für das Rust-HSV-Experiment")
    parser.add_argument(
        "--binary",
        type=Path,
        default=None,
        help="Pfad zum skintone-lab-Binary (sonst: automatische Suche / SKINTONE_LAB_BIN)",
    )
    args = parser.parse_args()
    app = SkintoneApp(binary=args.binary)
    app.mainloop()


if __name__ == "__main__":
    main()
