/**
 * pipeline.js — Die komplette Bildverarbeitungsroutine des Skintone-Experiments.
 *
 * Ablauf (siehe auch 000-user.txt, Punkt 3–5):
 *   1. Jedes Pixel wird von RGB nach HSV umgewandelt.
 *   2. Pixel, deren Hue NICHT innerhalb von `hue ± tolerance` liegt, landen
 *      auf der Maske mit 0 — alle anderen mit 1.
 *   3. Die Maske wird weichgezeichnet ("Feather"), damit keine harten Kanten
 *      entstehen.
 *   4. Der Hintergrund (Maske = 0) wird stark geblurt (Gaussian, Sigma) und
 *      anschließend in HSV sein Value (Helligkeit) um den Faktor `darken`
 *      abgesenkt — der Hue bleibt dabei erhalten, der Hintergrund wirkt
 *      dadurch gedimmt statt verfärbt.
 *   5. Compositing: Ergebnis = Maske * Original + (1 - Maske) * Hintergrund.
 *
 * Alle Funktionen arbeiten auf einem einfachen Bild-Objekt
 *   { width: number, height: number, data: Uint8ClampedArray }  // RGBA-Puffer
 * — exakt der Form von `ImageData` im Browser. Dadurch läuft die Pipeline
 * 1:1 im Browser (Canvas) und in Node (Tests), ohne jegliche Abhängigkeit.
 */

import { rgbToHsv, hsvToRgb, hueDistance, clamp } from "./hsv.js";
import { blurRgba, blurFloat } from "./blur.js";

/**
 * Standard-Parameter der Pipeline. Werden in der UI per Slider vorgegeben.
 */
export const DEFAULT_PARAMS = Object.freeze({
  hue: 25,        // Ziel-Hue in Grad [0, 360) — ca. Hautton
  tolerance: 20,  // erlaubte Abweichung in Grad [0, 180]
  blurSigma: 8,   // Blur-Stärke des Hintergrunds
  darken: 0.6,    // Anteil, um den der Value abgesenkt wird [0, 1]
  feather: 3,     // Weichzeichnung der Maskenkante (Sigma der Maske)
});

/**
 * Validiert die Pipeline-Parameter und wirft bei ungültigen Werten einen
 * Fehler mit deutscher Meldung. Hue wird per Modulo in [0,360) normalisiert,
 * die Toleranz muss fachlich in [0,180] liegen (mehr als 180° wäre der
 * gesamte Farbkreis und damit unsinnig).
 * @param {object} p Parameter-Objekt
 * @returns {object} normalisierte Kopie der Parameter
 */
export function validateParams(p) {
  const hue = ((p.hue % 360) + 360) % 360;
  const tolerance = Number(p.tolerance);
  const blurSigma = Number(p.blurSigma);
  const darken = Number(p.darken);
  const feather = Number(p.feather);

  if (!Number.isFinite(hue)) throw new Error("Hue muss eine Zahl sein.");
  if (!Number.isFinite(tolerance) || tolerance < 0 || tolerance > 180) {
    throw new Error("Toleranz muss zwischen 0 und 180 Grad liegen.");
  }
  if (!Number.isFinite(blurSigma) || blurSigma < 0 || blurSigma > 50) {
    throw new Error("Blur-Stärke (Sigma) muss zwischen 0 und 50 liegen.");
  }
  if (!Number.isFinite(darken) || darken < 0 || darken > 1) {
    throw new Error("Value-Absenkung muss zwischen 0 und 1 liegen.");
  }
  if (!Number.isFinite(feather) || feather < 0 || feather > 20) {
    throw new Error("Kanten-Weichzeichnung muss zwischen 0 und 20 liegen.");
  }
  return { hue, tolerance, blurSigma, darken, feather };
}

/**
 * Erstellt die binäre Hue-Maske: 1.0 für Pixel innerhalb von
 * `hue ± tolerance`, sonst 0.0.
 * @param {{width: number, height: number, data: Uint8ClampedArray}} image RGBA-Bild
 * @param {number} hue Ziel-Hue in Grad
 * @param {number} tolerance Toleranz in Grad
 * @returns {Float32Array} Maske mit width*height Werten in [0,1]
 */
