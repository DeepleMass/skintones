//! Bildunschärfe (Blur) als separabler Gaussian-Filter.
//!
//! Statt eines teuren 2D-Filters wird der Gauß-Kernel zweimal 1-dimensional
//! angewendet (erst horizontal, dann vertikal). Das ist bei gleicher Qualität
//! deutlich schneller: O(w·h·r) statt O(w·h·r²).
//!
//! Ränder werden per "clamp" behandelt: Pixel außerhalb des Bildes gelten als
//! Kopie des nächsten Randpixels.

use image::{Rgb, RgbImage};

/// Erzeugt einen normalisierten 1D-Gauß-Kernel für das gegebene `sigma`.
///
/// - `sigma <= 0` liefert den Kernel `[1.0]` (keine Unschärfe).
/// - Der Radius wird als `3·sigma` gewählt (99,7 % der Gauß-Glocke abgedeckt).
/// - Die Summe der Gewichte ist danach exakt 1, damit die Helligkeit erhalten bleibt.
pub fn gaussian_kernel(sigma: f32) -> Vec<f32> {
    if sigma <= 0.0 {
        return vec![1.0];
    }
    let radius = (sigma * 3.0).ceil().max(1.0) as i32;
    let mut kernel = Vec::with_capacity((2 * radius + 1) as usize);
    let norm = 1.0 / (2.0 * std::f32::consts::PI * sigma * sigma).sqrt();
    let mut sum = 0.0;
    for i in -radius..=radius {
        let w = norm * (-(i as f32 * i as f32) / (2.0 * sigma * sigma)).exp();
        kernel.push(w);
        sum += w;
    }
    // Normalisieren (numerische Abweichungen ausgleichen)
    for w in kernel.iter_mut() {
        *w /= sum;
    }
    kernel
}

/// Wendet einen 1D-Kernel horizontal auf `src` an und schreibt nach `dst`.
fn blur_horizontal(src: &RgbImage, dst: &mut RgbImage, kernel: &[f32]) {
    let (w, h) = src.dimensions();
    let radius = (kernel.len() as i32 - 1) / 2;
    for y in 0..h {
        for x in 0..w {
            let mut acc = [0.0f32; 3];
            for (k, weight) in kernel.iter().enumerate() {
                // clamp: außerhalb liegende Pixel = nächster Randpixel
                let sx = (x as i32 + k as i32 - radius).clamp(0, w as i32 - 1) as u32;
                let p = src.get_pixel(sx, y);
                acc[0] += weight * p[0] as f32;
                acc[1] += weight * p[1] as f32;
                acc[2] += weight * p[2] as f32;
            }
            dst.put_pixel(
                x,
                y,
                Rgb([
                    acc[0].round().clamp(0.0, 255.0) as u8,
                    acc[1].round().clamp(0.0, 255.0) as u8,
                    acc[2].round().clamp(0.0, 255.0) as u8,
                ]),
            );
        }
    }
}

/// Wendet einen 1D-Kernel vertikal auf `src` an und schreibt nach `dst`.
fn blur_vertical(src: &RgbImage, dst: &mut RgbImage, kernel: &[f32]) {
    let (w, h) = src.dimensions();
    let radius = (kernel.len() as i32 - 1) / 2;
    for y in 0..h {
        for x in 0..w {
            let mut acc = [0.0f32; 3];
            for (k, weight) in kernel.iter().enumerate() {
                let sy = (y as i32 + k as i32 - radius).clamp(0, h as i32 - 1) as u32;
                let p = src.get_pixel(x, sy);
                acc[0] += weight * p[0] as f32;
                acc[1] += weight * p[1] as f32;
                acc[2] += weight * p[2] as f32;
            }
            dst.put_pixel(
                x,
                y,
                Rgb([
                    acc[0].round().clamp(0.0, 255.0) as u8,
                    acc[1].round().clamp(0.0, 255.0) as u8,
                    acc[2].round().clamp(0.0, 255.0) as u8,
                ]),
            );
        }
    }
}

