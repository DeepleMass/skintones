# Skintone Lab — Python-GUI

Grafische Oberfläche (tkinter, Python-Standardbibliothek) für das
Rust-Experiment in `../rust`. Die GUI macht **keine** Pixelverarbeitung selbst,
sondern ruft das Rust-Binary `skintone-lab` als Subprozess auf
(`rust_bridge.py` kapselt das).

## Dateien

```
python/
├── skintone_gui.py            # tkinter-App (Hauptprogramm)
├── rust_bridge.py             # Kommando-Aufbau, Validierung, Subprozess (testbar ohne Display)
├── tests/test_rust_bridge.py  # unittest: Validierung, CLI-Aufbau, echter Lauf gegen das Binary
├── tests/test_gui_helpers.py  # unittest: hue_to_hex, JSONC-Parser, Beispielbild-Suche, Layout
└── requirements.txt           # Pillow (Pflicht), opencv-python (optional, Webcam)
```

## Installation & Start

```bash
cd python
pip install -r requirements.txt          # Pillow
# optional nur für Webcam: pip install opencv-python

# Rust-Binary bauen (falls noch nicht geschehen):
cd ../rust && cargo build --release && cd ../python

# GUI starten:
python3 skintone_gui.py
# oder mit explizitem Binary-Pfad:
python3 skintone_gui.py --binary ../rust/target/release/skintone-lab
# (alternativ Umgebungsvariable SKINTONE_LAB_BIN setzen)
```

## Bedienung (Standard-Elemente)

- **Datei-Menü / Knöpfe:** Bild öffnen …, Beispielbild laden … (lädt das Default-Bild
  `skintones/sample-images/default-image.jpg`, konfigurierbar über
  `skintones.defaultSampleImage` in `.vscode/settings.json`; Fallback: erstes Bild
  aus `skintones.sampleImagesDir`), Demo-Portrait erzeugen
  (synthetisches Testbild direkt aus dem Rust-Binary), Webcam aufnehmen …
  (Frame via OpenCV), Verarbeiten, Zurücksetzen (Restart: Parameter auf
  Standard + neu rechnen), Ergebnis speichern unter …, Beenden.
  Tastenkürzel: Strg+O / Strg+B / Strg+W / Strg+S / Strg+Q.
- **Parameter-Leiste (links):** Hue (0–359°), Toleranz ± (0–180°), Blur-Sigma,
  Abdunkeln (%), Kante weichzeichnen — jeweils als Slider + Spinbox.
- **Farbvorschau:** Farbswatch + Anzeige „Hue x° ± y° · #rrggbb“ — zeigt den
  aktuell eingestellten Farbwert als Kontrolle (live bei jeder Änderung).
- **Layout-Umschalter:** Button „Layout wechseln (horizontal/vertikal)“ oder
  Menü Ansicht — Original und Ergebnis nebeneinander (horizontal) oder
  untereinander (vertikal), passend zum Seitenverhältnis.
- **Theme:** explizit hell (unabhängig vom System-Darkmode).
- **Auto-Vorschau:** Checkbox; wenn aktiv, wird nach jeder Parameter-Änderung
  sofort neu gerechnet (im Hintergrund-Thread, GUI bleibt bedienbar).
- **Bildbereiche (rechts):** Original vs. Ergebnis (Anordnung umschaltbar).
- **Statusleiste (unten):** letzte Aktion, Laufzeit des Rust-Laufs, Fehler.

## Tests

```bash
cd python
python3 -m unittest discover -s tests -v
```

Unit-Tests für Validierung und Kommando-Aufbau laufen immer; der
Integrationstest gegen das echte Rust-Binary wird automatisch übersprungen,
wenn das Binary noch nicht gebaut ist.

## Webcam-Hinweis

Ohne `opencv-python` erscheint beim Webcam-Knopf ein Hinweis; die Frame-Datei
wird ansonsten als normales PNG gespeichert und wie ein geladenes Bild
verarbeitet.
