//! Die eigentliche Bildverarbeitungs-Pipeline des Experiments.
//!
//! Ablauf (siehe auch README.md):
//! 1. Jedes Pixel RGB -> HSV; Treffer-Maske über zirkulare Hue-Distanz (`hue ± tolerance`).
//! 2. Maske weichzeichnen ("Feather"), damit die Kante nicht hart aussieht.
//! 3. Hintergrund erzeugen: komplettes Bild gaussian-blurren und danach den
//!    HSV-Value um den Faktor `(1 - darken)` absenken.
//! 4. Compositing: `out = maske * original + (1 - maske) * hintergrund`.

use image::{Rgb, RgbImage};

use crate::blur::gaussian_blur;
use crate::hsv::{hsv_to_rgb, hue_distance, rgb_to_hsv};

/// Alle Parameter der Pipeline an einer Stelle.
///
/// Wertebereiche (werden von [`PipelineParams::validate`] geprüft):
/// - `hue`: Grad, wird auf `[0, 360)` gewrappt (z. B. 370 -> 10)
/// - `tolerance`: Grad, muss in `[0, 180]` liegen
/// - `blur_sigma`: Pixel, `[0, 100]` (0 = kein Blur)
/// - `darken`: Anteil `[0, 1]` — 0.6 dunkelt den Value auf 40 % ab
/// - `feather`: Pixel, `[0, 64]` — Radius zum Weichzeichnen der Maskenkante
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PipelineParams {
    /// Ziel-Hue in Grad (Mitte des gewünschten Farbbereichs).
    pub hue: f32,
    /// Erlaubte Abweichung +/- in Grad um `hue`.
    pub tolerance: f32,
    /// Sigma des Gaussian-Blur für Nicht-Treffer (in Pixeln).
    pub blur_sigma: f32,
    /// Anteil, um den der HSV-Value der Nicht-Treffer abgesenkt wird.
    pub darken: f32,
    /// Radius, mit dem die Treffer-Maske weichgezeichnet wird (in Pixeln).
    pub feather: f32,
}

impl Default for PipelineParams {
    /// Sinnvolle Startwerte für Hautfarbtöne (Hue ca. 20–30°).
    fn default() -> Self {
        Self {
            hue: 25.0,
            tolerance: 20.0,
            blur_sigma: 8.0,
            darken: 0.6,
            feather: 2.0,
        }
    }
}

impl PipelineParams {
    /// Prüft die Wertebereiche und gibt eine normalisierte Kopie zurück.
    ///
    /// `hue` wird gewrappt (ist also immer gültig), die übrigen Werte müssen
    /// im dokumentierten Bereich liegen, sonst kommt ein Fehler mit Klartext.
    pub fn validate(self) -> Result<Self, String> {
        let mut p = self;
        p.hue = p.hue.rem_euclid(360.0);
        if !p.hue.is_finite() {
            return Err("hue darf nicht NaN sein".into());
        }
        if !(0.0..=180.0).contains(&p.tolerance) || !p.tolerance.is_finite() {
            return Err(format!(
                "tolerance muss in [0, 180] liegen, war {}",
                self.tolerance
            ));
        }
        if !(0.0..=100.0).contains(&p.blur_sigma) || !p.blur_sigma.is_finite() {
            return Err(format!(
                "blur_sigma muss in [0, 100] liegen, war {}",
                self.blur_sigma
            ));
        }
        if !(0.0..=1.0).contains(&p.darken) || !p.darken.is_finite() {
            return Err(format!("darken muss in [0, 1] liegen, war {}", self.darken));
        }
        if !(0.0..=64.0).contains(&p.feather) || !p.feather.is_finite() {
            return Err(format!(
                "feather muss in [0, 64] liegen, war {}",
                self.feather
            ));
        }
        Ok(p)
    }
}

/// Baut die Treffer-Maske: `1.0` für Pixel, deren Hue innerhalb
/// `hue ± tolerance` liegt, sonst `0.0`.
///
/// Die Distanz wird zirkular berechnet (siehe [`hue_distance`]), damit ein
/// Bereich über 0/360° (z. B. hue=350, tolerance=20) korrekt funktioniert.
pub fn match_mask(img: &RgbImage, hue: f32, tolerance: f32) -> Vec<f32> {
    img.pixels()
        .map(|p| {
            let hsv = rgb_to_hsv(p[0], p[1], p[2]);
            if hue_distance(hsv.h, hue) <= tolerance {
                1.0
            } else {
                0.0
            }
        })
        .collect()
}

