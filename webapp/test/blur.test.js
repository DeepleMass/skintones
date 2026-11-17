/**
 * Unit-Tests für src/blur.js (Gaussian-Kernel, separabler Blur RGBA + Float).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { gaussianKernel, blurRgba, blurFloat } from "../src/blur.js";

test("gaussianKernel(0) ist der Delta-Impuls [1] (identische Abbildung)", () => {
  const k = gaussianKernel(0);
  assert.equal(k.length, 1);
  assert.equal(k[0], 1);
});

test("gaussianKernel: ungerade Länge, Summe = 1, symmetrisch", () => {
  const sigma = 2;
  const k = gaussianKernel(sigma);
  assert.equal(k.length % 2, 1);
  assert.equal(k.length, 2 * Math.ceil(3 * sigma) + 1);
  let sum = 0;
  for (const w of k) sum += w;
  assert.ok(Math.abs(sum - 1) < 1e-6, `Summe ${sum} sollte 1 sein`);
  for (let i = 0; i < k.length; i++) {
    assert.ok(Math.abs(k[i] - k[k.length - 1 - i]) < 1e-9, "Kernel muss symmetrisch sein");
  }
  // Maximum in der Mitte
  const mid = (k.length - 1) / 2;
  for (let i = 0; i < k.length; i++) assert.ok(k[i] <= k[mid] + 1e-12);
});

test("blurRgba: konstantes Bild bleibt exakt konstant (Helligkeitserhalt)", () => {
  const w = 8, h = 8;
  const src = new Uint8ClampedArray(w * h * 4);
  for (let p = 0; p < src.length; p += 4) {
    src[p] = 10; src[p + 1] = 20; src[p + 2] = 30; src[p + 3] = 255;
  }
  const out = blurRgba(src, w, h, 2);
  for (let p = 0; p < out.length; p += 4) {
    assert.equal(out[p], 10);
    assert.equal(out[p + 1], 20);
    assert.equal(out[p + 2], 30);
    assert.equal(out[p + 3], 255);
  }
  // Eingabe darf nicht verändert worden sein (Reinheit)
  assert.equal(src[0], 10);
});

test("blurRgba: Impuls wird weich verteilt, Gesamtenergie bleibt ~erhalten", () => {
  const w = 9, h = 9;
  const src = new Uint8ClampedArray(w * h * 4); // schwarz, Alpha 255
  for (let p = 3; p < src.length; p += 4) src[p] = 255;
  const c = (4 * w + 4) * 4; // Zentrum (4,4)
  src[c] = 255; src[c + 1] = 255; src[c + 2] = 255;

  const out = blurRgba(src, w, h, 1); // sigma=1 -> Radius 3, kein Rand-Clamping nötig
  // Zentrum ist heller als 0, aber dunkler als 255
  assert.ok(out[c] > 0 && out[c] < 255, `Zentrum ${out[c]}`);
  // Nachbarn haben etwas abbekommen
  const right = (4 * w + 5) * 4;
  assert.ok(out[right] > 0 && out[right] < 255);
  // Energieerhalt pro Kanal (Summe über das Bild), Toleranz nur fürs Runden
  let sumIn = 0, sumOut = 0;
  for (let p = 0; p < src.length; p += 4) { sumIn += src[p]; sumOut += out[p]; }
  // Toleranz 5 %: durch das Runden auf ganze Zahlen geht pro Pixel bis 0.5 verloren
  assert.ok(Math.abs(sumOut - sumIn) / sumIn < 0.05, `Energie ${sumIn} -> ${sumOut}`);
});

test("blurRgba mit sigma=0 ist die Identität", () => {
  const w = 4, h = 3;
  const src = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < src.length; i++) src[i] = (i * 37) % 256;
  const out = blurRgba(src, w, h, 0);
  assert.deepEqual([...out], [...src]);
});

test("blurFloat: konstante Maske bleibt konstant, Kante wird geglättet", () => {
  const w = 16, h = 1;
  const mask = new Float32Array(w);
  for (let x = 0; x < w; x++) mask[x] = x < 8 ? 1 : 0; // harte Kante bei x=8
  const soft = blurFloat(mask, w, h, 2);
  assert.equal(soft.length, w);
  // Tief innen bleibt 1 bzw. 0
  assert.ok(Math.abs(soft[0] - 1) < 1e-6);
  assert.ok(Math.abs(soft[w - 1] - 0) < 1e-6);
  // An der Kante: Wert zwischen 0 und 1 (geglättet), und monoton steigend/fallend
  assert.ok(soft[7] > 0 && soft[7] < 1);
  assert.ok(soft[8] > 0 && soft[8] < 1);
  for (let x = 1; x < w; x++) assert.ok(soft[x] <= soft[x - 1] + 1e-6, "monoton fallend");
  // Summe ~erhalten
  let sum = 0;
  for (const v of soft) sum += v;
  assert.ok(Math.abs(sum - 8) < 0.5, `Maskensumme ${sum} sollte ~8 sein`);
});
