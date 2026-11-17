//! Integrationstests: Sie rufen das fertig kompilierte Binary über
//! `CARGO_BIN_EXE_skintone-lab` auf (von Cargo automatisch gesetzt) und prüfen
//! den kompletten Ablauf Datei -> CLI -> Datei.

use std::path::PathBuf;
use std::process::Command;

use skintone_lab::hsv::rgb_to_hsv;

/// Pfad zum kompilierten Binary (Cargo stellt diese Env-Variable in Tests bereit).
fn bin() -> &'static str {
    env!("CARGO_BIN_EXE_skintone-lab")
}

/// Eindeutiges Temp-Verzeichnis für diesen Testlauf.
fn temp_dir(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("skintone-lab-it-{name}-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

#[test]
fn demo_und_process_end_to_end() {
    let dir = temp_dir("e2e");
    let input = dir.join("demo.png");
    let output = dir.join("ergebnis.png");

    // 1. Demo-Portrait erzeugen
    let demo = Command::new(bin())
        .args(["demo", "--output"])
        .arg(&input)
        .args(["--width", "320", "--height", "240"])
        .output()
        .expect("demo-Kommando konnte nicht gestartet werden");
    assert!(
        demo.status.success(),
        "demo schlug fehl: {}",
        String::from_utf8_lossy(&demo.stderr)
    );
    assert!(input.exists());

    // 2. Verarbeiten: Hue 25 (Gesicht) ± 15 — Hintergrund (Hue ~210) muss rausfallen
    let run = Command::new(bin())
        .args(["process", "--input"])
        .arg(&input)
        .args(["--output"])
        .arg(&output)
        .args(["--hue", "25", "--tolerance", "15"])
        .args(["--blur-sigma", "6", "--darken", "0.7", "--feather", "2"])
        .output()
        .expect("process-Kommando konnte nicht gestartet werden");
    assert!(
        run.status.success(),
        "process schlug fehl: {}",
        String::from_utf8_lossy(&run.stderr)
    );

    // 3. Maschinenlesbare OK-Zeile prüfen
    let stdout = String::from_utf8_lossy(&run.stdout);
    assert!(stdout.starts_with("OK "), "stdout war: {stdout}");
    assert!(stdout.contains("width=320") && stdout.contains("height=240"));
    assert!(stdout.contains("elapsed_ms="));
    assert!(output.exists());

    // 4. Ergebnisbild inhaltlich prüfen: Gesicht (Mitte) bleibt hell und hue-stabil,
    //    Hintergrund (Ecke) wird dunkler.
    let img = image::open(&output).unwrap().to_rgb8();
    let original = image::open(&input).unwrap().to_rgb8();
    let (w, h) = img.dimensions();
    let center = img.get_pixel(w / 2, h / 2);
    let corner = img.get_pixel(2, 2);
    let orig_center = original.get_pixel(w / 2, h / 2);
    let orig_corner = original.get_pixel(2, 2);

    // Gesicht: Hue nahe 25° und Helligkeit nahe am Original
    let hsv_face = rgb_to_hsv(center[0], center[1], center[2]);
    assert!(
        (hsv_face.h - 25.0).abs() < 15.0,
        "Gesichts-Hue im Ergebnis war {}",
        hsv_face.h
    );
    let v_face_in = rgb_to_hsv(orig_center[0], orig_center[1], orig_center[2]).v;
    assert!(
        hsv_face.v > v_face_in * 0.8,
        "Gesicht wurde abgedunkelt: v_in={v_face_in} v_out={}",
        hsv_face.v
    );

    // Hintergrund: deutlich dunkler als im Original
    let v_bg_in = rgb_to_hsv(orig_corner[0], orig_corner[1], orig_corner[2]).v;
    let v_bg_out = rgb_to_hsv(corner[0], corner[1], corner[2]).v;
    assert!(
        v_bg_out < v_bg_in * 0.6,
        "Hintergrund wurde nicht abgedunkelt: v_in={v_bg_in} v_out={v_bg_out}"
    );

    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn ungueltige_parameter_geben_fehlercode_2() {
    let dir = temp_dir("bad");
    let input = dir.join("demo.png");
    let output = dir.join("out.png");

    Command::new(bin())
        .args(["demo", "--output"])
        .arg(&input)
        .output()
        .unwrap();

    // tolerance > 180 ist fachlich unsinnig -> Exit-Code 2 und Fehlermeldung
    let run = Command::new(bin())
        .args(["process", "--input"])
        .arg(&input)
        .args(["--output"])
        .arg(&output)
        .args(["--hue", "25", "--tolerance", "200"])
        .output()
        .unwrap();
    assert_eq!(run.status.code(), Some(2));
    let stderr = String::from_utf8_lossy(&run.stderr);
    assert!(stderr.contains("tolerance"), "stderr war: {stderr}");
    assert!(!output.exists());

    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn fehlende_eingabe_datei_geben_fehlercode_2() {
    let dir = temp_dir("missing");
    let run = Command::new(bin())
        .args(["process", "--input"])
        .arg(dir.join("gibt-es-nicht.png"))
        .args(["--output"])
        .arg(dir.join("out.png"))
        .output()
        .unwrap();
    assert_eq!(run.status.code(), Some(2));
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn hue_wrappt_in_der_cli() {
    let dir = temp_dir("wrap");
    let input = dir.join("demo.png");
    let output = dir.join("out.png");
    Command::new(bin())
        .args(["demo", "--output"])
        .arg(&input)
        .output()
        .unwrap();

    // hue = 385 entspricht 25 -> muss genau so funktionieren wie hue = 25
    let run = Command::new(bin())
        .args(["process", "--input"])
        .arg(&input)
        .args(["--output"])
        .arg(&output)
        .args(["--hue", "385", "--tolerance", "15"])
        .output()
        .unwrap();
    assert!(run.status.success());
    assert!(output.exists());

    let _ = std::fs::remove_dir_all(&dir);
}
