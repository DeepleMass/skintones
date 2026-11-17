//! Konvertierung zwischen dem RGB- und dem HSV-Farbraum sowie Hue-Hilfsfunktionen.
//!
//! Konventionen in diesem Modul:
//! - **Hue** wird in Grad im Bereich `[0, 360)` geführt.
//! - **Saturation** und **Value** werden als Anteil im Bereich `[0, 1]` geführt.
//!
//! Graustufen (S = 0) haben fachlich keinen definierten Hue; wir definieren
//! der Determinismus halber Hue = 0 für solche Pixel (siehe [`rgb_to_hsv`]).

/// Ein Farbwert im HSV-Farbraum.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Hsv {
    /// Farbton in Grad, immer im Bereich `[0, 360)`.
    pub h: f32,
    /// Sättigung als Anteil im Bereich `[0, 1]`.
    pub s: f32,
    /// Helligkeit (Value) als Anteil im Bereich `[0, 1]`.
    pub v: f32,
}

/// Wandelt einen einzelnen RGB-Pixel (Kanäle je `0..=255`) in HSV um.
///
/// Standard-Formel: `max`/`min`/`delta` über die normierten Kanäle,
/// Hue über den Sektor (R, G oder B dominant), S = delta / max, V = max.
pub fn rgb_to_hsv(r: u8, g: u8, b: u8) -> Hsv {
    // Kanäle auf [0, 1] normieren
    let r = r as f32 / 255.0;
    let g = g as f32 / 255.0;
    let b = b as f32 / 255.0;

    let max = r.max(g).max(b);
    let min = r.min(g).min(b);
    let delta = max - min;

    // Hue: welcher Kanal dominant ist, legt den 60°-Sektor fest.
    // Bei delta == 0 (reines Grau) ist der Hue undefiniert -> wir setzen 0.
    let h = if delta == 0.0 {
        0.0
    } else if max == r {
        60.0 * ((g - b) / delta).rem_euclid(6.0)
    } else if max == g {
        60.0 * ((b - r) / delta + 2.0)
    } else {
        60.0 * ((r - g) / delta + 4.0)
    };
    // In den Bereich [0, 360) bringen (rem_euclid erledigt auch negative Werte)
    let h = h.rem_euclid(360.0);

    // Sättigung: 0 bei Schwarz (max == 0 vermeidet Division durch 0)
    let s = if max == 0.0 { 0.0 } else { delta / max };

    Hsv { h, s, v: max }
}

/// Wandelt HSV zurück in einen RGB-Pixel (Kanäle je `0..=255`).
///
/// Eingaben werden robust behandelt: Hue wird per `rem_euclid(360)` gewrappt,
/// S und V werden auf `[0, 1]` begrenzt.
pub fn hsv_to_rgb(h: f32, s: f32, v: f32) -> (u8, u8, u8) {
    let h = h.rem_euclid(360.0);
    let s = s.clamp(0.0, 1.0);
    let v = v.clamp(0.0, 1.0);

    // Standard-Zerlegung: C = V*S (Chroma), X = Zwischenwert, m = V - C
    let c = v * s;
    let x = c * (1.0 - ((h / 60.0) % 2.0 - 1.0).abs());
    let m = v - c;

    // Sektor à 60° bestimmt die RGB-Rohwerte
    let (r, g, b) = match h {
        0.0..60.0 => (c, x, 0.0),
        60.0..120.0 => (x, c, 0.0),
        120.0..180.0 => (0.0, c, x),
        180.0..240.0 => (0.0, x, c),
        240.0..300.0 => (x, 0.0, c),
        _ => (c, 0.0, x),
    };

    // Auf [0, 255] skalieren und runden
    let to_u8 = |f: f32| (f + m).clamp(0.0, 1.0).mul_add(255.0, 0.5) as u8;
    (to_u8(r), to_u8(g), to_u8(b))
}

