# skintones

[![CI](https://github.com/DeepleMass/skintones/actions/workflows/ci.yml/badge.svg)](https://github.com/DeepleMass/skintones/actions/workflows/ci.yml)

> **English summary:** Skintone Lab is a small experiment in skin-tone-aware
> image processing. Load a portrait (file upload or webcam), choose a **hue**
> value and a **tolerance** (± degrees): the image is converted to HSV and every
> pixel outside your hue range is strongly blurred and darkened (lower HSV
> value), while the selected range stays sharp and bright. The pixel pipeline is
> a fully tested Rust library + CLI (`rust/`, binary `skintone-lab`); a
> Python/tkinter GUI (`python/`) drives it via subprocess — with sliders for
> hue/tolerance/blur/darken, a live color preview, a switchable
> horizontal/vertical layout and a light theme. CI (cargo fmt/clippy/test +
> Python unittests) runs on every push to `dev`; pushing a `v*` tag builds
> release binaries for Linux and macOS automatically (`.github/workflows/`).
> Sample images live in `sample-images/` (default: `default-image.jpg`).
>
> **Suggested GitHub "About" description (one line):**
> `Skintone Lab — HSV skin-tone selector: pick a hue ± tolerance, keep that range sharp, blur + darken the rest. Rust pipeline + Python/tkinter GUI.`
>
> **Suggested topics:** `rust` `python` `tkinter` `image-processing` `hsv` `computer-vision`

---

## Deutsch

Experimente mit Hautfarbtönen: Ein Bild (Datei oder Webcam) wird nach HSV
umgerechnet; der User wählt einen **Hue** und eine **Toleranz** — Pixel
außerhalb des Bereichs werden geblurt und in ihrem Value abgesenkt, der
gewählte Bereich bleibt scharf/hell.

## Aufbau

```
skintones/
├── .github/workflows/  # CI (fmt/clippy/test + Python-Tests) und Release-CD (Tags v*)
├── .gitignore          # ignoriert target/ (alle Binaries), out/, __pycache__/, *.pyc
├── rust/               # komplette Bildverarbeitungsroutine in Rust (Library + CLI), getestet
│   └── README.md
├── python/             # tkinter-GUI, steuert das Rust-Binary als Subprozess
│   └── README.md
└── sample-images/      # Beispielbilder, Default: default-image.jpg (GUI: "Beispielbild laden", Strg+B)
```

## Schnellstart

```bash
# 1. Rust-Binary bauen + testen
cd rust && cargo build --release && cargo test

# 2. Python-Abhängigkeiten installieren
cd ../python && pip install -r requirements.txt

# 3. GUI starten
python3 skintone_gui.py
# dann in der GUI: "Demo-Portrait" klicken und mit den Slidern spielen,
# oder eigenes Bild über "Bild laden …" öffnen
```

## Manuell ohne GUI

```bash
rust/target/release/skintone-lab demo --output /tmp/demo.png
rust/target/release/skintone-lab process --input /tmp/demo.png --output /tmp/out.png \
    --hue 25 --tolerance 20 --blur-sigma 8 --darken 0.6 --feather 2
```
