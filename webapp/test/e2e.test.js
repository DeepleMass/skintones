/**
 * e2e.test.js — Ende-zu-Ende-Test ohne Browser: komplettes Demo-Portrait
 * erzeugen (src/demo.js) und die volle Pipeline (src/pipeline.js) laufen
 * lassen, dann die Pixel des Ergebnisses prüfen.
 *
 * Das ist derselbe Ablauf, den der "Demo-Portrait"-Button in der UI auslöst.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { createDemoImage } from "../src/demo.js";
import { processImage, DEFAULT_PARAMS } from "../src/pipeline.js";
import { rgbToHsv, hsvToRgb } from "../src/hsv.js";

const W = 160, H = 120; // klein halten, damit der Test schnell bleibt

test("Demo-Portrait hat die erwartete Größe und deckendes Alpha", () => {
  const demo = createDemoImage(W, H);
  assert.equal(demo.width, W);
  assert.equal(demo.height, H);
  assert.equal(demo.data.length, W * H * 4);
  for (let p = 3; p < demo.data.length; p += 4) assert.equal(demo.data[p], 255);
});

test("E2E: Gesicht (Hautton) bleibt erhalten, Hintergrund wird geblurt+abgedunkelt", () => {
  const demo = createDemoImage(W, H);
  const params = { ...DEFAULT_PARAMS, hue: 25, tolerance: 20, blurSigma: 6, darken: 0.6, feather: 2 };
  const { image, stats } = processImage(demo, params);

  // Gesichts-Mitte: Ellipsenmittelpunkt (0.5*W, 0.42*H)
  const fc = (Math.floor(0.42 * H) * W + Math.floor(0.5 * W)) * 4;
  // Tief im Gesichtsbereich -> Maske 1 -> Pixel exakt wie im Original
  for (let c = 0; c < 4; c++) {
    assert.equal(image.data[fc + c], demo.data[fc + c], `Gesichts-Pixel Kanal ${c} verändert`);
  }

  // Ecke oben links: Hintergrund (H≈210) -> Maske 0 -> abgedunkelt
  const corner = (2 * W + 2) * 4;
  const inHsv = rgbToHsv(demo.data[corner], demo.data[corner + 1], demo.data[corner + 2]);
  const outHsv = rgbToHsv(image.data[corner], image.data[corner + 1], image.data[corner + 2]);
  assert.ok(Math.abs(inHsv.h - 210) < 5, `Hintergrund-Hue ${inHsv.h} sollte ~210 sein`);
  assert.ok(Math.abs(outHsv.h - inHsv.h) < 5, "Hue des Hintergrunds bleibt erhalten");
  assert.ok(outHsv.v < inHsv.v * 0.6, `Value muss deutlich sinken: ${inHsv.v} -> ${outHsv.v}`);

  // Erwartete Zielfarbe: V * (1 - darken) im HSV-Raum
  const [er, eg, eb] = hsvToRgb(inHsv.h, inHsv.s, inHsv.v * (1 - params.darken));
  assert.ok(Math.abs(image.data[corner] - er) <= 4, `r ${image.data[corner]} ~ ${er}`);
  assert.ok(Math.abs(image.data[corner + 1] - eg) <= 4, `g ${image.data[corner + 1]} ~ ${eg}`);
  assert.ok(Math.abs(image.data[corner + 2] - eb) <= 4, `b ${image.data[corner + 2]} ~ ${eb}`);

  // Statistik: ein vernünftiger Anteil Treffer, Laufzeit gemessen
  assert.ok(stats.matched > 0 && stats.matched < stats.total);
  assert.ok(stats.elapsedMs >= 0);
});

test("E2E: Zielfarbe auf den Hintergrund dreht das Verhalten um", () => {
  const demo = createDemoImage(W, H);
  const { image } = processImage(demo, { ...DEFAULT_PARAMS, hue: 210, tolerance: 20, blurSigma: 6, darken: 0.6, feather: 2 });

  // Ecke (Hintergrund) ist jetzt Treffer -> exakt unverändert
  const corner = (2 * W + 2) * 4;
  for (let c = 0; c < 4; c++) assert.equal(image.data[corner + c], demo.data[corner + c]);

  // Gesichts-Mitte ist jetzt Nicht-Treffer -> dunkler geworden
  const fc = (Math.floor(0.42 * H) * W + Math.floor(0.5 * W)) * 4;
  const inV = rgbToHsv(demo.data[fc], demo.data[fc + 1], demo.data[fc + 2]).v;
  const outV = rgbToHsv(image.data[fc], image.data[fc + 1], image.data[fc + 2]).v;
  assert.ok(outV < inV - 0.2, `Gesicht muss abgedunkelt werden: ${inV} -> ${outV}`);
});

test("E2E: Pipeline auf Demo-Portrait bleibt performant (< 2 s für 160x120)", () => {
  const demo = createDemoImage(W, H);
  const { stats } = processImage(demo, { ...DEFAULT_PARAMS, blurSigma: 8 });
  assert.ok(stats.elapsedMs < 2000, `zu langsam: ${stats.elapsedMs} ms`);
});
