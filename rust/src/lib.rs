//! # skintone-lab
//!
//! Bildverarbeitungsroutine für das Hautfarb-Experiment: Der User wählt einen
//! **Hue-Wert** (Farbton in Grad) und eine **Toleranz** (+/- in Grad). Alle
//! Pixel, deren Hue *nicht* in diesem Bereich liegt, werden **stark geblurt**
//! und in ihrem **HSV-Value heruntergesetzt**; der gewählte Farbbereich bleibt
//! scharf und hell.
//!
//! ## Module
//! - [`hsv`] — RGB ↔ HSV-Konvertierung und zirkulare Hue-Distanz
//! - [`blur`] — separabler Gaussian-Blur
//! - [`pipeline`] — Maske, Feather, Darken, Compositing (die eigentliche Routine)
//! - [`image_io`] — Bilder laden/speichern
//! - [`demo`] — synthetisches Demo-Portrait erzeugen
//!
//! ## Beispiel (Library)
//! ```
//! use skintone_lab::{demo::demo_portrait, pipeline::{process, PipelineParams}};
//!
//! // Synthetisches Portrait erzeugen und mit Hue 25° ± 20° verarbeiten
//! let bild = demo_portrait(320, 240);
//! let params = PipelineParams { hue: 25.0, tolerance: 20.0, ..Default::default() };
//! let ergebnis = process(&bild, params).unwrap();
//! assert_eq!(ergebnis.dimensions(), bild.dimensions());
//! ```

pub mod blur;
pub mod demo;
pub mod hsv;
pub mod image_io;
pub mod pipeline;
