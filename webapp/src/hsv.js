/**
 * hsv.js — Farbkonvertierung RGB <-> HSV und Hue-Hilfsfunktionen.
 *
 * Konventionen in diesem Projekt:
 *   - r, g, b liegen in [0, 255] (wie in ImageData/Uint8ClampedArray).
 *   - h (Hue) liegt in Grad in [0, 360).
 *   - s (Saturation) und v (Value) liegen in [0, 1].
 *   - Graustufen (s = 0) haben fachlich keinen definierten Hue;
 *     wir verwenden die dokumentierte Konvention h = 0.
 *
 * Das Modul ist rein (keine DOM-/Canvas-Abhängigkeiten) und damit in Node
 * genauso testbar wie im Browser.
 */

/** Klemmt einen Wert in den Bereich [min, max]. */
export function clamp(value, min, max) {
  return value < min ? min : value > max ? max : value;
}

/** Normalisiert einen Hue-Wert per Modulo in den Bereich [0, 360). */
export function wrapHue(h) {
  // Doppel-Modulo: funktioniert auch für negative Werte und liefert nie -0
  return ((h % 360) + 360) % 360;
}

/**
 * Wandelt einen RGB-Pixelwert in HSV um.
 * @param {number} r Rotanteil [0,255]
 * @param {number} g Grünanteil [0,255]
 * @param {number} b Blauanteil [0,255]
 * @returns {{h: number, s: number, v: number}} Hue in Grad [0,360), s/v in [0,1]
 */
export function rgbToHsv(r, g, b) {
  // Umrechnung auf [0,1]
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;

  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const delta = max - min; // Farbabstand = Sättigungsgrundlage

  // Value ist schlicht der hellste Kanal
  const v = max;

  // Saturation: Anteil des delta am Maximalwert; bei Grau (max=0) definiert als 0
  const s = max === 0 ? 0 : delta / max;

  // Hue: Sektor des Farbkreises, in dem der Maximalwert liegt
  let h = 0;
  if (delta !== 0) {
    if (max === rn) {
      // Sektor zwischen Rot und Grün/Gelb: 60 * ((g-b)/delta mod 6)
      h = 60 * (((gn - bn) / delta) % 6);
    } else if (max === gn) {
      // Sektor zwischen Grün und Blau
      h = 60 * ((bn - rn) / delta + 2);
    } else {
      // Sektor zwischen Blau und Rot
      h = 60 * ((rn - gn) / delta + 4);
    }
  }
  // Negative Werte (Rotsektor "unter" 0) in den Bereich [0,360) heben
  h = wrapHue(h);
  // Graustufen: Konvention h = 0 (fachlich undefiniert, aber eindeutig)
  if (s === 0) h = 0;

  return { h, s, v };
}

/**
 * Wandelt HSV zurück in einen RGB-Pixelwert.
 * @param {number} h Hue in Grad (beliebig, wird per wrapHue normalisiert)
 * @param {number} s Saturation [0,1]
 * @param {number} v Value [0,1]
 * @returns {[number, number, number]} [r, g, b] in [0,255]
 */
export function hsvToRgb(h, s, v) {
  h = wrapHue(h);
  s = clamp(s, 0, 1);
  v = clamp(v, 0, 1);

  const c = v * s; // Chroma: maximaler Farbanteil
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1)); // Zwischenwert im Sektor
  const m = v - c; // Offset, der am Ende auf alle Kanäle addiert wird

  let rn, gn, bn;
  if (h < 60)       { rn = c; gn = x; bn = 0; }
  else if (h < 120) { rn = x; gn = c; bn = 0; }
  else if (h < 180) { rn = 0; gn = c; bn = x; }
  else if (h < 240) { rn = 0; gn = x; bn = c; }
  else if (h < 300) { rn = x; gn = 0; bn = c; }
  else              { rn = c; gn = 0; bn = x; }

  return [
    Math.round((rn + m) * 255),
    Math.round((gn + m) * 255),
    Math.round((bn + m) * 255),
  ];
}

/**
 * Zirkulare Distanz zweier Hue-Werte in Grad, Ergebnis in [0, 180].
 * Wichtig: Der Farbkreis läuft bei 0/360 nahtlos weiter, daher ist z. B.
 * der Abstand von 350° zu 10° nur 20° und nicht 340°.
 * @param {number} a erster Hue in Grad
 * @param {number} b zweiter Hue in Grad
 * @returns {number} Distanz in Grad [0, 180]
 */
export function hueDistance(a, b) {
  const d = Math.abs(wrapHue(a) - wrapHue(b)) % 360;
  return d > 180 ? 360 - d : d;
}

/**
 * Prüft, ob ein Pixel-Hue innerhalb der Toleranz um den Ziel-Hue liegt.
 * Die Grenze ist inklusive: Distanz == Toleranz zählt als Treffer.
 * @param {number} pixelHue Hue des Pixels in Grad
 * @param {number} targetHue gewünschter Hue in Grad
 * @param {number} tolerance erlaubte Abweichung in Grad [0, 180]
 * @returns {boolean} true, wenn der Pixel im Zielbereich liegt
 */
export function isHueMatch(pixelHue, targetHue, tolerance) {
  return hueDistance(pixelHue, targetHue) <= tolerance;
}
