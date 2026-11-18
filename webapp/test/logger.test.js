/**
 * logger.test.js — Tests für das Frontend-Logging (src/logger.js).
 * Läuft in Node: der Transport wird durch einen Fake ersetzt, window/location
 * sind in Node nicht definiert — der Logger darf deshalb nicht abstürzen.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { LOG_LEVELS, createLogger, createBrowserTransport, installGlobalErrorHandlers } from "../src/logger.js";

test("log() erzeugt Einträge mit Level, Message, Zeitstempel und schickt sie an den Transport", () => {
  const sent = [];
  const logger = createLogger({
    transport: (entry) => sent.push(entry),
    consoleObj: null, // Konsole im Test nicht beschreiben
    now: () => "2026-11-18T01:02:03.000Z",
  });
  const entry = logger.error("pipeline.invalidParams", { error: "undefined is not an object", rawInputs: { hue: "25" } });
  assert.equal(entry.level, "error");
  assert.equal(entry.message, "pipeline.invalidParams");
  assert.deepEqual(entry.data, { error: "undefined is not an object", rawInputs: { hue: "25" } });
  assert.equal(entry.timestamp, "2026-11-18T01:02:03.000Z");
  // in Node gibt es kein location -> null statt Absturz; navigator existiert
  // ab Node 21 global (userAgent "Node.js/..."), darf aber auch null sein
  assert.equal(entry.url, null);
  assert.ok(entry.userAgent === null || typeof entry.userAgent === "string");
  assert.equal(sent.length, 1);
  assert.equal(sent[0], entry, "Transport bekommt genau den Eintrag");
});

test("unbekannter Level wird zu info; Kurzschluss-Methoden debug/info/warning/error funktionieren", () => {
  const sent = [];
  const logger = createLogger({ transport: (e) => sent.push(e), consoleObj: null });
  logger.log("kaputt", "x");
  logger.debug("d"); logger.info("i"); logger.warning("w"); logger.error("e");
  assert.deepEqual(sent.map((e) => e.level), ["info", "debug", "info", "warning", "error"]);
  assert.ok(LOG_LEVELS.includes("error"));
});

test("Transport-Fehler und kaputte Konsole dürfen log() nicht werfen", () => {
  const logger = createLogger({
    transport: () => { throw new Error("Netzwerk weg"); },
    consoleObj: { warn() { throw new Error("Konsole kaputt"); }, error() { throw new Error("Konsole kaputt"); } },
  });
  assert.doesNotThrow(() => logger.warning("trotzdem loggen"));
});

test("createBrowserTransport liefert eine Funktion (Body-POST erst im Browser)", () => {
  assert.equal(typeof createBrowserTransport("/api/log"), "function");
  assert.equal(typeof createBrowserTransport(), "function");
});

test("installGlobalErrorHandlers logt window.onerror und unhandledrejection mit Stack", () => {
  const sent = [];
  const logger = createLogger({ transport: (e) => sent.push(e), consoleObj: null });
  // Minimaler EventTarget als window-Ersatz
  const listeners = {};
  const fakeWindow = { addEventListener: (type, fn) => { listeners[type] = fn; } };
  installGlobalErrorHandlers(logger, fakeWindow);
  assert.equal(typeof listeners.error, "function");
  assert.equal(typeof listeners.unhandledrejection, "function");

  const boom = new Error("undefined is not an object (evaluating 'el.hue.value')");
  listeners.error({ message: boom.message, filename: "app.js", lineno: 182, colno: 20, error: boom });
  listeners.unhandledrejection({ reason: boom });

  assert.equal(sent.length, 2);
  assert.equal(sent[0].level, "error");
  assert.match(sent[0].message, /window\.onerror: undefined is not an object/);
  assert.equal(sent[0].data.filename, "app.js");
  assert.equal(sent[0].data.lineno, 182);
  assert.match(sent[0].data.stack, /el\.hue\.value/);
  assert.match(sent[1].message, /unhandledrejection/);
});

test("installGlobalErrorHandlers ohne window (Node) ist ein No-Op", () => {
  const logger = createLogger({ consoleObj: null });
  assert.doesNotThrow(() => installGlobalErrorHandlers(logger, null));
});
