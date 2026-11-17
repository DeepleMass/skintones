/**
 * app.js — UI-Verdrahtung der Skintone-Web-App (nur Browser, Einstieg via index.html).
 *
 * Verantwortlichkeiten:
 *   - Bildquellen: Datei-Upload, Webcam (getUserMedia) mit Foto-Übernahme,
 *     synthetisches Demo-Portrait.
 *   - Parameter: Hue + Toleranz sowie Blur/Value-Absenkung/Feather als
 *     Slider + Zahlfelder (synchron), inkl. Hue-Farbfeld.
 *   - Aktionen: Verarbeiten, Zurücksetzen (Restart), Ergebnis speichern (PNG).
 *   - Anzeige: Original und Ergebnis auf zwei Canvases + Statuszeile mit
 *     Statistik (Treffer-Anteil, Laufzeit der Pipeline).
 *
 * Die eigentliche Bildverarbeitung liegt in den reinen Modulen
 * hsv.js / blur.js / pipeline.js / demo.js und wird hier nur aufgerufen.
 */

import { processImage, validateParams, DEFAULT_PARAMS } from "./pipeline.js";
import { createDemoImage } from "./demo.js";
import { hsvToRgb } from "./hsv.js";

/** Maximale Kantenlänge für die Verarbeitung (Performance im Browser). */
const MAX_WORK_SIZE = 1280;

// ---------------------------------------------------------------------------
// DOM-Elemente einmalig einsammeln
// ---------------------------------------------------------------------------
const el = {
  fileInput: document.getElementById("fileInput"),
  btnLoad: document.getElementById("btnLoad"),
  btnWebcamStart: document.getElementById("btnWebcamStart"),
  btnCapture: document.getElementById("btnCapture"),
  btnWebcamStop: document.getElementById("btnWebcamStop"),
  btnDemo: document.getElementById("btnDemo"),
  btnApply: document.getElementById("btnApply"),
  btnReset: document.getElementById("btnReset"),
  btnSave: document.getElementById("btnSave"),
  webcamSection: document.getElementById("webcamSection"),
  webcamVideo: document.getElementById("webcamVideo"),
  canvasOriginal: document.getElementById("canvasOriginal"),
  canvasResult: document.getElementById("canvasResult"),
  status: document.getElementById("status"),
  huePreview: document.getElementById("huePreview"),
};

// Arbeits-Canvas (nicht sichtbar): darauf liegen die ImageData-Puffer
const workCanvas = document.createElement("canvas");
const workCtx = workCanvas.getContext("2d", { willReadFrequently: true });

/** Aktuelles Originalbild als {width, height, data} oder null. */
let currentImage = null;
/** Aktuelles Ergebnisbild oder null. */
let resultImage = null;
/** Webcam-Stream, solange die Kamera läuft. */
let mediaStream = null;

// ---------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------

/** Schreibt eine Meldung in die Statuszeile. */
function setStatus(msg) {
  el.status.textContent = msg;
}

/**
 * Liest die Parameter aus den Eingabefeldern und validiert sie.
 * @returns {object} validierte Parameter für processImage()
 */
function readParams() {
  return validateParams({
    hue: Number(el.hue.value),
    tolerance: Number(el.tolerance.value),
    blurSigma: Number(el.blur.value),
    darken: Number(el.darken.value),
    feather: Number(el.feather.value),
  });
}

/**
 * Synchronisiert Slider <-> Zahlfelder und aktualisiert das Hue-Farbfeld.
 * Wird bei jeder Änderung eines der sechs Parameter aufgerufen.
 */
function syncControlsFrom(source) {
  // Jeweils das andere Feld des Paares aktualisieren
  const pairs = [
    [el.hue, el.hueNum],
    [el.tolerance, el.toleranceNum],
    [el.blur, el.blurNum],
    [el.darken, el.darkenNum],
    [el.feather, el.featherNum],
  ];
  for (const [range, num] of pairs) {
    if (source === range && num.value !== range.value) num.value = range.value;
    if (source === num && range.value !== num.value) range.value = num.value;
  }
  // Farbfeld zeigt den gewählten Hue (S/V moderat für gute Sichtbarkeit)
  const [r, g, b] = hsvToRgb(Number(el.hue.value), 0.7, 0.9);
  el.huePreview.style.background = `rgb(${r}, ${g}, ${b})`;
}

