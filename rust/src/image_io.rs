//! Laden und Speichern von Bildern über die `image`-Crate.
//!
//! Das Format wird anhand der Dateiendung bestimmt (PNG, JPEG, BMP, ...).
//! Geladen wird immer als RGB8 (Alphakanal wird verworfen), gespeichert
//! wird verlustfrei in PNG bzw. im zur Endung passenden Format.

use std::path::Path;

use image::{ImageError, RgbImage};

/// Lädt ein Bild von `path` und konvertiert es nach RGB8.
pub fn load_rgb(path: &Path) -> Result<RgbImage, ImageError> {
    // `image::open` erkennt das Format am Dateiinhalt, nicht an der Endung
    let img = image::open(path)?;
    Ok(img.to_rgb8())
}

/// Speichert `img` nach `path`; das Format ergibt sich aus der Endung
/// (z. B. `.png`). PNG ist verlustfrei und für Zwischenergebnisse ideal.
pub fn save_rgb(img: &RgbImage, path: &Path) -> Result<(), ImageError> {
    img.save(path)
}

#[cfg(test)]
mod tests {
    use super::*;
    use image::Rgb;

    #[test]
    fn speichern_und_laden_roundtrip() {
        // Eindeutiges Temp-Verzeichnis über die Prozess-ID (keine Zusatz-Crate nötig)
        let dir = std::env::temp_dir().join(format!("skintone-lab-io-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("roundtrip.png");

        let mut img = RgbImage::new(8, 8);
        for (i, p) in img.pixels_mut().enumerate() {
            *p = Rgb([i as u8, 255 - i as u8, 42]);
        }
        save_rgb(&img, &path).unwrap();
        assert!(path.exists());

        let loaded = load_rgb(&path).unwrap();
        assert_eq!(loaded.dimensions(), (8, 8));
        // PNG ist verlustfrei -> exakt gleiche Pixel
        for (a, b) in img.pixels().zip(loaded.pixels()) {
            assert_eq!(a.0, b.0);
        }

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn laden_einer_unsinnigen_datei_schlaegt_fehl() {
        let dir = std::env::temp_dir().join(format!("skintone-lab-io-bad-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("keinbild.png");
        std::fs::write(&path, b"das ist kein bild").unwrap();
        assert!(load_rgb(&path).is_err());
        let _ = std::fs::remove_dir_all(&dir);
    }
}
