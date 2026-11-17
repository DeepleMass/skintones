"""Brücke zwischen der Python-GUI und dem Rust-Binary `skintone-lab`.

Die GUI macht keine Pixelverarbeitung selbst, sondern ruft das Rust-Binary
als Subprozess auf:

    skintone-lab process --input <png> --output <png> --hue <grad> \
        --tolerance <grad> --blur-sigma <px> --darken <0..1> --feather <px>

Dieses Modul kapselt Kommando-Aufbau, Parameter-Validierung und Ausführung —
getrennt von tkinter, damit es ohne Display unit-testbar ist.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Standardwerte (müssen zu PipelineParams::default() in Rust passen)
# ---------------------------------------------------------------------------
DEFAULT_HUE = 25.0          # Ziel-Hue in Grad (typischer Hautfarb-Bereich)
DEFAULT_TOLERANCE = 20.0    # +/- Toleranz in Grad
DEFAULT_BLUR_SIGMA = 8.0    # Blur-Stärke für Nicht-Treffer in Pixeln
DEFAULT_DARKEN = 0.6        # Anteil, um den der Value abgesenkt wird
DEFAULT_FEATHER = 2.0       # Weichzeichnung der Maskenkante in Pixeln

# Erlaubte Wertebereiche (müssen zu PipelineParams::validate() in Rust passen)
HUE_RANGE = (0.0, 360.0)        # wird in Rust auf [0, 360) gewrappt
TOLERANCE_RANGE = (0.0, 180.0)
BLUR_SIGMA_RANGE = (0.0, 100.0)
DARKEN_RANGE = (0.0, 1.0)
FEATHER_RANGE = (0.0, 64.0)

# Zeitlimit für einen Verarbeitungslauf (große Bilder brauchen länger)
DEFAULT_TIMEOUT_S = 120.0


@dataclasses.dataclass(frozen=True)
class ProcessParams:
    """Alle Parameter für einen `process`-Aufruf des Rust-Binarys."""

    hue: float = DEFAULT_HUE
    tolerance: float = DEFAULT_TOLERANCE
    blur_sigma: float = DEFAULT_BLUR_SIGMA
    darken: float = DEFAULT_DARKEN
    feather: float = DEFAULT_FEATHER

    def validate(self) -> None:
        """Prüft die Wertebereiche und wirft `ValueError` mit Klartext."""
        for name, value, (low, high) in (
            ("hue", self.hue, HUE_RANGE),
            ("tolerance", self.tolerance, TOLERANCE_RANGE),
            ("blur_sigma", self.blur_sigma, BLUR_SIGMA_RANGE),
            ("darken", self.darken, DARKEN_RANGE),
            ("feather", self.feather, FEATHER_RANGE),
        ):
            if not (low <= value <= high):
                raise ValueError(
                    f"{name}={value} liegt außerhalb von [{low}, {high}]"
                )

    def to_cli_args(self, input_path: Path, output_path: Path) -> list[str]:
        """Baut die Argumentliste für `skintone-lab process ...`.

        Die Reihenfolge ist stabil, damit Tests sie exakt prüfen können.
        """
        self.validate()
        return [
            "process",
            "--input", str(input_path),
            "--output", str(output_path),
            "--hue", repr(float(self.hue)),
            "--tolerance", repr(float(self.tolerance)),
            "--blur-sigma", repr(float(self.blur_sigma)),
            "--darken", repr(float(self.darken)),
            "--feather", repr(float(self.feather)),
        ]


@dataclasses.dataclass
class ProcessResult:
    """Ergebnis eines Subprozess-Laufs."""

    returncode: int
    stdout: str
    stderr: str
    elapsed_s: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def ok_line(self) -> str | None:
        """Die `OK output=... width=... height=... elapsed_ms=...`-Zeile, falls vorhanden."""
        for line in self.stdout.splitlines():
            if line.startswith("OK "):
                return line
        return None


def find_binary(explicit: str | os.PathLike | None = None) -> Path:
    """Sucht das `skintone-lab`-Binary.

    Reihenfolge:
    1. expliziter Pfad (Argument) — wenn angegeben, wird NUR dieser geprüft
       und bei Fehlen sofort ein Fehler geworfen (keine stille Umleitung)
    2. Umgebungsvariable `SKINTONE_LAB_BIN`
    3. Release-Build im Rust-Subfolder: `../rust/target/release/skintone-lab`
    4. Debug-Build: `../rust/target/debug/skintone-lab`
    5. `skintone-lab` auf dem PATH
    """
    if explicit is not None:
        cand = Path(explicit)
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
        raise FileNotFoundError(f"explizites Binary nicht gefunden oder nicht ausführbar: {cand}")

    candidates: list[Path] = []
    env_bin = os.environ.get("SKINTONE_LAB_BIN")
    if env_bin:
        candidates.append(Path(env_bin))
    rust_root = Path(__file__).resolve().parent.parent / "rust"
    candidates.append(rust_root / "target" / "release" / "skintone-lab")
    candidates.append(rust_root / "target" / "debug" / "skintone-lab")
    on_path = shutil.which("skintone-lab")
    if on_path:
        candidates.append(Path(on_path))

    for cand in candidates:
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
    searched = ", ".join(str(c) for c in candidates)
    raise FileNotFoundError(
        "skintone-lab-Binary nicht gefunden. Bitte zuerst bauen: "
        "`cd ../rust && cargo build --release`. Gesucht: " + searched
    )


def run_process(
    binary: str | os.PathLike,
    params: ProcessParams,
    input_path: str | os.PathLike,
    output_path: str | os.PathLike,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> ProcessResult:
    """Führt `skintone-lab process` aus und liefert ein `ProcessResult`.

    Wirft `FileNotFoundError`, wenn das Binary fehlt, und
    `subprocess.TimeoutExpired`, wenn das Zeitlimit überschritten wird.
    """
    binary = Path(binary)
    args = [str(binary)] + params.to_cli_args(Path(input_path), Path(output_path))
    start = time.monotonic()
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    elapsed = time.monotonic() - start
    return ProcessResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        elapsed_s=elapsed,
    )


def run_demo(
    binary: str | os.PathLike,
    output_path: str | os.PathLike,
    width: int = 640,
    height: int = 480,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> ProcessResult:
    """Erzeugt über das Binary ein synthetisches Demo-Portrait."""
    args = [
        str(binary), "demo",
        "--output", str(output_path),
        "--width", str(int(width)),
        "--height", str(int(height)),
    ]
    start = time.monotonic()
    completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout_s)
    return ProcessResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        elapsed_s=time.monotonic() - start,
    )
