/**
 * Unit- + Integrationstests für src/pipeline.js.
 *
 * Integration auf Pixelebene: ein synthetisches Zwei-Hue-Bild
 * (links Blau H≈210°, rechts Hautton H≈25°) wird gefiltert — rechts muss
 * das Bild exakt erhalten bleiben, links muss es geblurt+abgedunkelt sein.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  processImage, buildHueMask, darkenValue, validateParams, DEFAULT_PARAMS,
} from "../src/pipeline.js";
import { rgbToHsv, hsvToRgb } from "../src/hsv.js";

/** Baut ein RGBA-Bild, dessen linke/rechte Hälfte je eine HSV-Farbe hat. */
function makeTwoHueImage(w = 64, h = 64, leftHsv = { h: 210, s: 0.55, v: 0.8 }, rightHsv = { h: 25, s: 0.45, v: 0.85 }) {
  const data = new Uint8ClampedArray(w * h * 4);
  const [lr, lg, lb] = hsvToRgb(leftHsv.h, leftHsv.s, leftHsv.v);
  const [rr, rg, rb] = hsvToRgb(rightHsv.h, rightHsv.s, rightHsv.v);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const p = (y * w + x) * 4;
      const left = x < w / 2;
      data[p] = left ? lr : rr;
      data[p + 1] = left ? lg : rg;
      data[p + 2] = left ? lb : rb;
      data[p + 3] = 255;
    }
  }
  return { width: w, height: h, data };
}

// ---------------------------------------------------------------------------
// validateParams
// ---------------------------------------------------------------------------

test("validateParams normalisiert Hue per Modulo und clamped nichts Hartes", () => {
  const p = validateParams({ hue: 370, tolerance: 20, blurSigma: 8, darken: 0.6, feather: 3 });
  assert.equal(p.hue, 10);
  const p2 = validateParams({ hue: -5, tolerance: 0, blurSigma: 0, darken: 0, feather: 0 });
  assert.equal(p2.hue, 355);
});

test("validateParams lehnt fachlich unsinnige Werte ab", () => {
  const base = { ...DEFAULT_PARAMS };
  assert.throws(() => validateParams({ ...base, tolerance: 181 }), /Toleranz/);
  assert.throws(() => validateParams({ ...base, tolerance: -1 }), /Toleranz/);
  assert.throws(() => validateParams({ ...base, darken: 1.5 }), /Absenkung/);
  assert.throws(() => validateParams({ ...base, blurSigma: -0.5 }), /Blur/);
  assert.throws(() => validateParams({ ...base, feather: 99 }), /Weichzeichnung/);
  assert.throws(() => validateParams({ ...base, hue: NaN }), /Hue/);
});

// ---------------------------------------------------------------------------
// buildHueMask / darkenValue
// ---------------------------------------------------------------------------

test("buildHueMask: Treffer/Nicht-Treffer und Toleranz-180-Match", () => {
  // 2x1: links Rot (H=0), rechts Blau (H=240)
  const img = { width: 2, height: 1, data: new Uint8ClampedArray([255, 0, 0, 255, 0, 0, 255, 255]) };
  assert.deepEqual([...buildHueMask(img, 0, 10)], [1, 0]);
  assert.deepEqual([...buildHueMask(img, 240, 10)], [0, 1]);
  assert.deepEqual([...buildHueMask(img, 120, 180)], [1, 1]); // 180° deckt alles ab
  assert.deepEqual([...buildHueMask(img, 0, 0)], [1, 0]);     // exakter Treffer
});

test("darkenValue senkt V um den Faktor, Hue und Alpha bleiben erhalten", () => {
  // Reines Rot: h=0, s=1, v=1 -> v*0.5 = 0.5 -> rgb(128, 0, 0)
  const out = darkenValue(new Uint8ClampedArray([255, 0, 0, 200]), 0.5);
  assert.deepEqual([...out], [128, 0, 0, 200]);
  const hsv = rgbToHsv(out[0], out[1], out[2]);
  assert.ok(Math.abs(hsv.h - 0) < 1);      // Hue unverändert
  assert.ok(Math.abs(hsv.v - 0.5) < 0.01); // Value halbiert
  // Weiß -> Grau
  const gray = darkenValue(new Uint8ClampedArray([255, 255, 255, 255]), 0.5);
  assert.deepEqual([...gray], [128, 128, 128, 255]);
});

// ---------------------------------------------------------------------------
// processImage — Integration auf Pixelebene
// ---------------------------------------------------------------------------

