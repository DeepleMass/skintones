//! Synthetisches Demo-"Portrait", damit das Experiment sofort ohne echtes
//! Foto ausprobiert werden kann (CLI: `skintone-lab demo --output demo.png`).
//!
//! Aufbau des Bildes (alles deterministisch, kein Zufall):
//! - Hintergrund: kühler Blauton (Hue ~210°) mit leichtem vertikalen Verlauf
//! - "Gesicht": Ellipse mit Hautfarb-Hue ~25°
//! - "Augen"/"Mund": kleine dunklere Kreise (liegen hue-mäßig nah am Gesicht)

use image::{Rgb, RgbImage};

use crate::hsv::hsv_to_rgb;

/// Erzeugt ein synthetisches Portrait der Größe `width` x `height`.
pub fn demo_portrait(width: u32, height: u32) -> RgbImage {
    let mut img = RgbImage::new(width, height);

    // Ellipsen-Maße relativ zur Bildgröße (Gesicht in der Mitte)
    let cx = width as f32 / 2.0;
    let cy = height as f32 / 2.0;
    let rx = width as f32 * 0.28; // Gesichts-Halbachse x
    let ry = height as f32 * 0.36; // Gesichts-Halbachse y

    for y in 0..height {
        for x in 0..width {
            let (xf, yf) = (x as f32, y as f32);

            // Hintergrund: Blauton mit vertikalem Helligkeitsverlauf (oben heller)
            let bg_v = 0.55 + 0.25 * (1.0 - yf / height as f32);
            let mut rgb = hsv_to_rgb(210.0, 0.45, bg_v);

            // Gesicht: Ellipsengleichung <= 1 liegt innen
            let dx = (xf - cx) / rx;
            let dy = (yf - cy) / ry;
            if dx * dx + dy * dy <= 1.0 {
                // Hautton: Hue 25°, leichte Schattierung nach unten
                let v = 0.9 - 0.25 * (dy + 1.0) / 2.0;
                rgb = hsv_to_rgb(25.0, 0.45, v);
            }

            // Augen: zwei Kreise im oberen Drittel des Gesichts
            for eye_x in [cx - rx * 0.4, cx + rx * 0.4] {
                let ex = (xf - eye_x) / (rx * 0.12);
                let ey = (yf - (cy - ry * 0.3)) / (ry * 0.12);
                if ex * ex + ey * ey <= 1.0 {
                    rgb = hsv_to_rgb(20.0, 0.5, 0.15); // dunkelbraun
                }
            }

            // Mund: breitere, flache Ellipse im unteren Drittel
            let mx = (xf - cx) / (rx * 0.35);
            let my = (yf - (cy + ry * 0.55)) / (ry * 0.08);
            if mx * mx + my * my <= 1.0 {
                rgb = hsv_to_rgb(15.0, 0.6, 0.35);
            }

            img.put_pixel(x, y, Rgb([rgb.0, rgb.1, rgb.2]));
        }
    }
    img
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hsv::rgb_to_hsv;

    #[test]
    fn demo_bild_hat_gesicht_und_hintergrund() {
        let img = demo_portrait(200, 200);
        assert_eq!(img.dimensions(), (200, 200));
        // Mitte = Gesicht -> Hue nahe 25°
        let center = img.get_pixel(100, 100);
        let hsv = rgb_to_hsv(center[0], center[1], center[2]);
        assert!(
            (hsv.h - 25.0).abs() < 10.0,
            "Gesichts-Hue war {} (s={}, v={})",
            hsv.h,
            hsv.s,
            hsv.v
        );
        // Ecke = Hintergrund -> Hue nahe 210°
        let corner = img.get_pixel(2, 2);
        let hsv_bg = rgb_to_hsv(corner[0], corner[1], corner[2]);
        assert!(
            (hsv_bg.h - 210.0).abs() < 10.0,
            "Hintergrund-Hue war {}",
            hsv_bg.h
        );
    }
}
