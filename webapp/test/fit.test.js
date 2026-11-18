/**
 * fit.test.js — Tests für die Fenster-Skalierung (src/fit.js).
 * Läuft in Node (reine Mathematik, kein DOM).
 *
 * Rendering: Das Ergebnisbild bekommt die GANZE verfügbare Bühne (Original
 * liegt als PiP darüber), deshalb wird auf availW×availH gefittet — ohne
 * Halbierung durch ein zweites Canvas.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { computeFitScale, ABS_MAX_EDGE } from "../src/fit.js";

test("Querformat: Skalierung begrenzt durch die verfügbare Breite", () => {
  // 2000x1000 in 1000x800: min(1000/2000=0.5, 800/1000=0.8) = 0.5
  const s = computeFitScale(2000, 1000, 1000, 800);
  assert.ok(Math.abs(s - 0.5) < 1e-9, `erwartet 0.5, war ${s}`);
});

test("Hochkant: Skalierung begrenzt durch die verfügbare Höhe", () => {
  // 1000x2000 in 1000x800: min(1000/1000=1, 800/2000=0.4) = 0.4
  const s = computeFitScale(1000, 2000, 1000, 800);
  assert.ok(Math.abs(s - 0.4) < 1e-9, `erwartet 0.4, war ${s}`);
});

test("Volle Bühne wird genutzt (keine Halbierung mehr)", () => {
  // 640x480 Demo in 1000x800: min(1000/640, 800/480) = min(1.5625, 1.6667) = 1.5625
  const s = computeFitScale(640, 480, 1000, 800);
  assert.ok(Math.abs(s - 1.5625) < 1e-9, `erwartet 1.5625, war ${s}`);
});

test("Hochskalieren ist erlaubt (Faktor > 1)", () => {
  const s = computeFitScale(100, 100, 1000, 800); // min(10, 8) = 8
  assert.ok(s > 1, `kleines Bild soll hochskaliert werden, war ${s}`);
  assert.ok(Math.abs(s - 8) < 1e-9);
});

test("Absolute Obergrenze (ABS_MAX_EDGE) deckelt das Hochskalieren", () => {
  const s = computeFitScale(10, 10, 5000, 5000); // fit 500, Cap 1280/10 = 128
  assert.equal(s, ABS_MAX_EDGE / 10);
});

test("Riesenbild wird auf ABS_MAX_EDGE heruntergerechnet", () => {
  const s = computeFitScale(8000, 6000, 4000, 3000); // min(0.5, 0.5)=0.5, Cap 0.16
  assert.ok(Math.abs(s - ABS_MAX_EDGE / 8000) < 1e-12);
});

test("Ungültige Bildgrößen liefern Faktor 1 (kein Absturz)", () => {
  assert.equal(computeFitScale(0, 100, 1000, 800), 1);
  assert.equal(computeFitScale(100, 0, 1000, 800), 1);
  assert.equal(computeFitScale(-5, 100, 1000, 800), 1);
});
