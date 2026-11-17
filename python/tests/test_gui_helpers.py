"""Unit-Tests für die headless testbaren Helfer aus skintone_gui.

Import von skintone_gui braucht kein Display (erst Tk() würde eines brauchen),
dadurch laufen diese Tests auch auf Maschinen ohne GUI.
"""

from __future__ import annotations

import colorsys
import json
import sys
import unittest
from pathlib import Path

# Modul liegt im Elternordner
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import skintone_gui as gui


class TestHueToHex(unittest.TestCase):
    """Farbvorschau: Hue (Grad) -> #rrggbb."""

    def test_format_ist_hex(self) -> None:
        for h in (0.0, 25.0, 120.0, 359.9):
            self.assertRegex(gui.hue_to_hex(h), r"^#[0-9a-f]{6}$")

    def test_stimmt_mit_colorsys(self) -> None:
        h = 137.0
        r, g, b = colorsys.hsv_to_rgb((h % 360.0) / 360.0, 0.65, 0.9)
        expected = "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))
        self.assertEqual(gui.hue_to_hex(h), expected)

    def test_hue_wird_gewrappt(self) -> None:
        self.assertEqual(gui.hue_to_hex(360.0), gui.hue_to_hex(0.0))
        self.assertEqual(gui.hue_to_hex(-10.0), gui.hue_to_hex(350.0))

    def test_rot_ist_reddish(self) -> None:
        # Hue 0 muss einen hohen Rot-Anteil haben
        hx = gui.hue_to_hex(0.0)
        r = int(hx[1:3], 16)
        g = int(hx[3:5], 16)
        self.assertGreater(r, g)


class TestStripJsonc(unittest.TestCase):
    """JSONC-Parser für .vscode/settings.json: Kommentare raus, Strings bleiben."""

    def test_kommentare_und_strings(self) -> None:
        text = '{\n  "a": "https://example.com//x", // Kommentar\n  "b": 2 // trailing\n}'
        self.assertEqual(
            json.loads(gui.strip_jsonc(text)),
            {"a": "https://example.com//x", "b": 2},
        )

    def test_echte_settings_datei_parst(self) -> None:
        settings = gui.workspace_root() / ".vscode" / "settings.json"
        data = json.loads(gui.strip_jsonc(settings.read_text(encoding="utf-8")))
        self.assertIn("skintones.sampleImagesDir", data)
        self.assertIn("skintones.rustDir", data)


class TestFindSampleImage(unittest.TestCase):
    """Default-Beispielbild: skintones/sample-images/default-image.jpg."""

    def testfindet_default_image(self) -> None:
        img = gui.find_sample_image()
        self.assertIsNotNone(img, "kein Beispielbild gefunden")
        assert img is not None
        self.assertTrue(img.exists())
        self.assertEqual(img.name, "default-image.jpg")
        self.assertEqual(img.parent.name, "sample-images")
        self.assertIn(img.suffix.lower(), gui.SUPPORTED_IMAGE_SUFFIXES)

    def _fake_root(self, d: str, settings: dict, files: list[str]) -> Path:
        """Baut einen Fake-Workspace-Root mit .vscode/settings.json und Bildern."""
        import json as _json
        fake_root = Path(d)
        (fake_root / ".vscode").mkdir(parents=True)
        (fake_root / ".vscode" / "settings.json").write_text(_json.dumps(settings))
        sample_dir = fake_root / settings.get("skintones.sampleImagesDir", "skintones/sample-images")
        sample_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            (sample_dir / name).write_bytes(b"\xff\xd8\xff")  # JPEG-Magic als Dummy
        return fake_root

    def test_default_image_hat_vorrang(self) -> None:
        # default-image.jpg gewinnt gegen eine alphabetisch frühere Datei
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            fake_root = self._fake_root(
                d,
                {
                    "skintones.defaultSampleImage": "skintones/sample-images/default-image.jpg",
                    "skintones.sampleImagesDir": "skintones/sample-images",
                },
                ["aaa-first.png", "default-image.jpg"],
            )
            original = gui.workspace_root
            gui.workspace_root = lambda: fake_root
            try:
                img = gui.find_sample_image()
                self.assertIsNotNone(img)
                assert img is not None
                self.assertEqual(img.name, "default-image.jpg")
            finally:
                gui.workspace_root = original

    def test_fallback_erstes_bild_im_dir(self) -> None:
        # Default-Bild fehlt -> erstes Bild im sampleImagesDir
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            fake_root = self._fake_root(
                d,
                {
                    "skintones.defaultSampleImage": "skintones/sample-images/default-image.jpg",
                    "skintones.sampleImagesDir": "skintones/sample-images",
                },
                ["aaa-first.png"],
            )
            original = gui.workspace_root
            gui.workspace_root = lambda: fake_root
            try:
                img = gui.find_sample_image()
                self.assertIsNotNone(img)
                assert img is not None
                self.assertEqual(img.name, "aaa-first.png")
            finally:
                gui.workspace_root = original

    def test_kein_verzeichnis_gibt_none(self) -> None:
        # Wenn das konfigurierte Verzeichnis nicht existiert, muss None kommen
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            fake_root = Path(d)
            (fake_root / ".vscode").mkdir()
            (fake_root / ".vscode" / "settings.json").write_text(
                '{"skintones.sampleImagesDir": "skintones/sample-images"}'
            )
            # monkey-patch für den Test: workspace_root auf fake_root
            original = gui.workspace_root
            gui.workspace_root = lambda: fake_root
            try:
                self.assertIsNone(gui.find_sample_image())
            finally:
                gui.workspace_root = original


class TestLayoutKonstanten(unittest.TestCase):
    def test_defaults(self) -> None:
        self.assertEqual(gui.DEFAULT_LAYOUT, "horizontal")
        self.assertEqual(set(gui.LAYOUT_MODES), {"horizontal", "vertikal"})


if __name__ == "__main__":
    unittest.main()
