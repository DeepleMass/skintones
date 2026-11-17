"""Unit-Tests für rust_bridge (laufen ohne Display, also ohne echtes tkinter-Fenster).

Testarten:
- reine Unit-Tests für Validierung und Kommando-Aufbau (immer ausführbar)
- ein Integrationstest gegen das echte Rust-Binary, falls es gebaut ist
  (sonst wird er übersprungen)
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

# Modul liegt im Elternordner
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rust_bridge
from rust_bridge import ProcessParams


class TestProcessParamsValidation(unittest.TestCase):
    """Validierung der Wertebereiche (Spiegel zu PipelineParams::validate in Rust)."""

    def test_defaults_sind_gueltig(self) -> None:
        ProcessParams().validate()  # darf nicht werfen

    def test_hue_wird_erlaubt_und_ist_breiter_als_360(self) -> None:
        # hue darf bis 360 gehen (Rust wrappt auf [0, 360)); 361 wäre fachlich ok,
        # wird aber vom GUI-Slider nie erreicht — wir prüfen die Grenze 360.
        ProcessParams(hue=360.0).validate()
        with self.assertRaises(ValueError):
            ProcessParams(hue=361.0).validate()
        with self.assertRaises(ValueError):
            ProcessParams(hue=-1.0).validate()

    def test_tolerance_grenzen(self) -> None:
        ProcessParams(tolerance=0.0).validate()
        ProcessParams(tolerance=180.0).validate()
        with self.assertRaises(ValueError):
            ProcessParams(tolerance=180.5).validate()
        with self.assertRaises(ValueError):
            ProcessParams(tolerance=-0.1).validate()

    def test_darken_und_blur_und_feather(self) -> None:
        ProcessParams(darken=0.0).validate()
        ProcessParams(darken=1.0).validate()
        with self.assertRaises(ValueError):
            ProcessParams(darken=1.01).validate()
        with self.assertRaises(ValueError):
            ProcessParams(blur_sigma=101.0).validate()
        with self.assertRaises(ValueError):
            ProcessParams(feather=65.0).validate()


class TestCliArgs(unittest.TestCase):
    """Der Kommando-Aufbau muss exakt dem CLI des Rust-Binarys entsprechen."""

    def test_to_cli_args_reihenfolge_und_werte(self) -> None:
        params = ProcessParams(hue=25.0, tolerance=15.0, blur_sigma=6.0, darken=0.7, feather=2.0)
        args = params.to_cli_args(Path("/tmp/in.png"), Path("/tmp/out.png"))
        self.assertEqual(
            args,
            [
                "process",
                "--input", "/tmp/in.png",
                "--output", "/tmp/out.png",
                "--hue", "25.0",
                "--tolerance", "15.0",
                "--blur-sigma", "6.0",
                "--darken", "0.7",
                "--feather", "2.0",
            ],
        )

    def test_to_cli_args_validiert_zuerst(self) -> None:
        with self.assertRaises(ValueError):
            ProcessParams(tolerance=999.0).to_cli_args(Path("a"), Path("b"))


class TestFindBinary(unittest.TestCase):
    """Suchreihenfolge für das Binary."""

    def test_expliziter_pfad(self) -> None:
        # ein existierendes, ausführbares File wird als expliziter Pfad genommen
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "skintone-lab"
            fake.write_text("#!/bin/sh\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            self.assertEqual(rust_bridge.find_binary(fake), fake)

    def test_umgebungsvariable(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "mein-binary"
            fake.write_text("#!/bin/sh\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            os.environ["SKINTONE_LAB_BIN"] = str(fake)
            try:
                self.assertEqual(rust_bridge.find_binary(), fake)
            finally:
                del os.environ["SKINTONE_LAB_BIN"]

    def test_expliziter_pfad_streng(self) -> None:
        # ein explizit übergebener, nicht existierender Pfad wirft sofort —
        # es wird NICHT still auf die Auto-Suche umgeschaltet
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                rust_bridge.find_binary(Path(d) / "gibt-es-nicht")


@unittest.skipUnless(shutil.which("skintone-lab") or (Path(__file__).resolve().parent.parent.parent / "rust" / "target" / "release" / "skintone-lab").exists() or (Path(__file__).resolve().parent.parent.parent / "rust" / "target" / "debug" / "skintone-lab").exists(), "Rust-Binary nicht gebaut")
class TestAgainstRealBinary(unittest.TestCase):
    """Integrationstest: echtes Binary erzeugen -> verarbeiten -> prüfen."""

    def setUp(self) -> None:
        self.binary = rust_bridge.find_binary()
        self.dir = tempfile.TemporaryDirectory(prefix="bridge-it-")
        self.input = Path(self.dir.name) / "demo.png"
        self.output = Path(self.dir.name) / "out.png"
        demo = rust_bridge.run_demo(self.binary, self.input, 160, 120)
        assert demo.ok, demo.stderr

    def tearDown(self) -> None:
        self.dir.cleanup()

    def test_process_liefert_ok_zeile_und_datei(self) -> None:
        params = ProcessParams(hue=25.0, tolerance=20.0, blur_sigma=4.0, darken=0.6, feather=1.0)
        result = rust_bridge.run_process(self.binary, params, self.input, self.output)
        self.assertTrue(result.ok, result.stderr)
        self.assertIsNotNone(result.ok_line)
        assert result.ok_line is not None
        self.assertIn("width=160", result.ok_line)
        self.assertIn("height=120", result.ok_line)
        self.assertTrue(self.output.exists())
        self.assertGreater(self.output.stat().st_size, 0)

    def test_ungueltige_toleranz_schlaegt_fehl(self) -> None:
        # tolerance > 180 wird zwar vom Bridge nicht durchgelassen,
        # deshalb hier ein konstruierter Aufruf direkt über subprocess:
        import subprocess
        completed = subprocess.run(
            [str(self.binary), "process", "--input", str(self.input),
             "--output", str(self.output), "--hue", "25", "--tolerance", "200"],
            capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("tolerance", completed.stderr)


if __name__ == "__main__":
    unittest.main()
