/**
 * blur.js — Separabler Gaussian-Blur für RGBA-Bilder und f32-Masken.
 *
 * "Separabel" heißt: der 2D-Gaussian-Kernel wird in zwei 1D-Pässe zerlegt
 * (erst horizontal, dann vertikal). Das ist O(n * k) statt O(n * k²) und
 * damit auch für Portraits in voller Auflösung schnell genug.
 *
 * Alle Funktionen arbeiten auf flachen Puffern und sind rein — sie verändern
 * die Eingabe nicht, sondern liefern eine neue Kopie. Dadurch sind sie in
 * Node ohne Browser testbar.
 */

/**
 * Erzeugt einen normalisierten 1D-Gaussian-Kernel.
 * @param {number} sigma Standardabweichung; bei sigma <= 0 kommt ein
 *                       Delta-Impuls [1] heraus (identische Abbildung).
 * @returns {Float32Array} Kernel ungerader Länge (mindestens 1), Summe = 1
 */
export function gaussianKernel(sigma) {
  if (sigma <= 0) return new Float32Array([1]);
  // Radius = 3*sigma deckt >99.7 % der Glockenkurve ab
  const radius = Math.max(1, Math.ceil(3 * sigma));
  const size = 2 * radius + 1;
  const kernel = new Float32Array(size);
  const norm = 1 / (sigma * Math.sqrt(2 * Math.PI));
  let sum = 0;
  for (let i = -radius; i <= radius; i++) {
    const w = norm * Math.exp(-(i * i) / (2 * sigma * sigma));
    kernel[i + radius] = w;
    sum += w;
  }
  // Normalisieren, damit die Gesamthelligkeit des Bildes erhalten bleibt
  for (let i = 0; i < size; i++) kernel[i] /= sum;
  return kernel;
}

/**
 * Faltet ein eindimensionales Signal mit dem Kernel (Rand per Clamping,
 * d. h. der Randpixel wird so oft wiederholt wie nötig — vermeidet
 * Abdunklung an den Bildrändern).
 * @param {ArrayLike<number>} src Quellpuffer
 * @param {Float32Array} dst Zielpuffer (gleiche Länge wie src)
 * @param {Float32Array} kernel Kernel aus gaussianKernel()
 */
function convolve1D(src, dst, kernel) {
  const n = src.length;
  const radius = (kernel.length - 1) / 2;
  for (let i = 0; i < n; i++) {
    let acc = 0;
    for (let k = -radius; k <= radius; k++) {
      // Randbehandlung: Index auf [0, n-1] klemmen
      const j = i + k < 0 ? 0 : i + k >= n ? n - 1 : i + k;
      acc += kernel[k + radius] * src[j];
    }
    dst[i] = acc;
  }
}

/**
 * Separabler Gaussian-Blur auf einem RGBA-Bildpuffer.
 * @param {Uint8ClampedArray} src RGBA-Daten (Länge = width*height*4)
 * @param {number} width Bildbreite in Pixeln
 * @param {number} height Bildhöhe in Pixeln
 * @param {number} sigma Blur-Stärke
 * @returns {Uint8ClampedArray} neuer RGBA-Puffer (src bleibt unverändert)
 */
export function blurRgba(src, width, height, sigma) {
  const kernel = gaussianKernel(sigma);
  const pixelCount = width * height;
  const channels = 4;
  const tmp = new Float32Array(src.length);
  const out = new Float32Array(src.length);

  // Pass 1: horizontal — zeilenweise über alle 4 Kanäle
  for (let y = 0; y < height; y++) {
    const rowStart = y * width * channels;
    for (let c = 0; c < channels; c++) {
      // Kanal c der Zeile in einen Hilfsvektor kopieren
      const line = new Float32Array(width);
      for (let x = 0; x < width; x++) line[x] = src[rowStart + x * channels + c];
      const lineOut = new Float32Array(width);
      convolve1D(line, lineOut, kernel);
      for (let x = 0; x < width; x++) tmp[rowStart + x * channels + c] = lineOut[x];
    }
  }

  // Pass 2: vertikal — spaltenweise über alle 4 Kanäle
  for (let x = 0; x < width; x++) {
    for (let c = 0; c < channels; c++) {
      const col = new Float32Array(height);
      for (let y = 0; y < height; y++) col[y] = tmp[(y * width + x) * channels + c];
      const colOut = new Float32Array(height);
      convolve1D(col, colOut, kernel);
      for (let y = 0; y < height; y++) out[(y * width + x) * channels + c] = colOut[y];
    }
  }

  // Float-Ergebnis zurück auf [0,255] runden; Alpha bleibt faktisch unverändert,
  // wird aber regulär mitgeblurrt (bei deckendem Alpha 255 überall = kein Effekt)
  const result = new Uint8ClampedArray(out.length);
  for (let i = 0; i < out.length; i++) result[i] = Math.round(out[i]);
  return result;
}

/**
 * Gaussian-Blur auf einer eindimensionalen Float-Maske (z. B. für das
 * Weichzeichnen der Hue-Maske = "Feather").
 * @param {Float32Array} src Maske (ein Wert pro Pixel)
 * @param {number} width Bildbreite
 * @param {number} height Bildhöhe
 * @param {number} sigma Blur-Stärke
 * @returns {Float32Array} neue, geglättete Maske
 */
export function blurFloat(src, width, height, sigma) {
  const kernel = gaussianKernel(sigma);
  const tmp = new Float32Array(src.length);
  const out = new Float32Array(src.length);

  // Horizontal
  for (let y = 0; y < height; y++) {
    const rowStart = y * width;
    const line = src.subarray(rowStart, rowStart + width);
    const lineOut = new Float32Array(width);
    convolve1D(line, lineOut, kernel);
    tmp.set(lineOut, rowStart);
  }
  // Vertikal
  for (let x = 0; x < width; x++) {
    const col = new Float32Array(height);
    for (let y = 0; y < height; y++) col[y] = tmp[y * width + x];
    const colOut = new Float32Array(height);
    convolve1D(col, colOut, kernel);
    for (let y = 0; y < height; y++) out[y * width + x] = colOut[y];
  }
  return out;
}
