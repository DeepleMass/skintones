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
import { createI18n, LANGUAGES, LANGUAGE_NAMES } from "./i18n.js";
import { createLogger, createBrowserTransport, installGlobalErrorHandlers } from "./logger.js";
import { computeFitScale, ABS_MAX_EDGE } from "./fit.js";

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
  btnTheme: document.getElementById("btnTheme"),
  btnLang: document.getElementById("btnLang"),
  langCode: document.getElementById("langCode"),
  // Parameter-Inputs (Slider + Zahlfelder) — readParams()/syncControlsFrom()
  // greifen über el darauf zu; fehlten früher und sorgten für
  // "undefined is not an object (evaluating 'el.hue.value')".
  hue: document.getElementById("hue"),
  hueNum: document.getElementById("hueNum"),
  tolerance: document.getElementById("tolerance"),
  toleranceNum: document.getElementById("toleranceNum"),
  blur: document.getElementById("blur"),
  blurNum: document.getElementById("blurNum"),
  darken: document.getElementById("darken"),
  darkenNum: document.getElementById("darkenNum"),
  feather: document.getElementById("feather"),
  featherNum: document.getElementById("featherNum"),
  views: document.getElementById("views"),
  langMenu: document.getElementById("langMenu"),
};

// Frontend-Logger: schreibt auf die Konsole UND per POST /api/log nach
// webapplogs/browser.log (serverseitig). Globale Fehler landen automatisch im Log.
const logger = createLogger({ transport: createBrowserTransport("/api/log") });
installGlobalErrorHandlers(logger);

// Arbeits-Canvas (nicht sichtbar): darauf liegen die ImageData-Puffer
const workCanvas = document.createElement("canvas");
const workCtx = workCanvas.getContext("2d", { willReadFrequently: true });
// Roh-Canvas in Originalauflösung (Quelle für das Skalieren auf die Fenstergröße)
const rawCanvas = document.createElement("canvas");
const rawCtx = rawCanvas.getContext("2d", { willReadFrequently: true });

/** Aktuelles Originalbild (auf Fenstergröße skaliert) als {width, height, data} oder null. */
let currentImage = null;
/** Unskaliertes Original + Loader, um bei Fenster-Resize neu zu fitten. */
let rawImage = null;
let currentLoader = null;
let currentLabelKey = "source.demo";
let currentLabelParams = null;
/** Aktuelles Ergebnisbild oder null. */
let resultImage = null;
/** Webcam-Stream, solange die Kamera läuft. */
let mediaStream = null;

// ---------------------------------------------------------------------------
// Theme (Daylight/Dark) und Sprache (i18n)
// ---------------------------------------------------------------------------

/** Aktives i18n-Objekt; Startsprache aus localStorage, sonst Deutsch. */
const i18n = createI18n(localStorage.getItem("skintone-lang") || "de");

/** Zuletzt gesetzte Statusmeldung als {key, params}, damit ein Sprachwechsel
 *  die Statuszeile direkt in die neue Sprache übersetzen kann. */
let lastStatus = { key: "status.ready", params: null };

/**
 * Wendet das Theme an und speichert die Wahl (Default: "light" = Daylight).
 * @param {string} theme "light" oder "dark"
 */
function applyTheme(theme) {
  const value = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = value;
  localStorage.setItem("skintone-theme", value);
}

/** Aktualisiert den Sprachcode auf der Sprach-Schaltfläche. */
function updateLangButton() {
  el.langCode.textContent = i18n.lang.toUpperCase();
  el.btnLang.title = `${i18n.t("lang.toggle")} — ${LANGUAGE_NAMES[i18n.lang]}`;
}

// ---------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------

/**
 * Schreibt eine übersetzte Meldung in die Statuszeile.
 * @param {string} key i18n-Schlüssel, z. B. "status.ready"
 * @param {object} [params] Platzhalter-Werte für die Vorlage
 */
