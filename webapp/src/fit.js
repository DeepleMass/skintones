/**
 * fit.js — Skalierung des Bildes auf die Fenstergröße (reines Modul, in Node testbar).
 *
 * computeFitScale() liefert den Skalierungsfaktor, mit dem ein Bild so
 * verkleinert ODER vergrößert wird, dass es in den verfügbaren Anzeigebereich
 * passt. Das Ergebnisbild wird als große Bühne dargestellt und bekommt
 * deshalb den kompletten Bereich; das Original liegt als kleines
 * Bild-im-Bild (PiP) darüber und wird per CSS verkleinert angezeigt.
 * Eine absolute Obergrenze (absMax) verhindert absurd große Puffer.
 */

/** Absolute Obergrenze der Kantenlänge für die Verarbeitung (Performance). */
export const ABS_MAX_EDGE = 1280;

/**
 * Skalierungsfaktor, damit ein Bild der Größe imgW×imgH in den verfügbaren
 * Bereich availW×availH passt (hoch- oder herunterskaliert, Faktor kann > 1
 * sein, da auch hochskaliert werden darf).
 *
 * @param {number} imgW Bildbreite in px
 * @param {number} imgH Bildhöhe in px
 * @param {number} availW verfügbarer Anzeigebereich Breite in px
 * @param {number} availH verfügbarer Anzeigebereich Höhe in px
 * @param {number} [absMax] absolute Obergrenze der Kantenlänge nach dem Scaling
 * @returns {number} Skalierungsfaktor (> 0)
 */
export function computeFitScale(imgW, imgH, availW, availH, absMax = ABS_MAX_EDGE) {
  if (!(imgW > 0) || !(imgH > 0)) return 1;
  const fit = Math.min(availW / imgW, availH / imgH);
  return Math.min(fit, absMax / Math.max(imgW, imgH));
}