/**
 * Zeichnet ein {width, height, data}-Bild auf eine der beiden Anzeige-Canvases.
 */
function drawToCanvas(canvas, image) {
  canvas.width = image.width;
  canvas.height = image.height;
  const ctx = canvas.getContext("2d");
  ctx.putImageData(new ImageData(image.data, image.width, image.height), 0, 0);
}

/**
 * Übernimmt ein Bild als neues "Original": zeichnet es auf die linke Canvas,
 * aktiviert die Aktions-Buttons und stößt sofort eine Verarbeitung an.
 * @param {{width: number, height: number, data: Uint8ClampedArray}} image RGBA-Bild
 * @param {string} label Herkunft für die Statuszeile (z. B. "Upload")
 */
function setOriginalImage(image, label) {
  currentImage = image;
  resultImage = null;
  drawToCanvas(el.canvasOriginal, image);
  // Ergebnis-Canvas leeren (gleich große Fläche, transparent-schachbrettig via CSS)
  el.canvasResult.width = image.width;
  el.canvasResult.height = image.height;
  el.btnApply.disabled = false;
  el.btnReset.disabled = false;
  el.btnSave.disabled = true;
  setStatus(`${label}: ${image.width}×${image.height} geladen — verarbeitet …`);
  applyFilter(); // sofortiges erstes Ergebnis
}

/**
 * Führt die Pipeline mit den aktuellen UI-Parametern aus und zeigt das
 * Ergebnis rechts an. Misst die Laufzeit und zählt die Hue-Treffer.
 */
function applyFilter() {
  if (!currentImage) return;
  let params;
  try {
    params = readParams();
  } catch (err) {
    setStatus(`Ungültige Parameter: ${err.message}`);
    return;
  }
  const { image, stats } = processImage(currentImage, params);
  resultImage = image;
  drawToCanvas(el.canvasResult, image);
  el.btnSave.disabled = false;
  const pct = ((stats.matched / stats.total) * 100).toFixed(1);
  setStatus(
    `Hue ${params.hue}° ± ${params.tolerance}° — ` +
    `${stats.matched}/${stats.total} Pixel im Bereich (${pct} %), ` +
    `Pipeline in ${stats.elapsedMs.toFixed(1)} ms.`,
  );
}

/**
 * Skaliert ein Bild auf maximal MAX_WORK_SIZE Pixel Kantenlänge herunter
 * (Seitenverhältnis bleibt erhalten) und liefert {width, height, data}.
 * @param {HTMLImageElement|HTMLVideoElement|HTMLCanvasElement} source
 */
function imageElementToData(source) {
  const scale = Math.min(1, MAX_WORK_SIZE / Math.max(source.width || source.videoWidth, source.height || source.videoHeight));
  const w = Math.max(1, Math.round((source.width || source.videoWidth) * scale));
  const h = Math.max(1, Math.round((source.height || source.videoHeight) * scale));
  workCanvas.width = w;
  workCanvas.height = h;
  workCtx.drawImage(source, 0, 0, w, h);
  const { data, width, height } = workCtx.getImageData(0, 0, w, h);
  return { width, height, data: new Uint8ClampedArray(data) };
}

// ---------------------------------------------------------------------------
// Bildquellen
// ---------------------------------------------------------------------------

/** Datei-Upload: liest die gewählte Bilddatei als Image und übernimmt sie. */
function onFileChosen(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    setOriginalImage(imageElementToData(img), `Upload „${file.name}“`);
    URL.revokeObjectURL(url); // Speicher des Blob-URLs wieder freigeben
  };
  img.onerror = () => {
    URL.revokeObjectURL(url);
    setStatus(`Fehler: „${file.name}“ konnte nicht als Bild gelesen werden.`);
  };
  img.src = url;
}

