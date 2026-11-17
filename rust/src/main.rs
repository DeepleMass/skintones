//! Kommandozeilenschnittstelle von `skintone-lab`.
//!
//! Das Python-GUI (../python) ruft dieses Binary als Subprozess auf.
//!
//! ## Subkommandos
//! - `process` — Bild verarbeiten (Hue-Selektion + Blur/Darken des Rests)
//! - `demo`    — synthetisches Demo-Portrait erzeugen
//!
//! ## Erfolgs-Ausgabe von `process` (maschinenlesbar, eine Zeile):
//! `OK output=<pfad> width=<w> height=<h> elapsed_ms=<ms>`
//!
//! Fehler landen auf stderr, Exit-Code ist dann 2.

use std::path::PathBuf;
use std::process::ExitCode;
use std::time::Instant;

use clap::{Parser, Subcommand};

use skintone_lab::demo::demo_portrait;
use skintone_lab::image_io::{load_rgb, save_rgb};
use skintone_lab::pipeline::{process, PipelineParams};

/// HSV-Hue-Selektion: wählt einen Farbbereich und blurt/dunkelt den Rest.
#[derive(Parser)]
#[command(name = "skintone-lab", version, about, long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Verarbeitet ein Bild: Pixel außerhalb von `hue ± tolerance` werden
    /// geblurt und in ihrem HSV-Value abgesenkt.
    Process {
        /// Eingabebild (PNG, JPEG, BMP, ... — Format wird am Inhalt erkannt)
        #[arg(long)]
        input: PathBuf,
        /// Ausgabedatei (Format über die Endung, z. B. .png)
        #[arg(long)]
        output: PathBuf,
        /// Ziel-Hue in Grad [0, 360); wird gewrappt, z. B. 370 -> 10
        #[arg(long, default_value_t = 25.0)]
        hue: f32,
        /// Toleranz +/- in Grad um den Hue, [0, 180]
        #[arg(long, default_value_t = 20.0)]
        tolerance: f32,
        /// Sigma des Gaussian-Blur für Nicht-Treffer in Pixeln, [0, 100]
        #[arg(long, default_value_t = 8.0)]
        blur_sigma: f32,
        /// Anteil, um den der Value der Nicht-Treffer abgesenkt wird, [0, 1]
        #[arg(long, default_value_t = 0.6)]
        darken: f32,
        /// Radius zum Weichzeichnen der Maskenkante in Pixeln, [0, 64]
        #[arg(long, default_value_t = 2.0)]
        feather: f32,
    },
    /// Erzeugt ein synthetisches Demo-Portrait (zum Sofort-Ausprobieren).
    Demo {
        /// Ausgabedatei (z. B. demo.png)
        #[arg(long)]
        output: PathBuf,
        /// Breite in Pixeln
        #[arg(long, default_value_t = 640)]
        width: u32,
        /// Höhe in Pixeln
        #[arg(long, default_value_t = 480)]
        height: u32,
    },
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    match cli.command {
        Commands::Process {
            input,
            output,
            hue,
            tolerance,
            blur_sigma,
            darken,
            feather,
        } => run_process(
            &input,
            &output,
            PipelineParams {
                hue,
                tolerance,
                blur_sigma,
                darken,
                feather,
            },
        ),
        Commands::Demo {
            output,
            width,
            height,
        } => run_demo(&output, width, height),
    }
}

/// Lädt das Eingabebild, führt die Pipeline aus, speichert das Ergebnis und
/// gibt die maschinenlesbare `OK ...`-Zeile auf stdout aus.
fn run_process(input: &PathBuf, output: &PathBuf, params: PipelineParams) -> ExitCode {
    let start = Instant::now();

    // Schritt 1: Bild laden
    let img = match load_rgb(input) {
        Ok(img) => img,
        Err(e) => {
            eprintln!(
                "FEHLER: Eingabebild {:?} konnte nicht geladen werden: {e}",
                input
            );
            return ExitCode::from(2);
        }
    };

    // Schritt 2: Pipeline ausführen (Parameter werden validiert)
    let result = match process(&img, params) {
        Ok(r) => r,
        Err(e) => {
            eprintln!("FEHLER: ungültige Parameter: {e}");
            return ExitCode::from(2);
        }
    };

    // Schritt 3: Ergebnis speichern
    if let Err(e) = save_rgb(&result, output) {
        eprintln!(
            "FEHLER: Ausgabebild {:?} konnte nicht gespeichert werden: {e}",
            output
        );
        return ExitCode::from(2);
    }

    // Schritt 4: Maschinenlesbare Erfolgszeile (GUI und Tests parsen die)
    let (w, h) = result.dimensions();
    let elapsed_ms = start.elapsed().as_millis();
    println!(
        "OK output={} width={w} height={h} elapsed_ms={elapsed_ms}",
        output.display()
    );
    ExitCode::SUCCESS
}

/// Erzeugt das Demo-Portrait und speichert es.
fn run_demo(output: &PathBuf, width: u32, height: u32) -> ExitCode {
    if width == 0 || height == 0 {
        eprintln!("FEHLER: Breite und Höhe müssen > 0 sein");
        return ExitCode::from(2);
    }
    let img = demo_portrait(width, height);
    match save_rgb(&img, output) {
        Ok(()) => {
            println!(
                "OK output={} width={width} height={height}",
                output.display()
            );
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("FEHLER: {:?} konnte nicht gespeichert werden: {e}", output);
            ExitCode::from(2)
        }
    }
}