/// Weichzeichnung der Maske per Box-Blur (horizontal + vertikal) auf `f32`-Werten.
///
/// Dadurch werden die Kanten zwischen "Original bleibt stehen" und "Hintergrund
/// wird geblurt" weich. `radius = 0` tut nichts. Ränder per clamp behandeln.
pub fn feather_mask(mask: &mut [f32], width: u32, height: u32, radius: u32) {
    if radius == 0 || mask.len() != (width * height) as usize {
        return;
    }
    let w = width as i32;
    let h = height as i32;
    let r = radius as i32;
    let mut tmp = vec![0.0f32; mask.len()];

    // Horizontal
    for y in 0..h {
        for x in 0..w {
            let mut sum = 0.0;
            for k in -r..=r {
                let sx = (x + k).clamp(0, w - 1);
                sum += mask[(y * w + sx) as usize];
            }
            tmp[(y * w + x) as usize] = sum / (2 * r + 1) as f32;
        }
    }
    // Vertikal
    for y in 0..h {
        for x in 0..w {
            let mut sum = 0.0;
            for k in -r..=r {
                let sy = (y + k).clamp(0, h - 1);
                sum += tmp[(sy * w + x) as usize];
            }
            mask[(y * w + x) as usize] = sum / (2 * r + 1) as f32;
        }
    }
}

/// Senkt den HSV-Value jedes Pixels um den Anteil `darken` ab
/// (z. B. `darken = 0.6` lässt 40 % der Helligkeit übrig).
///
/// Im Gegensatz zu einer einfachen RGB-Multiplikation bleibt so der Hue des
/// Pixels erhalten — der Hintergrund sieht "gedimmt", nicht "verfärbt" aus.
pub fn darken_value(img: &RgbImage, darken: f32) -> RgbImage {
    let keep = 1.0 - darken.clamp(0.0, 1.0);
    let (w, h) = img.dimensions();
    let mut out = RgbImage::new(w, h);
    for (dst, src) in out.pixels_mut().zip(img.pixels()) {
        let hsv = rgb_to_hsv(src[0], src[1], src[2]);
        let (r, g, b) = hsv_to_rgb(hsv.h, hsv.s, hsv.v * keep);
        *dst = Rgb([r, g, b]);
    }
    out
}