function setStatus(key, params) {
  lastStatus = { key, params };
  el.status.textContent = i18n.t(key, params);
  // Statusmeldungen mitloggen (invalidParams zusätzlich als Fehler mit Details)
  if (key === "status.invalidParams") {
    logger.error("status", { key, params });
  } else {
    logger.debug("status", { key, params });
  }
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
 * Verfügbarer Anzeigebereich für die Bühne (Ergebnis-Canvas): Fenster bzw.
 * views-Bereich minus Header, Steuerungsbereich und Statuszeile (plus Puffer
 * für Paddings/Gaps). Das Original liegt als PiP darüber und braucht keinen
 * eigenen Platz.
 */
function displayBox() {
  const header = document.querySelector("header");
  const controls = document.querySelector(".controls");
  const reserved = (header ? header.offsetHeight : 0) + (controls ? controls.offsetHeight : 0) +
    el.status.offsetHeight + 96;
  return {
    availW: Math.max(280, (el.views.clientWidth || window.innerWidth) - 48),
    availH: Math.max(200, window.innerHeight - reserved),
  };
}

/**
 * Skaliert ein Rohbild {width, height, data} so auf die Fenstergröße, dass es
 * samt zweitem Canvas in den Anzeigebereich passt (hoch- oder herunter).
 * Liefert das skalierte Bild plus den Skalierungsfaktor.
 */
function fitToWindow(raw) {
  const box = displayBox();
  const scale = computeFitScale(raw.width, raw.height, box.availW, box.availH, ABS_MAX_EDGE);
  const w = Math.max(1, Math.round(raw.width * scale));
  const h = Math.max(1, Math.round(raw.height * scale));
  rawCanvas.width = raw.width;
  rawCanvas.height = raw.height;
  rawCtx.putImageData(new ImageData(raw.data, raw.width, raw.height), 0, 0);
  workCanvas.width = w;
  workCanvas.height = h;
  workCtx.drawImage(rawCanvas, 0, 0, w, h);
  const { data } = workCtx.getImageData(0, 0, w, h);
  return { width: w, height: h, data: new Uint8ClampedArray(data), scale };
}

/**
 * Übernimmt ein Rohbild (Originalauflösung) als neues "Original": skaliert es
 * auf die Fenstergröße (Ergebnis füllt die Bühne so groß wie möglich), zeichnet
 * es auf beide Canvases (Original als PiP-Overlay), aktiviert die
 * Aktions-Buttons und stößt sofort eine Verarbeitung an.
 * @param {{width: number, height: number, data: Uint8ClampedArray}} raw RGBA-Bild in Originalauflösung
 * @param {string} labelKey i18n-Schlüssel der Herkunft (z. B. "source.demo")
 * @param {object} [labelParams] Platzhalter für den Herkunfts-Schlüssel
 */
function setOriginalImage(raw, labelKey, labelParams) {
  rawImage = raw;
  currentLabelKey = labelKey;
  currentLabelParams = labelParams;
  const fitted = fitToWindow(raw);
  const image = { width: fitted.width, height: fitted.height, data: fitted.data };
  currentImage = image;
  resultImage = null;
  // Rendering: Ergebnis als große Bühne, Original als Bild im Bild (PiP) —
  // beide Canvases bekommen dieselbe (gefittete) Auflösung.
  const orientation = image.height > image.width ? "portrait" : "landscape";
  drawToCanvas(el.canvasOriginal, image);
  // Ergebnis-Canvas leeren (gleich große Fläche, transparent-schachbrettig via CSS)
  el.canvasResult.width = image.width;
  el.canvasResult.height = image.height;
  el.btnApply.disabled = false;
  el.btnReset.disabled = false;
  el.btnSave.disabled = true;
  setStatus("status.loaded", {
    label: i18n.t(labelKey, labelParams),
    width: image.width,
    height: image.height,
  });
  logger.info("image.loaded", {
    labelKey,
    labelParams,
    raw: { width: raw.width, height: raw.height },
    scaled: { width: image.width, height: image.height },
    scale: Number(fitted.scale.toFixed(3)),
    orientation,
  });
  applyFilter(); // sofortiges erstes Ergebnis
}

/**
 * Führt die Pipeline mit den aktuellen UI-Parametern aus und zeigt das
 * Ergebnis rechts an. Misst die Laufzeit und zählt die Hue-Treffer.
 */
function applyFilter() {
  if (!currentImage) return;
  // Rohwerte der Inputs loggen — hilfreich, wenn ein Parameter "undefined" ist
  const rawInputs = {
    hue: el.hue.value, tolerance: el.tolerance.value,
    blur: el.blur.value, darken: el.darken.value, feather: el.feather.value,
  };
  let params;
  try {
    params = readParams();
  } catch (err) {
    logger.error("pipeline.invalidParams", {
      error: String(err), stack: err.stack, rawInputs,
    });
    setStatus("status.invalidParams", { error: err.message });
    return;
  }
  logger.info("pipeline.start", { params, image: { width: currentImage.width, height: currentImage.height } });
  const { image, stats } = processImage(currentImage, params);
  resultImage = image;
  drawToCanvas(el.canvasResult, image);
  el.btnSave.disabled = false;
  const pct = ((stats.matched / stats.total) * 100).toFixed(1);
  setStatus("status.result", {
    hue: params.hue,
    tolerance: params.tolerance,
    matched: stats.matched,
    total: stats.total,
    pct,
    ms: stats.elapsedMs.toFixed(1),
  });
  logger.info("pipeline.done", {
    params, matched: stats.matched, total: stats.total, pct,
    elapsedMs: stats.elapsedMs.toFixed(1), result: { width: image.width, height: image.height },
  });
}

/**
 * Liest ein Bild-Element (img/video/canvas) in ORIGINAL-Auflösung als
 * {width, height, data}. Das Skalieren auf die Fenstergröße macht fitToWindow().
 * @param {HTMLImageElement|HTMLVideoElement|HTMLCanvasElement} source
 */
function elementToRawData(source) {
  const w = source.width || source.videoWidth;
  const h = source.height || source.videoHeight;
  if (!w || !h) return null;
  rawCanvas.width = w;
  rawCanvas.height = h;
  rawCtx.drawImage(source, 0, 0, w, h);
  const { data } = rawCtx.getImageData(0, 0, w, h);
  return { width: w, height: h, data: new Uint8ClampedArray(data) };
}

// ---------------------------------------------------------------------------
// Bildquellen
// ---------------------------------------------------------------------------

/** Datei-Upload: liest die gewählte Bilddatei als Image und übernimmt sie. */
function onFileChosen(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  logger.info("file.chosen", { name: file.name, size: file.size, type: file.type });
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    const raw = elementToRawData(img);
    currentLoader = () => elementToRawData(img); // für Re-Fit bei Fenster-Resize
    setOriginalImage(raw, "source.uploadFile", { name: file.name });
    URL.revokeObjectURL(url); // Speicher des Blob-URLs wieder freigeben
  };
  img.onerror = () => {
    URL.revokeObjectURL(url);
    logger.error("file.loadError", { name: file.name });
    setStatus("status.loadError", { name: file.name });
  };
  img.src = url;
}

