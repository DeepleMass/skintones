# skintone-lab (Rust)

Bildverarbeitungsroutine für das Hautfarb-Experiment: Der User wählt einen
**Hue-Wert** (Farbton in Grad) und eine **Toleranz** (+/- in Grad). Alle Pixel,
deren Hue *nicht* in `hue ± tolerance` liegt, werden **stark geblurt** und in
ihrem **HSV-Value heruntergesetzt**. Der gewählte Farbbereich bleibt scharf und
hell. Das Ergebnis wird gespeichert/angezeigt (die Anzeige macht die
Python-GUI in `../python`).

## Projektstruktur

```
rust/
├── Cargo.toml                  # Abhängigkeiten: image (I/O), clap (CLI)
├── src/
│   ├── lib.rs                  # Crate-Dokumentation + Doctest, re-exportiert die Module
│   ├── hsv.rs                  # RGB <-> HSV, zirkulare Hue-Distanz (Unit-Tests)
│   ├── blur.rs                 # separabler Gaussian-Blur (Unit-Tests)
│   ├── pipeline.rs             # Maske, Feather, Darken, Compositing (Unit-Tests)
│   ├── image_io.rs             # Bilder laden/speichern via `image`-Crate (Unit-Tests)
│   ├── demo.rs                 # synthetisches Demo-Portrait (Unit-Test)
│   └── main.rs                 # CLI: `process` und `demo`
└── tests/
    ├── cli_integration.rs      # End-to-End über das kompilierte Binary
    └── pipeline_integration.rs # End-to-End auf Library-Ebene inkl. PNG-Roundtrip
```

Der gesamte Code ist kommentiert (deutsch), alle öffentlichen Items tragen
Doc-Kommentare (`cargo doc --open` erzeugt die Doku).

## Verarbeitungs-Pipeline (Schritt für Schritt)

1. **RGB → HSV** pro Pixel (`hsv::rgb_to_hsv`). Hue in Grad `[0, 360)`,
   Saturation/Value in `[0, 1]`. Graustufen (S = 0) haben keinen definierten
   Hue; Konvention: Hue = 0.
2. **Treffer-Maske** (`pipeline::match_mask`): Pixel ist Treffer, wenn die
   *zirkulare* Hue-Distanz `min(|a-b| mod 360, 360 - |a-b| mod 360)` kleiner
   gleich der Toleranz ist. Dadurch funktioniert ein Bereich über 0/360°
   (z. B. hue = 350, tolerance = 20) korrekt.
3. **Feather**: Die binäre Maske wird per Box-Blur weichgezeichnet, damit die
   Kante zwischen Original und Hintergrund nicht hart aussieht.
4. **Hintergrund**: Das komplette Bild wird mit einem separablen
   Gaussian-Blur (`blur::gaussian_blur`, Sigma als Parameter) unscharf
   gerechnet; danach wird der HSV-Value jedes Pixels mit `(1 - darken)`
   skaliert (`pipeline::darken_value`). Im HSV-Raum dunkelt man ab, damit der
   Hue des Hintergrunds erhalten bleibt (gedimmt statt verfärbt).
5. **Compositing** pro Kanal: `out = m·original + (1−m)·hintergrund`
   mit der Maske `m`.

## Parameter

| Parameter     | Bedeutung                                   | Bereich      | Default |
|---------------|---------------------------------------------|--------------|---------|
| `hue`         | Ziel-Hue in Grad (Mitte des Bereichs)       | wird auf `[0,360)` gewrappt | 25 |
| `tolerance`   | erlaubte Abweichung +/- in Grad             | `[0, 180]`   | 20      |
| `blur_sigma`  | Sigma des Gaussian-Blur für Nicht-Treffer   | `[0, 100]` px | 8       |
| `darken`      | Anteil, um den der Value abgesenkt wird     | `[0, 1]`     | 0.6     |
| `feather`     | Radius zum Weichzeichnen der Maskenkante    | `[0, 64]` px | 2       |

## Bauen, testen, ausführen

```bash
cd rust
cargo build --release        # Binary: target/release/skintone-lab
cargo test                   # 22 Unit-Tests + 6 Integrationstests + 1 Doctest
cargo doc --open             # Doku

# Demo-Portrait erzeugen und sofort verarbeiten:
./target/release/skintone-lab demo --output /tmp/demo.png --width 640 --height 480
./target/release/skintone-lab process \
    --input /tmp/demo.png --output /tmp/ergebnis.png \
    --hue 25 --tolerance 20 --blur-sigma 8 --darken 0.6 --feather 2
```

`process` gibt auf stdout eine maschinenlesbare Zeile aus
(`OK output=… width=… height=… elapsed_ms=…`), Fehler gehen nach stderr mit
Exit-Code 2. Das Python-GUI parst diese Zeile.

## Library-Beispiel

```rust
use skintone_lab::{demo::demo_portrait, pipeline::{process, PipelineParams}};

let bild = demo_portrait(640, 480);
let params = PipelineParams { hue: 25.0, tolerance: 20.0, ..Default::default() };
let ergebnis = process(&bild, params).unwrap();
skintone_lab::image_io::save_rgb(&ergebnis, std::path::Path::new("/tmp/out.png")).unwrap();
```

## Tests

- **Unit-Tests** in jedem Modul (`cargo test --lib`): HSV-Konvertierung und
  Roundtrip, zirkulare Hue-Distanz, Gauß-Kernel (Summe = 1, symmetrisch),
  Blur-Eigenschaften, Maske inkl. Wrap-Around, Feather, Darken, Pipeline auf
  synthetischen Zwei-Hue-Bildern, IO-Roundtrip.
- **Integrationstests** (`tests/`): komplettes Binary via
  `CARGO_BIN_EXE_skintone-lab` — `demo` → `process` → Datei- und Pixel-Prüfung,
  Fehlerfälle (ungültige Toleranz, fehlende Datei → Exit-Code 2), Hue-Wrap in
  der CLI; sowie Library-End-to-End inkl. PNG-Speicher-/Lade-Roundtrip.
- **Doctest** in `lib.rs`.