/// Führt die komplette Pipeline aus und liefert das Ergebnisbild.
///
/// Die Parameter werden vorher via [`PipelineParams::validate`] geprüft;
/// bei ungültigen Werten kommt ein Fehler (statt eines stillen Ergebnisses).
pub fn process(img: &RgbImage, params: PipelineParams) -> Result<RgbImage, String> {
    let p = params.validate()?;
    let (w, h) = img.dimensions();
    if w == 0 || h == 0 {
        return Err("Eingabebild ist leer".into());
    }

    // 1. Treffer-Maske aus dem Hue-Abstand
    let mut mask = match_mask(img, p.hue, p.tolerance);

    // 2. Maskenkanten weichzeichnen
    if p.feather > 0.0 {
        feather_mask(&mut mask, w, h, p.feather.round() as u32);
    }

    // 3. Hintergrund: komplettes Bild blurren, dann Value absenken
    let blurred = gaussian_blur(img, p.blur_sigma);
    let background = darken_value(&blurred, p.darken);

    // 4. Compositing: Treffer keep original, Rest bekommt den Hintergrund
    let mut out = RgbImage::new(w, h);
    for y in 0..h {
        for x in 0..w {
            let i = (y * w + x) as usize;
            let m = mask[i];
            let orig = img.get_pixel(x, y);
            let bg = background.get_pixel(x, y);
            let mut px = [0u8; 3];
            for c in 0..3 {
                px[c] = (m * orig[c] as f32 + (1.0 - m) * bg[c] as f32)
                    .round()
                    .clamp(0.0, 255.0) as u8;
            }
            out.put_pixel(x, y, Rgb(px));
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Baut ein Bild, dessen linke Hälfte Hue 0 (Rot) und rechte Hälfte Hue 120
    /// (Grün) hat — klar getrennte Farbbereiche für aussagekräftige Tests.
    fn two_hue_image(w: u32, h: u32) -> RgbImage {
        let mut img = RgbImage::new(w, h);
        for y in 0..h {
            for x in 0..w {
                let (r, g, b) = if x < w / 2 {
                    hsv_to_rgb(0.0, 0.8, 0.9)
                } else {
                    hsv_to_rgb(120.0, 0.8, 0.9)
                };
                img.put_pixel(x, y, Rgb([r, g, b]));
            }
        }
        img
    }

    #[test]
    fn validate_wrappt_hue_und_prueft_bereiche() {
        let p = PipelineParams {
            hue: 370.0,
            ..Default::default()
        }
        .validate()
        .unwrap();
        assert!((p.hue - 10.0).abs() < 1e-6);

        let bad = PipelineParams {
            tolerance: 181.0,
            ..Default::default()
        };
        assert!(bad.validate().is_err());
        let bad = PipelineParams {
            darken: 1.5,
            ..Default::default()
        };
        assert!(bad.validate().is_err());
        let bad = PipelineParams {
            blur_sigma: -1.0,
            ..Default::default()
        };
        assert!(bad.validate().is_err());
        let bad = PipelineParams {
            hue: f32::NAN,
            ..Default::default()
        };
        assert!(bad.validate().is_err());
    }

    #[test]
    fn maske_trennt_hue_bereiche() {
        let (w, h) = (20u32, 10u32);
        let img = two_hue_image(w, h);
        let mask = match_mask(&img, 0.0, 10.0);
        // Zeile-major flach abgelegt: pro Pixel anhand der x-Koordinate prüfen
        for y in 0..h {
            for x in 0..w {
                let m = mask[(y * w + x) as usize];
                if x < w / 2 {
                    assert_eq!(m, 1.0, "Pixel ({x},{y}) mit Hue 0 muss Treffer sein");
                } else {
                    assert_eq!(m, 0.0, "Pixel ({x},{y}) mit Hue 120 darf kein Treffer sein");
                }
            }
        }
    }

    #[test]
    fn maske_respektiert_wrap_around() {
        // Ziel-Hue 350 mit Toleranz 20 umfasst 330..360 und 0..10
        let mut img = RgbImage::new(2, 1);
        let (r1, g1, b1) = hsv_to_rgb(355.0, 0.8, 0.9); // im Bereich
        let (r2, g2, b2) = hsv_to_rgb(180.0, 0.8, 0.9); // außerhalb
        img.put_pixel(0, 0, Rgb([r1, g1, b1]));
        img.put_pixel(1, 0, Rgb([r2, g2, b2]));
        let mask = match_mask(&img, 350.0, 20.0);
        assert_eq!(mask, vec![1.0, 0.0]);
    }

    #[test]
    fn feather_macht_harte_kante_weicher() {
        let w = 20;
        let h = 1;
        let mut mask = vec![0.0f32; (w * h) as usize];
        for x in 0..w / 2 {
            mask[x as usize] = 1.0;
        }
        let hart = mask.clone();
        feather_mask(&mut mask, w, h, 2);
        // In der Mitte bleibt 1.0/0.0, an der Kante entstehen Zwischenwerte
        assert_eq!(mask[0], 1.0);
        assert_eq!(mask[(w - 1) as usize], 0.0);
        assert!(mask[(w / 2 - 1) as usize] < 1.0 && mask[(w / 2 - 1) as usize] > 0.0);
        assert_ne!(mask, hart);
        // radius 0 ändert nichts
        let mut m2 = hart.clone();
        feather_mask(&mut m2, w, h, 0);
        assert_eq!(m2, hart);
    }

    #[test]
    fn darken_value_haelt_hue_und_senkt_value() {
        let (r, g, b) = hsv_to_rgb(30.0, 0.6, 1.0);
        let img = RgbImage::from_pixel(1, 1, Rgb([r, g, b]));
        let out = darken_value(&img, 0.5);
        let hsv_in = rgb_to_hsv(r, g, b);
        let hsv_out = rgb_to_hsv(
            out.get_pixel(0, 0)[0],
            out.get_pixel(0, 0)[1],
            out.get_pixel(0, 0)[2],
        );
        // Hue bleibt (annähernd) gleich, Value halbiert sich
        assert!(hue_distance(hsv_in.h, hsv_out.h) < 1.0);
        assert!((hsv_out.v - 0.5).abs() < 0.02, "v war {}", hsv_out.v);
        // darken = 0 ändert nichts
        let same = darken_value(&img, 0.0);
        assert_eq!(same.get_pixel(0, 0)[0], r);
    }

    #[test]
    fn pipeline_haelt_treffer_und_dunkelt_nicht_treffer() {
        let img = two_hue_image(40, 20);
        let params = PipelineParams {
            hue: 0.0,
            tolerance: 10.0,
            blur_sigma: 0.0, // Blur aus, damit Darken direkt messbar ist
            darken: 0.8,
            feather: 0.0,
        };
        let out = process(&img, params).unwrap();

        // Linker Bereich (Treffer): bleibt original
        let orig = img.get_pixel(5, 10);
        let kept = out.get_pixel(5, 10);
        assert!(
            kept[0].abs_diff(orig[0]) <= 1
                && kept[1].abs_diff(orig[1]) <= 1
                && kept[2].abs_diff(orig[2]) <= 1
        );

        // Rechter Bereich (Nicht-Treffer): deutlich dunkler (Value auf 20 %)
        let bg = out.get_pixel(35, 10);
        let orig_bg = img.get_pixel(35, 10);
        let v_in = rgb_to_hsv(orig_bg[0], orig_bg[1], orig_bg[2]).v;
        let v_out = rgb_to_hsv(bg[0], bg[1], bg[2]).v;
        assert!(v_out < v_in * 0.35, "v_in={v_in} v_out={v_out}");
    }

    #[test]
    fn pipeline_mit_toleranz_180_nimmt_alles() {
        let img = two_hue_image(10, 10);
        let params = PipelineParams {
            hue: 0.0,
            tolerance: 180.0,
            darken: 1.0,
            ..Default::default()
        };
        let out = process(&img, params).unwrap();
        // Jeder Pixel ist Treffer -> Ergebnis == Original
        for (a, b) in img.pixels().zip(out.pixels()) {
            assert!(
                a[0].abs_diff(b[0]) <= 1 && a[1].abs_diff(b[1]) <= 1 && a[2].abs_diff(b[2]) <= 1
            );
        }
    }

    #[test]
    fn pipeline_lehnt_unglueltige_parameter_ab() {
        let img = RgbImage::new(4, 4);
        let bad = PipelineParams {
            tolerance: 200.0,
            ..Default::default()
        };
        assert!(process(&img, bad).is_err());
    }
}