test("processImage: Hautton-Hälfte bleibt exakt, Blau-Hälfte wird dunkler", () => {
  const img = makeTwoHueImage();
  const params = { hue: 25, tolerance: 20, blurSigma: 4, darken: 0.5, feather: 2 };
  const { image, stats } = processImage(img, params);

  assert.equal(image.width, 64);
  assert.equal(image.height, 64);
  assert.equal(image.data.length, img.data.length);

  // Statistik: exakt die rechte Hälfte (2048 von 4096 Pixeln) ist Treffer
  assert.equal(stats.total, 64 * 64);
  assert.equal(stats.matched, 64 * 32);
  assert.ok(stats.elapsedMs >= 0);

  // Tief im rechten (Haut-)Bereich: Pixel exakt unverändert (Maske = 1)
  const pr = (32 * 64 + 60) * 4;
  for (let c = 0; c < 4; c++) {
    assert.equal(image.data[pr + c], img.data[pr + c], `Kanal ${c} im Treffer-Bereich`);
  }

  // Tief im linken (Hintergrund-)Bereich: abgedunkelt, aber Hue erhalten
  const pl = (32 * 64 + 4) * 4;
  const origHsv = rgbToHsv(img.data[pl], img.data[pl + 1], img.data[pl + 2]);
  const outHsv = rgbToHsv(image.data[pl], image.data[pl + 1], image.data[pl + 2]);
  assert.ok(Math.abs(outHsv.h - origHsv.h) < 3, `Hue driftet: ${origHsv.h} -> ${outHsv.h}`);
  assert.ok(outHsv.v < origHsv.v - 0.3, `Value sollte deutlich sinken: ${origHsv.v} -> ${outHsv.v}`);
  assert.ok(image.data[pl + 2] < img.data[pl + 2], "Blaukanal des Hintergrunds wird kleiner");
  // Alpha bleibt 255
  assert.equal(image.data[pl + 3], 255);
  // Erwartete Zielfarbe: V halbiert im HSV-Raum
  const [er, eg, eb] = hsvToRgb(210, 0.55, 0.8 * 0.5);
  assert.ok(Math.abs(image.data[pl] - er) <= 3, `r ${image.data[pl]} ~ ${er}`);
  assert.ok(Math.abs(image.data[pl + 1] - eg) <= 3, `g ${image.data[pl + 1]} ~ ${eg}`);
  assert.ok(Math.abs(image.data[pl + 2] - eb) <= 3, `b ${image.data[pl + 2]} ~ ${eb}`);
});

test("processImage: blurSigma=0 + darken=0 ist die Identität", () => {
  const img = makeTwoHueImage(32, 16);
  const { image } = processImage(img, { hue: 25, tolerance: 20, blurSigma: 0, darken: 0, feather: 0 });
  assert.deepEqual([...image.data], [...img.data]);
});

test("processImage: mit Hue auf den Hintergrund bleibt die Haut dunkel", () => {
  const img = makeTwoHueImage();
  // Ziel = Hintergrundblau: Hautbereich (rechts) ist dann "Nicht-Treffer"
  const { image } = processImage(img, { hue: 210, tolerance: 20, blurSigma: 4, darken: 0.5, feather: 2 });
  const pr = (32 * 64 + 60) * 4; // tief in der rechten Hälfte
  const inHsv = rgbToHsv(img.data[pr], img.data[pr + 1], img.data[pr + 2]);
  const outHsv = rgbToHsv(image.data[pr], image.data[pr + 1], image.data[pr + 2]);
  assert.ok(outHsv.v < inHsv.v - 0.3, "Hautbereich muss abgedunkelt werden");
  // Linke Hälfte (Treffer) bleibt exakt
  const pl = (32 * 64 + 4) * 4;
  for (let c = 0; c < 4; c++) assert.equal(image.data[pl + c], img.data[pl + c]);
});

test("processImage: Eingabebild wird nicht verändert (Reinheit)", () => {
  const img = makeTwoHueImage(16, 16);
  const snapshot = [...img.data];
  processImage(img, { ...DEFAULT_PARAMS });
  assert.deepEqual([...img.data], snapshot);
});

test("processImage: 1x1-Bild läuft ohne Absturz durch", () => {
  const tiny = { width: 1, height: 1, data: new Uint8ClampedArray([255, 0, 0, 255]) };
  const { image, stats } = processImage(tiny, { hue: 0, tolerance: 10, blurSigma: 2, darken: 0.5, feather: 1 });
  assert.equal(image.width, 1);
  assert.equal(image.data.length, 4);
  assert.equal(stats.total, 1);
  assert.equal(stats.matched, 1); // Rot auf Hue 0 -> Treffer
});

test("processImage: ungültige Parameter werfen Fehler durch", () => {
  const img = makeTwoHueImage(8, 8);
  assert.throws(() => processImage(img, { hue: 0, tolerance: 200, blurSigma: 1, darken: 0, feather: 0 }), /Toleranz/);
});