/** Webcam starten: getUserMedia (braucht localhost/HTTPS = "secure context"). */
async function startWebcam() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    logger.warning("webcam.unavailable", { reason: "getUserMedia fehlt" });
    setStatus("status.noWebcam");
    return;
  }
  logger.info("webcam.start", { facingMode: "user" });
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
    setStatus("status.webcamRunning");
    logger.info("webcam.running", { tracks: mediaStream.getTracks().map((t) => t.kind) });
  } catch (err) {
    logger.error("webcam.error", { error: String(err), stack: err.stack });
    setStatus("status.webcamError", { error: err.message });
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
  setStatus("status.webcamStopped");
  logger.info("webcam.stopped", {});
}

/** Foto aufnehmen: aktueller Webcam-Frame wird als Original übernommen. */
function captureWebcamFrame() {
  if (!mediaStream) return;
  logger.info("webcam.capture", { videoWidth: el.webcamVideo.videoWidth, videoHeight: el.webcamVideo.videoHeight });
  currentLoader = () => elementToRawData(el.webcamVideo);
  const raw = elementToRawData(el.webcamVideo);
  if (raw) setOriginalImage(raw, "source.webcam");
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
  currentLoader = () => createDemoImage(640, 480);
  setOriginalImage(currentLoader(), "source.demo");
});
el.btnApply.addEventListener("click", applyFilter);

