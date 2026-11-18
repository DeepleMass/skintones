/**
 * i18n.test.js — Tests für das Mehrsprachigkeits-Modul src/i18n.js.
 * Läuft in Node (kein DOM nötig): prüft Vollständigkeit und Konsistenz
 * der Übersetzungen sowie das t()-Verhalten von createI18n().
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { LANGUAGES, LANGUAGE_NAMES, STRINGS, createI18n } from "../src/i18n.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), ".."); // webapp/

test("alle 7 Sprachen sind vorhanden (de, en, fr, es, it, zh, ja)", () => {
  assert.deepEqual(LANGUAGES, ["de", "en", "fr", "es", "it", "zh", "ja"]);
  for (const lang of LANGUAGES) {
    assert.ok(STRINGS[lang], `fehlende Übersetzungen für: ${lang}`);
    assert.ok(LANGUAGE_NAMES[lang], `fehlender Sprachname für: ${lang}`);
  }
});

test("jede Sprache hat exakt dieselben Schlüssel wie Deutsch", () => {
  const deKeys = Object.keys(STRINGS.de).sort();
  assert.ok(deKeys.length > 20, "zu wenige Schlüssel, Übersetzung unvollständig?");
  for (const lang of LANGUAGES) {
    assert.deepEqual(Object.keys(STRINGS[lang]).sort(), deKeys, `Schlüssel-Mismatch bei ${lang}`);
  }
});

test("keine leeren Übersetzungen und konsistente Platzhalter pro Schlüssel", () => {
  const placeholders = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
  const deKeys = Object.keys(STRINGS.de);
  for (const lang of LANGUAGES) {
    for (const key of deKeys) {
      const value = STRINGS[lang][key];
      assert.ok(typeof value === "string" && value.trim().length > 0, `leer: ${lang}.${key}`);
      assert.deepEqual(
        placeholders(value),
        placeholders(STRINGS.de[key]),
        `Platzhalter-Mismatch bei ${lang}.${key}`,
      );
    }
  }
});

test("source.default (Auto-Load-Label) ist in allen Sprachen vorhanden", () => {
  for (const lang of LANGUAGES) {
    assert.ok(STRINGS[lang]["source.default"], `fehlt: ${lang}.source.default`);
  }
});

test("alle data-i18n-Schlüssel in index.html existieren in den Übersetzungen", () => {
  const html = readFileSync(join(ROOT, "index.html"), "utf8");
  const keys = [...html.matchAll(/data-i18n(?:-title)?="([^"]+)"/g)].map((m) => m[1]);
  assert.ok(keys.length >= 20, "zu wenige data-i18n-Attribute in index.html");
  for (const key of new Set(keys)) {
    assert.ok(STRINGS.de[key], `data-i18n-Schlüssel fehlt in de: ${key}`);
  }
});

test("t() interpoliert Platzhalter und fällt auf Deutsch/Schlüssel zurück", () => {
  const i18n = createI18n("en");
  assert.equal(i18n.t("menu.actions"), "Actions");
  assert.equal(i18n.t("status.loaded", { label: "Demo", width: 640, height: 480 }),
    "Demo: 640×480 loaded — processing …");
  // Unbekannter Schlüssel -> Schlüssel selbst
  assert.equal(i18n.t("gibt.es.nicht"), "gibt.es.nicht");
  // Ungültige Startsprache -> Fallback de
  assert.equal(createI18n("xx").lang, "de");
});

test("setLang/nextLang schalten zyklisch durch alle Sprachen", () => {
  const i18n = createI18n("de");
  const reihenfolge = [];
  for (let i = 0; i < LANGUAGES.length; i++) {
    reihenfolge.push(i18n.lang);
    i18n.setLang(i18n.nextLang());
  }
  assert.deepEqual(reihenfolge, LANGUAGES);
  assert.equal(i18n.lang, "de", "nach einem vollen Zyklus wieder bei de");
  i18n.setLang("xx"); // ungültig -> bleibt
  assert.equal(i18n.lang, "de");
});