/// Zirkulare Distanz zweier Hue-Werte in Grad, Ergebnis in `[0, 180]`.
///
/// Der Farbkreis ist geschlossen: Hue 359 und Hue 1 liegen nur 2° auseinander.
/// Deshalb: `d = |a - b| mod 360`, und die kürzere Richtung gewinnt.
pub fn hue_distance(a: f32, b: f32) -> f32 {
    let d = (a - b).abs().rem_euclid(360.0);
    d.min(360.0 - d)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Hilfsfunktion: RGB -> HSV -> RGB muss (nahezu) wieder den Ausgangswert liefern.
    fn roundtrip(r: u8, g: u8, b: u8) -> (u8, u8, u8) {
        let hsv = rgb_to_hsv(r, g, b);
        hsv_to_rgb(hsv.h, hsv.s, hsv.v)
    }

    #[test]
    fn primaerfarben_haben_bekannte_hues() {
        assert_eq!(
            rgb_to_hsv(255, 0, 0),
            Hsv {
                h: 0.0,
                s: 1.0,
                v: 1.0
            }
        );
        let gruen = rgb_to_hsv(0, 255, 0);
        assert!((gruen.h - 120.0).abs() < 1e-4 && gruen.s == 1.0 && gruen.v == 1.0);
        let blau = rgb_to_hsv(0, 0, 255);
        assert!((blau.h - 240.0).abs() < 1e-4 && blau.s == 1.0 && blau.v == 1.0);
    }

    #[test]
    fn grau_und_schwarz_haben_definierte_werte() {
        // S = 0, V = Helligkeit; Hue ist per Konvention 0
        assert_eq!(
            rgb_to_hsv(255, 255, 255),
            Hsv {
                h: 0.0,
                s: 0.0,
                v: 1.0
            }
        );
        assert_eq!(
            rgb_to_hsv(0, 0, 0),
            Hsv {
                h: 0.0,
                s: 0.0,
                v: 0.0
            }
        );
        let grau = rgb_to_hsv(128, 128, 128);
        assert_eq!(grau.s, 0.0);
        assert!((grau.v - 128.0 / 255.0).abs() < 1e-4);
    }

    #[test]
    fn hue_liegt_immer_im_bereich_0_bis_360() {
        // Ein Pixel knapp unter dem Rot-Sektor (negativer Rohwert) darf nicht negativ werden
        let hsv = rgb_to_hsv(255, 0, 10);
        assert!((hsv.h - 357.6).abs() < 0.5, "hue war {}", hsv.h);
        assert!(hsv.h >= 0.0 && hsv.h < 360.0);
    }

    #[test]
    fn roundtrip_ist_stabil() {
        for &(r, g, b) in &[
            (255, 0, 0),
            (0, 255, 0),
            (0, 0, 255),
            (240, 200, 170), // heller Hautton
            (140, 90, 60),   // dunklerer Hautton
            (10, 20, 30),
            (200, 200, 200),
            (0, 0, 0),
        ] {
            let (r2, g2, b2) = roundtrip(r, g, b);
            assert!(
                r.abs_diff(r2) <= 1 && g.abs_diff(g2) <= 1 && b.abs_diff(b2) <= 1,
                "roundtrip({r},{g},{b}) -> ({r2},{g2},{b2})"
            );
        }
    }

    #[test]
    fn hue_distance_ist_zirkulaer() {
        assert_eq!(hue_distance(10.0, 20.0), 10.0);
        assert_eq!(hue_distance(20.0, 10.0), 10.0);
        // Wrap-Around am 0/360-Übergang: 359 und 1 sind nur 2° entfernt
        assert_eq!(hue_distance(359.0, 1.0), 2.0);
        assert_eq!(hue_distance(0.0, 180.0), 180.0);
        assert_eq!(hue_distance(350.0, 170.0), 180.0);
        // Gleicher Wert -> 0
        assert_eq!(hue_distance(123.0, 123.0), 0.0);
    }

    #[test]
    fn hsv_to_rgb_wrapped_hue_und_clamped() {
        // 360° == 0° (Rot)
        assert_eq!(hsv_to_rgb(360.0, 1.0, 1.0), (255, 0, 0));
        // Negative Hue-Werte werden gewrappt: -120° == 240° (Blau)
        assert_eq!(hsv_to_rgb(-120.0, 1.0, 1.0), (0, 0, 255));
        // S/V außerhalb [0,1] werden begrenzt statt zu explodieren
        assert_eq!(hsv_to_rgb(0.0, 5.0, 1.0), (255, 0, 0));
        assert_eq!(hsv_to_rgb(0.0, 1.0, -1.0), (0, 0, 0));
    }
}
