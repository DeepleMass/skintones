/**
 * demo.js — Erzeugt ein synthetisches "Portrait", damit die App sofort
 * ausprobierbar ist (ohne Upload/Webcam). Gleiches Verfahren wie im
 * Rust-Bruderprojekt: einfarbiger Hintergrund + Gesichts-Ellipse in
 * einem Hautton.
 *
 * Reine Funktion auf {width, height, data} — nutzbar im Browser (Canvas)
 * und in Node (Tests).
 */

import { hsvToRgb } from "./hsv.js";

/**
 * Baut ein Demo-Portrait: Hintergrund in Blau (Hue ~210°), Gesicht als
 * Ellipse in einem Hautton (Hue ~25°), dazu eine dunklere "Schulter"-Ellipse.
 * @param {number} width Breite in Pixeln
 * @param {number} height Höhe in Pixeln
 * @returns {{width: number, height: number, data: Uint8ClampedArray}} RGBA-Bild
 */
export function createDemoImage(width = 640, height = 480) {
  const data = new Uint8ClampedArray(width * height * 4);

  // Farbkonstanten im HSV-Raum
  const backgroundHsv = { h: 210, s: 0.55, v: 0.8 };  // bläulicher Hintergrund
  const skinHsv = { h: 25, s: 0.45, v: 0.85 };         // Hautton
  const shoulderHsv = { h: 220, s: 0.35, v: 0.35 };    // dunkle Kleidung

  const [br, bg, bb] = hsvToRgb(backgroundHsv.h, backgroundHsv.s, backgroundHsv.v);
  const [sr, sg, sb] = hsvToRgb(skinHsv.h, skinHsv.s, skinHsv.v);
  const [kr, kg, kb] = hsvToRgb(shoulderHsv.h, shoulderHsv.s, shoulderHsv.v);

  // Ellipsen-Mittelpunkte und -Radien (relativ zur Bildgröße)
  const faceCx = width * 0.5, faceCy = height * 0.42;
  const faceRx = width * 0.22, faceRy = height * 0.3;
  const shoulderCx = width * 0.5, shoulderCy = height * 1.05;
  const shoulderRx = width * 0.42, shoulderRy = height * 0.55;

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      // Normalisierte Ellipsen-Gleichung: < 1 heißt "innen"
      const inFace =
        ((x - faceCx) / faceRx) ** 2 + ((y - faceCy) / faceRy) ** 2 <= 1;
      const inShoulder =
        ((x - shoulderCx) / shoulderRx) ** 2 + ((y - shoulderCy) / shoulderRy) ** 2 <= 1;

      const p = (y * width + x) * 4;
      if (inFace) {
        data[p] = sr; data[p + 1] = sg; data[p + 2] = sb;
      } else if (inShoulder) {
        data[p] = kr; data[p + 1] = kg; data[p + 2] = kb;
      } else {
        data[p] = br; data[p + 1] = bg; data[p + 2] = bb;
      }
      data[p + 3] = 255; // Alpha: voll deckend
    }
  }
  return { width, height, data };
}
