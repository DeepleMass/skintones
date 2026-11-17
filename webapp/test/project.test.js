/**
 * project.test.js — Projekt-Integrity-Test: prüft, dass alle in index.html
 * referenzierten Dateien existieren und die Projektstruktur vollständig ist.
 * Läuft in Node (fs-Zugriff), nicht im Browser.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), ".."); // webapp/
const REPO_ROOT = join(ROOT, ".."); // Git-Repo-Root (liegt eine Ebene über webapp/)

test("index.html referenziert nur Dateien, die existieren", () => {
  const html = readFileSync(join(ROOT, "index.html"), "utf8");
  const refs = [...html.matchAll(/(?:src|href)="(\.\/[^"]+)"/g)].map((m) => m[1]);
  assert.ok(refs.length >= 2, "mindestens styles.css und app.js erwartet");
  for (const ref of refs) {
    assert.ok(existsSync(join(ROOT, ref)), `fehlt: ${ref}`);
  }
});

test("Projektstruktur ist vollständig (webapp/ und Repo-Root)", () => {
  // Dateien innerhalb von webapp/
  const webappFiles = [
    "package.json",
    "index.html",
    "styles.css",
    "src/hsv.js",
    "src/blur.js",
    "src/pipeline.js",
    "src/demo.js",
    "src/app.js",
    "flask_app/app.py",
    "flask_app/requirements.txt",
    "flask_app/test_app.py",
  ];
  for (const f of webappFiles) {
    assert.ok(existsSync(join(ROOT, f)), `fehlt in webapp/: ${f}`);
  }
  // Start-Skripte, Doku und .gitignore liegen im Repo-Root (eine Ebene höher)
  const repoFiles = ["README.md", "start.py", "start.sh", ".gitignore"];
  for (const f of repoFiles) {
    assert.ok(existsSync(join(REPO_ROOT, f)), `fehlt im Repo-Root: ${f}`);
  }
});

test("index.html lädt app.js als ES-Modul und hat die Kern-UI-Elemente", () => {
  const html = readFileSync(join(ROOT, "index.html"), "utf8");
  assert.match(html, /<script type="module" src="\.\/src\/app\.js"><\/script>/);
  for (const id of ["fileInput", "btnWebcamStart", "btnCapture", "btnDemo", "btnApply", "btnReset", "btnSave", "hue", "tolerance", "canvasOriginal", "canvasResult"]) {
    assert.ok(html.includes(`id="${id}"`), `fehlende Element-ID: ${id}`);
  }
});

test("app.js verdrahtet genau die IDs aus index.html (keine Tippfehler)", () => {
  const html = readFileSync(join(ROOT, "index.html"), "utf8");
  const app = readFileSync(join(ROOT, "src/app.js"), "utf8");
  const ids = [...html.matchAll(/id="([^"]+)"/g)].map((m) => m[1]);
  for (const id of ids) {
    if (id.endsWith("Num")) {
      // Zahlfelder werden dynamisch als base + "Num" adressiert
      const base = id.slice(0, -3);
      assert.ok(app.includes(`"${base}"`), `app.js kennt die Basis-ID nicht: ${base}`);
      assert.ok(app.includes('"Num"'), 'app.js baut die "Num"-IDs nicht dynamisch');
    } else {
      assert.ok(app.includes(`"${id}"`), `app.js kennt die ID nicht: ${id}`);
    }
  }
});
