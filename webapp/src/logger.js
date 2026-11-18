/**
 * logger.js — Frontend-Logging der Skintone-Web-App (reines Modul, in Node testbar).
 *
 * Jeder Log-Eintrag wird
 *   1. auf die Browser-Konsole geschrieben (wie bisher) und
 *   2. per Transport an den Flask-Endpunkt POST /api/log geschickt, der ihn
 *      in webapplogs/browser.log ablegt.
 *
 * Damit landen auch unbehandelte Fehler (window.onerror, unhandledrejection)
 * automatisch im Log — z. B. "undefined is not an object (evaluating
 * 'el.hue.value')" samt Stacktrace, Datei und Zeilennummer.
 *
 * Aufbau:
 *   - createLogger({transport, consoleObj, now}): liefert {debug, info,
 *     warning, error, log}. Ohne Transport (z. B. in Node-Tests) wird nur
 *     die Konsole bedient und der Eintrag zurückgegeben.
 *   - createBrowserTransport(endpoint): Transport via navigator.sendBeacon
 *     (überlebt auch pagehide) mit fetch-Fallback.
 *   - installGlobalErrorHandlers(logger, target): hängt window.onerror und
 *     unhandledrejection ein.
 */

export const LOG_LEVELS = ["debug", "info", "warning", "error"];

/**
 * Erzeugt einen Logger.
 * @param {object} [opts]
 * @param {(entry: object) => void} [opts.transport] z. B. createBrowserTransport()
 * @param {object} [opts.consoleObj] Konsole (Default: globales console)
 * @param {() => string} [opts.now] Zeitstempel-Funktion (ISO-String)
 */
export function createLogger(opts = {}) {
  const {
    transport = null,
    consoleObj = typeof console !== "undefined" ? console : null,
    now = () => new Date().toISOString(),
  } = opts;

  /**
   * Erzeugt einen Log-Eintrag, schreibt ihn auf die Konsole und an den Transport.
   * @param {string} level einer von LOG_LEVELS (Unbekanntes wird zu "info")
   * @param {string} message Klartext, was passiert ist
   * @param {*} [data] optionale strukturierte Zusatzdaten (Objekte, Stacktraces …)
   * @returns {object} der erzeugte Eintrag
   */
  function log(level, message, data = null) {
    if (!LOG_LEVELS.includes(level)) level = "info";
    const entry = {
      level,
      message: String(message),
      data: data ?? null,
      timestamp: now(),
      url: typeof location !== "undefined" ? location.href : null,
      userAgent: typeof navigator !== "undefined" && navigator.userAgent ? navigator.userAgent : null,
    };
    if (consoleObj) {
      const fn =
        level === "warning" ? consoleObj.warn :
        level === "error" ? consoleObj.error :
        level === "debug" ? (consoleObj.debug || consoleObj.log) :
        consoleObj.info || consoleObj.log;
      try {
        fn.call(consoleObj, `[${entry.timestamp}] ${level.toUpperCase()} | ${entry.message}`, data ?? "");
      } catch { /* Konsole darf nie die App stoppen */ }
    }
    if (transport) {
      try { transport(entry); } catch { /* Transport darf nie die App stoppen */ }
    }
    return entry;
  }

  return {
    debug: (message, data) => log("debug", message, data),
    info: (message, data) => log("info", message, data),
    warning: (message, data) => log("warning", message, data),
    error: (message, data) => log("error", message, data),
    log,
  };
}

/**
 * Transport für den Browser: schickt jeden Eintrag als JSON-POST an den
 * Flask-Endpunkt (Default /api/log). sendBeacon wird bevorzugt, weil es
 * auch beim Schließen der Seite noch zugestellt wird; sonst fetch mit
 * keepalive. Fehler werden geschluckt (Logging darf nie blockieren).
 * @param {string} endpoint URL des Log-Endpunkts
 */
export function createBrowserTransport(endpoint = "/api/log") {
  return (entry) => {
    const payload = JSON.stringify(entry);
    if (typeof navigator !== "undefined" && navigator.sendBeacon) {
      navigator.sendBeacon(endpoint, new Blob([payload], { type: "application/json" }));
    } else if (typeof fetch !== "undefined") {
      fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
        keepalive: true,
      }).catch(() => {});
    }
  };
}

/**
 * Hängt globale Fehler-Handler ein, damit unbehandelte Fehler und
 * abgelehnte Promises automatisch mit Stacktrace ins Log wandern.
 * @param {object} logger Ergebnis von createLogger()
 * @param {object} [target] Default: window (in Node-Tests ein eigener EventTarget)
 */
export function installGlobalErrorHandlers(logger, target = typeof window !== "undefined" ? window : null) {
  if (!target || typeof target.addEventListener !== "function") return;
  target.addEventListener("error", (event) => {
    logger.error(`window.onerror: ${event.message}`, {
      filename: event.filename ?? null,
      lineno: event.lineno ?? null,
      colno: event.colno ?? null,
      stack: event.error && event.error.stack ? String(event.error.stack) : null,
    });
  });
  target.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    logger.error(`unhandledrejection: ${reason && reason.message ? reason.message : String(reason)}`, {
      stack: reason && reason.stack ? String(reason.stack) : null,
    });
  });
}
