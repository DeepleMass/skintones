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
    "src/i18n.js",
    "src/logger.js",
    "src/fit.js",
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

test("Regression el.hue.value: alle Parameter-Inputs hängen am el-Objekt", () => {
  // Fehlerbild war: "undefined is not an object (evaluating 'el.hue.value')",
  // weil readParams()/syncControlsFrom() über el.hue auf undefined griffen.
  const app = readFileSync(join(ROOT, "src/app.js"), "utf8");
  for (const id of ["hue", "hueNum", "tolerance", "toleranceNum", "blur", "blurNum", "darken", "darkenNum", "feather", "featherNum"]) {
    assert.ok(
      app.includes(`${id}: document.getElementById("${id}")`),
      `el.${id} fehlt in app.js — readParams() würde auf undefined zugreifen`,
    );
  }
});

test("app.js loggt ausführlich: Logger-Import, globale Fehler-Handler, Pipeline-Events", () => {
  const app = readFileSync(join(ROOT, "src/app.js"), "utf8");
  assert.match(app, /import \{[^}]*createLogger[^}]*\} from "\.\/logger\.js"/);
  assert.match(app, /installGlobalErrorHandlers\(logger\)/);
  assert.match(app, /createBrowserTransport\("\/api\/log"\)/);
  for (const event of ["app.boot", "pipeline.start", "pipeline.done", "pipeline.invalidParams", "ui.click", "param.change", "image.loaded", "window.resize"]) {
    assert.ok(app.includes(`"${event}"`), `fehlendes Log-Event in app.js: ${event}`);
  }
});

test("app.js skaliert Bilder auf die Fenstergröße (volle Bühne) + Re-Fit bei Resize", () => {
  const app = readFileSync(join(ROOT, "src/app.js"), "utf8");
  assert.match(app, /import \{[^}]*computeFitScale[^}]*\} from "\.\/fit\.js"/);
  assert.match(app, /computeFitScale\(/, "fitToWindow nutzt computeFitScale");
  assert.match(app, /addEventListener\("resize"/, "Re-Fit bei Fenster-Resize");
  assert.ok(!app.includes('classList.toggle("portrait"'), "altes Orientierungs-Layout muss entfernt sein");
  assert.ok(!app.includes('classList.toggle("landscape"'), "altes Orientierungs-Layout muss entfernt sein");
});

test("Default-Image wird beim Start automatisch geladen", () => {
  const app = readFileSync(join(ROOT, "src/app.js"), "utf8");
  const flask = readFileSync(join(ROOT, "flask_app/app.py"), "utf8");
  assert.ok(app.includes('"./images/default-image.jpg"'), "app.js lädt das Default-Image");
  assert.match(app, /loadDefaultImage\(\)/, "Auto-Load wird beim Boot aufgerufen");
  assert.ok(app.includes('"source.default"'), "i18n-Label source.default wird genutzt");
  assert.match(flask, /@app\.route\("\/images\/<path:filename>"\)/, "Flask serviert /images/…");
  // die Datei liegt im Repo-Root unter images/
  assert.ok(existsSync(join(REPO_ROOT, "images", "default-image.jpg")), "images/default-image.jpg fehlt im Repo-Root");
});

test("Rendering: Ergebnis als große Bühne, Original als Bild im Bild (PiP)", () => {
  const html = readFileSync(join(ROOT, "index.html"), "utf8");
  const css = readFileSync(join(ROOT, "styles.css"), "utf8");
  assert.ok(html.includes('class="stage"'), "Stage-Figure fehlt in index.html");
  assert.ok(html.includes('class="pip"'), "PiP-Figure fehlt in index.html");
  assert.ok(
    html.indexOf('id="canvasResult"') < html.indexOf('id="canvasOriginal"'),
    "Ergebnis-Canvas liegt in der Bühne, Original-Canvas im PiP",
  );
  assert.match(css, /\.pip\s*\{[^}]*position:\s*absolute/s, "PiP ist absolut über der Bühne positioniert");
  assert.match(css, /\.pip\s*\{[^}]*width:\s*min\(/s, "PiP-Breite ist begrenzt (kleines Bild im Bild)");
  assert.match(css, /\.stage\s*>\s*\.canvas-wrap\s*>\s*canvas\s*\{[^}]*max-width:\s*100%/s, "Bühnen-Canvas nutzt die volle Breite");
});

test("Sprachauswahl ist ein Dropdown (kein Klick-Zyklus mehr)", () => {
  const app = readFileSync(join(ROOT, "src/app.js"), "utf8");
  const html = readFileSync(join(ROOT, "index.html"), "utf8");
  assert.ok(html.includes('id="langMenu"'), "Dropdown-Container langMenu fehlt in index.html");
  assert.match(app, /buildLangMenu\(\)/, "Menü wird aufgebaut");
  assert.match(app, /selectLang\(code\)/, "selectLang wendet die Wahl an");
  assert.ok(!app.includes("i18n.nextLang()"), "Zyklus-Wechsel darf nicht mehr genutzt werden");
});