/** Webcam starten: getUserMedia (braucht localhost/HTTPS = "secure context"). */
async function startWebcam() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setStatus("Webcam nicht verfügbar: getUserMedia fehlt (Doch HTTPS/localhost nötig?).");
    return;
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user" }, // Frontkamera bevorzugen (Portrait)
      audio: false,
    });
    el.webcamVideo.srcObject = mediaStream;
    el.webcamSection.classList.remove("hidden");
    el.btnWebcamStart.disabled = true;
    el.btnWebcamStop.disabled = false;
    el.btnCapture.disabled = false;
    setStatus("Webcam läuft — mit „Foto aufnehmen“ einen Frame übernehmen.");
  } catch (err) {
    setStatus(`Webcam-Fehler: ${err.message} (Kamerazugriff erlaubt?)`);
  }
}

/** Webcam stoppen: alle Tracks beenden, Vorschau ausblenden. */
function stopWebcam() {
  if (mediaStream) {
    for (const track of mediaStream.getTracks()) track.stop();
    mediaStream = null;
  }
  el.webcamVideo.srcObject = null;
  el.webcamSection.classList.add("hidden");
  el.btnWebcamStart.disabled = false;
  el.btnWebcamStop.disabled = true;
  el.btnCapture.disabled = true;
  setStatus("Webcam gestoppt.");
}

/** Foto aufnehmen: aktueller Webcam-Frame wird als Original übernommen. */
function captureWebcamFrame() {
  if (!mediaStream) return;
  setOriginalImage(imageElementToData(el.webcamVideo), "Webcam-Foto");
}

// ---------------------------------------------------------------------------
// Event-Verdrahtung (alle Buttons und Eingabefelder)
// ---------------------------------------------------------------------------
el.btnLoad.addEventListener("click", () => el.fileInput.click());
el.fileInput.addEventListener("change", onFileChosen);
el.btnWebcamStart.addEventListener("click", startWebcam);
el.btnWebcamStop.addEventListener("click", stopWebcam);
el.btnCapture.addEventListener("click", captureWebcamFrame);
el.btnDemo.addEventListener("click", () => {
  setOriginalImage(createDemoImage(640, 480), "Demo-Portrait");
});
el.btnApply.addEventListener("click", applyFilter);

/** Zurücksetzen (Restart): Ergebnis entfernen, Original bleibt stehen. */
el.btnReset.addEventListener("click", () => {
  if (!currentImage) return;
  resultImage = null;
  el.canvasResult.width = currentImage.width;
  el.canvasResult.height = currentImage.height;
  el.btnSave.disabled = true;
  setStatus("Zurückgesetzt — Original ist wieder unverändert sichtbar.");
});

/** Ergebnis als PNG speichern (Download über einen temporären Link). */
el.btnSave.addEventListener("click", () => {
  if (!resultImage) return;
  const out = document.createElement("canvas");
  out.width = resultImage.width;
  out.height = resultImage.height;
  out.getContext("2d").putImageData(
    new ImageData(resultImage.data, resultImage.width, resultImage.height), 0, 0,
  );
  const link = document.createElement("a");
  link.download = "skintone-ergebnis.png";
  link.href = out.toDataURL("image/png");
  link.click();
  setStatus("Ergebnis als „skintone-ergebnis.png“ gespeichert.");
});

// Slider + Zahlfelder synchronisieren; bei Änderung an einem Filter-Parameter
// und geladenem Bild sofort neu rechnen (Live-Vorschau)
const paramInputs = ["hue", "tolerance", "blur", "darken", "feather"];
for (const id of paramInputs) {
  const range = document.getElementById(id);
  const num = document.getElementById(id + "Num");
  range.addEventListener("input", () => { syncControlsFrom(range); applyFilter(); });
  num.addEventListener("input", () => { syncControlsFrom(num); applyFilter(); });
}

// Beim Start: Default-Werte in die Felder eintragen und Farbfeld setzen
for (const [id, key] of [["hue", "hue"], ["tolerance", "tolerance"], ["blur", "blurSigma"], ["darken", "darken"], ["feather", "feather"]]) {
  document.getElementById(id).value = DEFAULT_PARAMS[key];
  document.getElementById(id + "Num").value = DEFAULT_PARAMS[key];
}
syncControlsFrom(el.hue);
