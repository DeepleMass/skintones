/**
 * Unit-Tests für src/hsv.js (RGB<->HSV, zirkulare Hue-Distanz).
 * Aufruf: node --test test/  (eingebauter Testrunner von Node, keine Deps)
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { rgbToHsv, hsvToRgb, hueDistance, wrapHue, clamp, isHueMatch } from "../src/hsv.js";

test("clamp begrenzt Werte auf [min, max]", () => {
  assert.equal(clamp(5, 0, 10), 5);
  assert.equal(clamp(-1, 0, 10), 0);
  assert.equal(clamp(11, 0, 10), 10);
});

test("wrapHue normalisiert per Modulo in [0, 360)", () => {
  assert.equal(wrapHue(0), 0);
  assert.equal(wrapHue(359.5), 359.5);
  assert.equal(wrapHue(360), 0);
  assert.equal(wrapHue(370), 10);
  assert.equal(wrapHue(-5), 355);
  assert.equal(wrapHue(-360), 0);
});

test("rgbToHsv: Primär- und Sekundärfarben (bekannte Werte)", () => {
  assert.deepEqual(rgbToHsv(255, 0, 0), { h: 0, s: 1, v: 1 });       // Rot
  assert.deepEqual(rgbToHsv(0, 255, 0), { h: 120, s: 1, v: 1 });     // Grün
  assert.deepEqual(rgbToHsv(0, 0, 255), { h: 240, s: 1, v: 1 });     // Blau
  assert.deepEqual(rgbToHsv(255, 255, 0), { h: 60, s: 1, v: 1 });    // Gelb
  assert.deepEqual(rgbToHsv(0, 255, 255), { h: 180, s: 1, v: 1 });   // Cyan
  assert.deepEqual(rgbToHsv(255, 0, 255), { h: 300, s: 1, v: 1 });   // Magenta
});

test("rgbToHsv: Grau/Weiß/Schwarz haben s=0 und Konvention h=0", () => {
  assert.deepEqual(rgbToHsv(0, 0, 0), { h: 0, s: 0, v: 0 });
  assert.deepEqual(rgbToHsv(255, 255, 255), { h: 0, s: 0, v: 1 });
  const gray = rgbToHsv(128, 128, 128);
  assert.equal(gray.s, 0);
  assert.equal(gray.h, 0);
  assert.ok(Math.abs(gray.v - 128 / 255) < 1e-9);
});

test("rgbToHsv: ein Hautton landet im erwarteten Hue-Bereich", () => {
  const skin = rgbToHsv(217, 160, 119); // typischer heller Hautton
  assert.ok(skin.h > 15 && skin.h < 40, `Hue ${skin.h} sollte ~25° sein`);
  assert.ok(skin.s > 0.3 && skin.s < 0.6);
  assert.ok(skin.v > 0.7);
});

test("Roundtrip rgb -> hsv -> rgb bleibt innerhalb ±1 pro Kanal", () => {
  const samples = [
    [217, 160, 119], [92, 148, 204], [10, 200, 90], [250, 128, 3],
    [0, 0, 0], [255, 255, 255], [1, 2, 3], [200, 200, 200], [90, 40, 160],
  ];
  for (const [r, g, b] of samples) {
    const { h, s, v } = rgbToHsv(r, g, b);
    const [r2, g2, b2] = hsvToRgb(h, s, v);
    assert.ok(Math.abs(r2 - r) <= 1, `r: ${r} -> ${r2}`);
    assert.ok(Math.abs(g2 - g) <= 1, `g: ${g} -> ${g2}`);
    assert.ok(Math.abs(b2 - b) <= 1, `b: ${b} -> ${b2}`);
  }
});

test("hsvToRgb respektiert wrapHue (h=360 == h=0)", () => {
  assert.deepEqual(hsvToRgb(360, 1, 1), hsvToRgb(0, 1, 1));
  assert.deepEqual(hsvToRgb(-60, 1, 1), hsvToRgb(300, 1, 1));
});

test("hueDistance ist zirkular (Wrap bei 0/360) und symmetrisch", () => {
  assert.equal(hueDistance(350, 10), 20);   // über den 0/360-Übergang
  assert.equal(hueDistance(10, 350), 20);   // symmetrisch
  assert.equal(hueDistance(0, 180), 180);   // größtmöglicher Abstand
  assert.equal(hueDistance(25, 25), 0);
  assert.equal(hueDistance(0, 360), 0);     // 360 wird zu 0 normalisiert
  assert.equal(hueDistance(200, 20), 180); // größtmöglicher Abstand
});

test("isHueMatch: Toleranzgrenze ist inklusive, Wrap funktioniert", () => {
  assert.equal(isHueMatch(30, 25, 5), true);   // Distanz 5 == Toleranz -> Treffer
  assert.equal(isHueMatch(31, 25, 5), false);
  assert.equal(isHueMatch(20, 25, 5), true);
  assert.equal(isHueMatch(355, 5, 10), true);  // 355 vs 5: Distanz 10 über Wrap
  assert.equal(isHueMatch(0, 359, 1), true);
  assert.equal(isHueMatch(180, 0, 179), false);
});