/// Gaussian-Unschärfe eines RGB-Bildes mit Standardabweichung `sigma` (in Pixeln).
///
/// `sigma <= 0` liefert eine Kopie des Originals. Die Implementierung ist
/// separabel (horizontal + vertikal) und damit deutlich schneller als ein 2D-Filter.
pub fn gaussian_blur(img: &RgbImage, sigma: f32) -> RgbImage {
    if sigma <= 0.0 {
        return img.clone();
    }
    let (w, h) = img.dimensions();
    let kernel = gaussian_kernel(sigma);
    // Erster Durchlauf: horizontal in einen Puffer ...
    let mut tmp = RgbImage::new(w, h);
    blur_horizontal(img, &mut tmp, &kernel);
    // ... zweiter Durchlauf: vertikal ins Ergebnis
    let mut out = RgbImage::new(w, h);
    blur_vertical(&tmp, &mut out, &kernel);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn kernel_ist_normalisiert_und_symmetrisch() {
        let k = gaussian_kernel(2.5);
        let sum: f32 = k.iter().sum();
        assert!((sum - 1.0).abs() < 1e-6, "Summe war {sum}");
        for i in 0..k.len() {
            assert!(
                (k[i] - k[k.len() - 1 - i]).abs() < 1e-7,
                "asymmetrisch bei {i}"
            );
        }
        // Maximum in der Mitte
        let mid = k.len() / 2;
        assert!(k[mid] == k.iter().cloned().fold(f32::MIN, f32::max));
    }

    #[test]
    fn kernel_bei_sigma_0_ist_neutral() {
        assert_eq!(gaussian_kernel(0.0), vec![1.0]);
        assert_eq!(gaussian_kernel(-3.0), vec![1.0]);
    }

    #[test]
    fn konstantes_bild_bleibt_konstant() {
        let img = RgbImage::from_pixel(17, 9, Rgb([100, 150, 200]));
        let out = gaussian_blur(&img, 5.0);
        for p in out.pixels() {
            // Erlaubt eine Abweichung von 1 durch Rundung an den Rändern
            assert!(p[0].abs_diff(100) <= 1 && p[1].abs_diff(150) <= 1 && p[2].abs_diff(200) <= 1);
        }
    }

    #[test]
    fn blur_macht_impuls_weicher() {
        // Einzelner heller Punkt in der Mitte eines schwarzen Bildes
        let mut img = RgbImage::from_pixel(21, 21, Rgb([0, 0, 0]));
        img.put_pixel(10, 10, Rgb([255, 255, 255]));
        let out = gaussian_blur(&img, 2.0);
        // Der Impuls ist auseinandergezogen: Zentrum heller als Rand, Nachbarn > 0
        let center = out.get_pixel(10, 10);
        let nachbar = out.get_pixel(11, 10);
        let ecke = out.get_pixel(0, 0);
        assert!(center[0] < 255, "Zentrum muss dunkler als 255 sein");
        assert!(nachbar[0] > 0, "Nachbar muss angehoben sein");
        assert!(ecke[0] < nachbar[0], "Ecke muss dunkler als Nachbar sein");
        // Gesamthelligkeit bleibt näherungsweise erhalten (Kernel-Summe = 1)
        let sum_in: u64 = img.pixels().map(|p| p[0] as u64).sum();
        let sum_out: u64 = out.pixels().map(|p| p[0] as u64).sum();
        let diff = sum_in.abs_diff(sum_out);
        assert!(
            diff < sum_in / 10,
            "Helligkeit driftet: {sum_in} -> {sum_out}"
        );
    }

    #[test]
    fn sigma_0_gibt_kopie_zurueck() {
        let img = RgbImage::from_pixel(4, 4, Rgb([1, 2, 3]));
        let out = gaussian_blur(&img, 0.0);
        assert_eq!(out.get_pixel(0, 0)[0], 1);
        assert_eq!(out.dimensions(), img.dimensions());
    }
}