export function buildHueMask(image, hue, tolerance) {
  const { width, height, data } = image;
  const mask = new Float32Array(width * height);
  for (let i = 0, p = 0; i < width * height; i++, p += 4) {
    const { h } = rgbToHsv(data[p], data[p + 1], data[p + 2]);
    mask[i] = hueDistance(h, hue) <= tolerance ? 1 : 0;
  }
  return mask;
}

/**
 * Senkt den Value (Helligkeit) aller Pixel eines RGBA-Puffers im HSV-Raum
 * um den Faktor `darken` ab. Der Hue bleibt erhalten — das Bild wird
 * dunkler, nicht verfärbt. Alpha bleibt unangetastet.
 * @param {Uint8ClampedArray} data RGBA-Puffer (wird NICHT verändert)
 * @param {number} darken Anteil der Absenkung [0,1]: v_neu = v * (1 - darken)
 * @returns {Uint8ClampedArray} neuer Puffer mit abgedunkelten Pixeln
 */
export function darkenValue(data, darken) {
  const out = new Uint8ClampedArray(data.length);
  for (let p = 0; p < data.length; p += 4) {
    const { h, s, v } = rgbToHsv(data[p], data[p + 1], data[p + 2]);
    const [r, g, b] = hsvToRgb(h, s, v * (1 - darken));
    out[p] = r;
    out[p + 1] = g;
    out[p + 2] = b;
    out[p + 3] = data[p + 3]; // Alpha übernehmen
  }
  return out;
}

/**
 * Führt die komplette Pipeline aus.
 *
 * @param {{width: number, height: number, data: Uint8ClampedArray}} image
 *        Eingabebild (RGBA), z. B. ImageData vom Canvas. Wird nicht verändert.
 * @param {object} params Parameter (siehe DEFAULT_PARAMS / validateParams)
 * @returns {{image: {width: number, height: number, data: Uint8ClampedArray},
 *            mask: Float32Array, stats: {matched: number, total: number,
 *            elapsedMs: number}}}
 *          Ergebnisbild, die weichgezeichnete Maske und Statistiken
 *          (wie viele Pixel im Hue-Bereich lagen, Laufzeit in ms).
 */
export function processImage(image, params) {
  const t0 = nowMs();
  const { width, height, data } = image;
  const p = validateParams(params);
  const total = width * height;

  // 1) Hue-Maske bauen und zählen, wie viele Pixel im Zielbereich liegen
  const rawMask = buildHueMask(image, p.hue, p.tolerance);
  let matched = 0;
  for (let i = 0; i < total; i++) matched += rawMask[i];

  // 2) Maske weichzeichnen (Feather) -> weiche Kanten beim Compositing
  const mask = p.feather > 0 ? blurFloat(rawMask, width, height, p.feather) : rawMask;

  // 3) Hintergrund: komplettes Bild stark blurren, dann Value absenken
  const blurred = blurRgba(data, width, height, p.blurSigma);
  const background = p.darken > 0 ? darkenValue(blurred, p.darken) : blurred;

  // 4) Compositing pro Kanal: out = m*original + (1-m)*hintergrund
  const out = new Uint8ClampedArray(data.length);
  for (let i = 0, px = 0; i < total; i++, px += 4) {
    const m = clamp(mask[i], 0, 1);
    const inv = 1 - m;
    out[px]     = Math.round(m * data[px]     + inv * background[px]);
    out[px + 1] = Math.round(m * data[px + 1] + inv * background[px + 1]);
    out[px + 2] = Math.round(m * data[px + 2] + inv * background[px + 2]);
    out[px + 3] = data[px + 3]; // Alpha bleibt immer original
  }

  return {
    image: { width, height, data: out },
    mask,
    stats: { matched, total, elapsedMs: nowMs() - t0 },
  };
}

/**
 * Zeitquelle als Millisekunden. Im Browser `performance.now()`, in Node
 * `perf_hooks.performance.now()` — beide liefern eine monotone Uhr.
 */
function nowMs() {
  if (typeof performance !== "undefined" && performance.now) return performance.now();
  // Fallback (ältere Umgebungen): Date.now()
  return Date.now();
}
