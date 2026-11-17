//! Integrationstests auf Library-Ebene: synthetisches Bild -> Pipeline ->
//! inhaltliche Prüfung des Ergebnisses (ohne CLI, dafür mit echten Bildern
//! über image_io, inkl. PNG-Roundtrip).

use skintone_lab::demo::demo_portrait;
use skintone_lab::hsv::rgb_to_hsv;
use skintone_lab::image_io::{load_rgb, save_rgb};
use skintone_lab::pipeline::{process, PipelineParams};

#[test]
fn komplettes_demo_szenario_ueber_dateien() {
    let dir = std::env::temp_dir().join(format!("skintone-lab-pipe-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let in_path = dir.join("in.png");
    let out_path = dir.join("out.png");

    // Synthetisches Portrait erzeugen, als PNG speichern, wieder laden
    let original = demo_portrait(240, 180);
    save_rgb(&original, &in_path).unwrap();
    let loaded = load_rgb(&in_path).unwrap();
    assert_eq!(loaded.dimensions(), (240, 180));

    // Pipeline: Hautfarb-Hue 25° ± 20°
    let params = PipelineParams {
        hue: 25.0,
        tolerance: 20.0,
        blur_sigma: 5.0,
        darken: 0.7,
        feather: 2.0,
    };
    let result = process(&loaded, params).unwrap();
    save_rgb(&result, &out_path).unwrap();
    let reloaded = load_rgb(&out_path).unwrap();

    // Abmessungen bleiben erhalten
    assert_eq!(reloaded.dimensions(), (240, 180));

    // Gesicht (Bildmitte) bleibt hue-stabil und deutlich heller als der Hintergrund
    let face = reloaded.get_pixel(120, 90);
    let bg = reloaded.get_pixel(3, 3);
    let face_hsv = rgb_to_hsv(face[0], face[1], face[2]);
    let bg_hsv = rgb_to_hsv(bg[0], bg[1], bg[2]);
    assert!((face_hsv.h - 25.0).abs() < 20.0, "face hue {}", face_hsv.h);
    assert!(
        face_hsv.v > bg_hsv.v + 0.15,
        "Gesicht (v={}) muss heller sein als Hintergrund (v={})",
        face_hsv.v,
        bg_hsv.v
    );

    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn toleranz_null_nimmt_nur_exakten_hue() {
    // Primärfarben haben exakt darstellbare Hues (Rot = 0°, Grün = 120°),
    // deshalb ist bei tolerance = 0 ein exakter Vergleich sinnvoll.
    let params = PipelineParams {
        hue: 0.0,
        tolerance: 0.0,
        blur_sigma: 0.0,
        darken: 1.0, // maximal abdunkeln, leicht messbar
        feather: 0.0,
    };
    // Reines Rot (Hue exakt 0) bleibt mit tolerance 0 erhalten
    let red = image::RgbImage::from_pixel(1, 1, image::Rgb([255, 0, 0]));
    let out_red = process(&red, params).unwrap();
    let p = out_red.get_pixel(0, 0);
    assert_eq!(p.0, [255, 0, 0], "rotes Pixel muss exakt erhalten bleiben");
    // Reines Grün (Hue 120) wird mit darken=1 komplett schwarz
    let green = image::RgbImage::from_pixel(1, 1, image::Rgb([0, 255, 0]));
    let out_green = process(&green, params).unwrap();
    let p2 = out_green.get_pixel(0, 0);
    assert!(p2[0] <= 2 && p2[1] <= 2 && p2[2] <= 2, "Pixel war {p2:?}");
}