/** Zurücksetzen (Restart): Ergebnis entfernen, Original bleibt stehen. */
el.btnReset.addEventListener("click", () => {
  if (!currentImage) return;
  resultImage = null;
  el.canvasResult.width = currentImage.width;
  el.canvasResult.height = currentImage.height;
  el.btnSave.disabled = true;
  setStatus("status.reset");
  logger.info("ui.reset", { hadResult: resultImage !== null });
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
  setStatus("status.saved");
  logger.info("ui.save", { file: link.download, width: resultImage.width, height: resultImage.height });
});

// Slider + Zahlfelder synchronisieren; bei Änderung an einem Filter-Parameter
// und geladenem Bild sofort neu rechnen (Live-Vorschau)
const paramInputs = ["hue", "tolerance", "blur", "darken", "feather"];
for (const id of paramInputs) {
  const range = document.getElementById(id);
  const num = document.getElementById(id + "Num");
  range.addEventListener("input", () => {
    logger.debug("param.change", { id, source: "range", value: range.value });
    syncControlsFrom(range); applyFilter();
  });
  num.addEventListener("input", () => {
    logger.debug("param.change", { id, source: "number", value: num.value });
    syncControlsFrom(num); applyFilter();
  });
}

// Jeden Button-Klick protokollieren (welcher Button, welcher Text, disabled?)
for (const btn of document.querySelectorAll("button")) {
  btn.addEventListener("click", () => {
    logger.debug("ui.click", { id: btn.id, label: btn.textContent.trim(), disabled: btn.disabled });
  });
}

// Theme wechseln (Daylight <-> Dark); die Wahl bleibt in localStorage erhalten
el.btnTheme.addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(next);
  logger.info("ui.theme", { theme: next });
});

// ---------------------------------------------------------------------------
// Sprachauswahl als Dropdown-Menü unter der Globus-Schaltfläche
// ---------------------------------------------------------------------------

/** Baut die Menüeinträge (Sprache: nativer Name + Code) aus i18n.js auf. */
function buildLangMenu() {
  el.langMenu.innerHTML = "";
  for (const code of LANGUAGES) {
    const item = document.createElement("button");
    item.type = "button";
    item.setAttribute("role", "menuitem");
    item.dataset.lang = code;
    const name = document.createElement("span");
    name.textContent = LANGUAGE_NAMES[code];
    const badge = document.createElement("span");
    badge.className = "code";
    badge.textContent = code.toUpperCase();
    item.append(name, badge);
    item.addEventListener("click", () => selectLang(code));
    el.langMenu.appendChild(item);
  }
}

/** Markiert den aktiven Eintrag im Dropdown. */
function markActiveLang() {
  for (const b of el.langMenu.querySelectorAll("button")) {
    b.classList.toggle("active", b.dataset.lang === i18n.lang);
  }
}

/** Wendet eine Sprache an, übersetzt das DOM und schließt das Menü. */
function selectLang(code) {
  i18n.setLang(code);
  localStorage.setItem("skintone-lang", i18n.lang);
  i18n.applyDom(); // alle Menüeinträge, Labels, Tooltips neu übersetzen
  updateLangButton();
  setStatus(lastStatus.key, lastStatus.params); // Statuszeile neu übersetzen
  markActiveLang();
  el.langMenu.classList.add("hidden");
  logger.info("ui.lang", { lang: i18n.lang, name: LANGUAGE_NAMES[i18n.lang] });
}

// Globus-Button klappt das Menü auf/zu
el.btnLang.addEventListener("click", (event) => {
  event.stopPropagation();
  el.langMenu.classList.toggle("hidden");
  logger.debug("ui.langMenu.toggle", { open: !el.langMenu.classList.contains("hidden") });
});
// Klick außerhalb oder Escape schließt das Menü
document.addEventListener("click", (event) => {
  if (!el.langMenu.classList.contains("hidden") &&
      !el.langMenu.contains(event.target) && !el.btnLang.contains(event.target)) {
    el.langMenu.classList.add("hidden");
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") el.langMenu.classList.add("hidden");
});

// Fenster-Resize: aktuelles Bild neu auf die Fenstergröße skalieren (debounced)
let resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (!currentLoader) return;
    const raw = currentLoader();
    if (!raw) return;
    logger.info("window.resize", {
      innerWidth: window.innerWidth, innerHeight: window.innerHeight,
      raw: { width: raw.width, height: raw.height },
    });
    setOriginalImage(raw, currentLabelKey, currentLabelParams);
  }, 300);
});

// ---------------------------------------------------------------------------
// Default-Image: wird beim Start automatisch geladen (images/default-image.jpg,
// wird vom Flask-Server unter /images/ ausgeliefert)
// ---------------------------------------------------------------------------

/** Pfad des Default-Bildes, relativ zum webapp-Root. */
const DEFAULT_IMAGE_URL = "./images/default-image.jpg";

/**
 * Lädt das Default-Image und übernimmt es als Original (inkl. sofortiger
 * Verarbeitung). Schlägt das Laden fehl (z. B. anderer statischer Server ohne
 * /images/), wird nur eine Warnung geloggt — die App bleibt benutzbar.
 */
async function loadDefaultImage() {
  logger.info("defaultImage.load", { url: DEFAULT_IMAGE_URL });
  try {
    const resp = await fetch(DEFAULT_IMAGE_URL);
    if (!resp.ok) throw new Error(`HTTP ${resp.status} für ${DEFAULT_IMAGE_URL}`);
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = () => reject(new Error(`Decode-Fehler für ${DEFAULT_IMAGE_URL}`));
      img.src = url;
    });
    const raw = elementToRawData(img);
    currentLoader = () => elementToRawData(img); // Re-Fit bei Resize
    setOriginalImage(raw, "source.default");
    logger.info("defaultImage.loaded", { url: DEFAULT_IMAGE_URL, size: blob.size, type: blob.type, raw: { width: raw.width, height: raw.height } });
  } catch (err) {
    logger.warning("defaultImage.loadFailed", { url: DEFAULT_IMAGE_URL, error: String(err) });
  }
}

// Beim Start: Default-Werte in die Felder eintragen und Farbfeld setzen
for (const [id, key] of [["hue", "hue"], ["tolerance", "tolerance"], ["blur", "blurSigma"], ["darken", "darken"], ["feather", "feather"]]) {
  document.getElementById(id).value = DEFAULT_PARAMS[key];
  document.getElementById(id + "Num").value = DEFAULT_PARAMS[key];
}
syncControlsFrom(el.hue);

// Beim Start: gespeichertes Theme + Sprache anwenden und Texte übersetzen
try {
  applyTheme(localStorage.getItem("skintone-theme") || "light");
  buildLangMenu();
  i18n.applyDom();
  updateLangButton();
  markActiveLang();
  setStatus("status.ready");
  logger.info("app.boot", {
    theme: document.documentElement.dataset.theme,
    lang: i18n.lang,
    defaultParams: DEFAULT_PARAMS,
    defaultImage: DEFAULT_IMAGE_URL,
    hasWebcam: Boolean(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
    secureContext: typeof isSecureContext !== "undefined" ? isSecureContext : null,
    viewport: { width: window.innerWidth, height: window.innerHeight },
  });
  loadDefaultImage(); // Default-Image immer beim Start laden
} catch (err) {
  // Falls schon das Initialisieren fehlschlägt: trotzdem ins Log schreiben
  logger.error("app.initError", { error: String(err), stack: err.stack });
  setStatus("status.invalidParams", { error: String(err) });
}
