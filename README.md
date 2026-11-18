# Skintone-Lab (Web-App)

Experiment zu Hautfarbtönen direkt im Browser: Ein Portrait wird geladen
(Upload oder Webcam), der User wählt einen **Hue-Wert + Toleranz**, und alle
Bildbereiche **außerhalb** von `hue ± toleranz` werden **stark geblurt und in
ihrem Value (Helligkeit) abgesenkt**. Das Ergebnis wird live angezeigt.

Reines JavaScript (ES-Module) — **kein Build-Schritt, keine Runtime-Dependencies**.

## Lage im Repository

Dieses Verzeichnis ist das Git-Repo-Root. Die Web-App liegt im Unterordner
`webapp/`, die Start-Skripte liegen direkt im Root:

```
.                            # Repo-Root
├── .gitignore               # ignoriert __pycache__/, *.pyc, webapplogs/
├── README.md                # diese Datei
├── start.py                 # Start-Skript: Flask starten + Browser öffnen (+ Logging)
├── start.sh                 # Wrapper: ./start.sh
├── server_gui.py            # tkinter-Mini-App: Server per Button starten/restarten/stoppen
├── test_server_gui.py       # Tests für server_gui.py (headless, echter Flask-Subprozess)
├── webapplogs/              # Logfolder (wird zur Laufzeit angelegt, gitignored)
│   ├── server.log           # Flask: Requests, Status, Dauer, Fehler mit Stacktrace
│   ├── browser.log          # Frontend-Logs via POST /api/log (inkl. window.onerror)
│   ├── launcher.log         # start.py: Start/Stop, Health-Poll
│   └── gui.log              # server_gui.py: Klicks, Start/Stop/Restart
├── images/
│   └── default-image.jpg    # fertiges Testbild zum Hochladen in der App
└── webapp/
    ├── index.html           # UI: Upload, Webcam, Slider, Buttons, 2 Canvases, Sprach-/Theme-Buttons
    ├── styles.css           # Stylesheet mit Daylight- (Default) und Dark-Theme
    ├── package.json         # Metadaten + npm-Skripte (test, start)
    ├── src/
    │   ├── hsv.js           # RGB<->HSV, zirkulare Hue-Distanz (Wrap bei 0/360)
    │   ├── blur.js          # separabler Gaussian-Blur (RGBA + Float-Maske)
    │   ├── pipeline.js      # komplette Verarbeitungsroutine (Maske -> Feather -> Blur+Darken -> Compositing)
    │   ├── demo.js          # synthetisches Demo-Portrait (Sofort-Test ohne Bild)
    │   ├── i18n.js          # Übersetzungen de/en/fr/es/it/zh/ja + Sprachumschaltung
    │   ├── logger.js        # Frontend-Logging: Konsole + POST /api/log, globale Fehler-Handler
    │   └── app.js           # UI-Verdrahtung (DOM, Canvas, Webcam via getUserMedia) + Logging
    ├── test/                # Node-Testrunner (node --test), ohne npm-Deps
    │   ├── hsv.test.js      # Unit-Tests HSV/Hue-Distanz
    │   ├── blur.test.js     # Unit-Tests Kernel + Blur
    │   ├── pipeline.test.js # Unit + Pixel-Integration (Zwei-Hue-Bild)
    │   ├── e2e.test.js      # Ende-zu-Ende: Demo-Portrait komplett durch die Pipeline
    │   ├── i18n.test.js     # Übersetzungen: Vollständigkeit, Platzhalter, Sprachzyklus
    │   ├── logger.test.js   # Logging: Transport, Level, globale Fehler-Handler
    │   └── project.test.js # Integrity: index.html-Referenzen, IDs, Projektstruktur, el-Regression
    └── flask_app/
        ├── app.py           # Flask-Server: statisch + /api/health + /api/log + Request-Logging
        ├── requirements.txt # flask>=3.0
        └── test_app.py      # Flask-Tests (test_client): /, /api/health, /api/log, MIME-Typen, Logging
```

## Schnellstart — Projekt im Browser ausprobieren (mit Flask)

```bash
# aus dem Repo-Root:
pip install -r webapp/flask_app/requirements.txt   # einmalig: Flask installieren
python3 server_gui.py                              # tkinter-GUI: Button "Server starten / neu starten"
python3 start.py                                   # startet Flask UND öffnet den Browser
# oder: ./start.sh                                # dasselbe als Shell-Wrapper
# oder manuell: cd webapp && flask --app flask_app.app:app run --port 5824
```

**Im VS Code (Workspace-Root ist der Ordner über diesem Repo):** Palette öffnen
(`Strg+Shift+P`) → **„Tasks: Run Task“** → **„webapp: Server-GUI starten“**
— führt `server_gui.py` in einer eigenen Konsole aus (Task definiert in
`.vscode/tasks.json`, Pfad-Variable `skintones.webappDir` in `.vscode/settings.json`).

**Server-GUI (`server_gui.py`):** Mini-Fenster mit einem Button zum **Starten /
Neu starten (Restart)**, „Stoppen“ und „Browser öffnen“, Port-Wahl und einem
Live-Log-Tail aus `webapplogs/`. Erkennt automatisch das `../.venv`-Python,
falls Flask dort installiert ist.

**Logging (`webapplogs/`):** Alle Komponenten loggen ausführlich in den
Logfolder `webapplogs/` im Repo-Root (täglich rotiert, 14 Backups, gitignored;
für Tests umschaltbar über `SKINTONE_LOG_DIR`):

| Datei | Inhalt |
|---|---|
| `app.log` | **alle Logs fortlaufend in einer Datei** — Server, Browser, Launcher und GUI schreiben alle hier hinein; das GUI-Fenster zeigt genau diesen Tail live an |
| `server.log` | jeder Request (Methode, Pfad, Status, Dauer, User-Agent), 404/500 mit Stacktrace |
| `browser.log` | Frontend-Logs via `POST /api/log`: Boot, Button-Klicks, Parameter-Änderungen, Bild-Skalierung (`image.loaded` mit Roh-/Zielgröße + Faktor), Pipeline-Start/-Ergebnis, `window.onerror`/`unhandledrejection` **mit Stacktrace, Datei und Zeile** |
| `launcher.log` | `start.py`: Start/Stop, Health-Poll-Versuche, Fehler |
| `gui.log` | `server_gui.py`: Klicks, Start/Stop/Restart, Health-Poll, Fenster-Events |

So landet z. B. ein `"undefined is not an object (evaluating 'el.hue.value')"`
automatisch mit Stacktrace und den rohen Input-Werten in `browser.log` —
manuelles Zurückmelden ist nicht nötig:
`grep -n "ERROR" webapplogs/browser.log`

Danach im Browser `http://127.0.0.1:5824/` öffnen — das Default-Image
`images/default-image.jpg` (Repo-Root, wird von Flask unter `/images/…`
ausgeliefert) wird **beim Start automatisch geladen** und sofort verarbeitet.
Danach kann man z. B. **„Demo-Portrait“** klicken oder ein eigenes Bild über
„Bild laden …“ hochladen / Webcam starten.

Jeder andere statische Server geht auch, z. B. `cd webapp && python3 -m http.server 8000`.

**Webcam-Hinweis:** `getUserMedia` benötigt einen „secure context“. `http://127.0.0.1`
und `http://localhost` gelten als sicher — daher funktioniert die Webcam über
Flask auf localhost ohne HTTPS. Aufruf von einer fremden IP/Hostnamen ohne HTTPS
schlägt fehl (Meldung in der Statuszeile).

## Bedienung

| Element | Funktion |
|---|---|
| Bild laden … | Datei-Dialog, beliebiges Bild (Portrait-Annahme, keine Gesichtserkennung) |
| Webcam starten / Foto aufnehmen / Webcam stoppen | `getUserMedia`, Frame als Bild übernehmen |
| Demo-Portrait | synthetisches Testbild (Gesicht H≈25° vor blauem Hintergrund H≈210°) |
| Hue (0–359°) + Toleranz ± | Zielfarbwert und erlaubte Abweichung in Grad |
| Blur-Stärke (σ), Value-Absenkung, Kanten-Weichzeichnung | Effekt auf Nicht-Treffer |
| Verarbeiten | Pipeline explizit auslösen (läuft sonst live bei jeder Änderung) |
| Zurücksetzen | Restart: Ergebnis verwerfen, Original bleibt |
| Ergebnis speichern | PNG-Download |

Bilder werden beim Laden **auf die Fenstergröße skaliert** (hoch oder herunter,
Seitenverhältnis bleibt erhalten; absolute Obergrenze 1280 px, siehe
`src/fit.js`). Beim Fenster-Resize wird automatisch neu skaliert.
**Rendering:** Das Ergebnisbild füllt die Bühne so groß wie möglich; das
Original wird als kleines **Bild im Bild (PiP)** unten rechts über das
Ergebnis gelegt (Stage + `.pip`-Overlay in `index.html`/`styles.css`).

### Themes und Sprachen

- **Daylight-Theme:** Die App startet hell (`data-theme="light"` auf `<html>`,
  Variablen in `:root` in `styles.css`). Über die runde Sonne/Mond-Schaltfläche
  oben rechts wechselt man ins dunkle Theme (`html[data-theme="dark"]`);
  die Wahl liegt in `localStorage` (`skintone-theme`) und wird vor dem ersten
  Paint per Inline-Skript im `<head>` gesetzt (kein Flackern).
- **Mehrsprachigkeit:** Alle Menüeinträge, Labels, Buttons, Tooltips und
  Statusmeldungen liegen in `src/i18n.js` für **de, en, fr, es, it, zh, ja**.
  Die Schaltfläche mit dem runden Globus-Icon oben rechts klappt ein
  **Dropdown-Menü** auf (Sprache wählen per Klick, schließt bei Klick
  außerhalb/Escape; Wahl in `localStorage` unter `skintone-lang`).
  Texte im DOM tragen `data-i18n`-/`data-i18n-title`-Attribute.

## Die Bildverarbeitungsroutine (Pipeline)

1. Jedes Pixel wird RGB → HSV umgewandelt (Hue in Grad `[0,360)`, S/V in `[0,1]`;
   Graustufen S=0 bekommen die Konvention H=0).
2. **Zirkulare Hue-Distanz** `min(|a−b|, 360−|a−b|)` gegen den Ziel-Hue —
   am Wrap bei 0/360 korrekt.
3. **Maske:** Treffer = 1, wenn `distanz ≤ toleranz`, sonst 0.
4. **Feather:** Maske wird mit kleinem Gaussian weichgezeichnet (weiche Kanten).
5. **Hintergrund:** komplettes Bild wird separabel gaussian-geblurt (Sigma),
   dann wird im HSV-Raum der **Value mit `(1 − darken)` skaliert** — der
   Hintergrund wird gedimmt, nicht verfärbt (Hue bleibt erhalten).
6. **Compositing:** `out = maske · original + (1 − maske) · hintergrund`
   pro Kanal; Alpha bleibt immer original.

## Tests

Alle Tests laufen **ohne** `npm install` (Node-Testrunner ist eingebaut,
Node ≥ 20 genügt; Flask-Test nutzt `unittest`). Aufruf aus `webapp/`:

```bash
cd webapp
node --test                            # JS-Tests (Unit + Integration + E2E + i18n + Logging + Integrity)
python3 -m unittest flask_app.test_app # Flask-Server-Tests inkl. /api/log und Logging (aus webapp/)
python3 -m unittest test_server_gui    # GUI-Controller-Tests: echter Flask-Subprozess (aus Repo-Root)
# Flask-Tests alternativ als Repo-Paket vom Elternordner des Repos:
cd .. && python3 -m unittest skintones.webapp.flask_app.test_app
```

Testarten:
- **Unit:** HSV-Konvertierung (bekannte Werte, Roundtrip ±1), Hue-Distanz
  (Wrap, Symmetrie, inkl. Toleranzgrenze), Gaussian-Kernel (Summe=1,
  symmetrisch), Blur (konstantes Bild bleibt konstant, Impuls verteilt sich,
  Energieerhalt), Parameter-Validierung (Toleranz > 180° wird abgelehnt),
  i18n (alle 7 Sprachen vollständig, Platzhalter konsistent, Zyklus),
  logger (Transport, Level-Normalisierung, globale Fehler-Handler).
- **Integration (Pixel-Ebene):** synthetisches Zwei-Hue-Bild — Treffer-Hälfte
  bleibt exakt gleich, Nicht-Treffer-Hälfte wird abgedunkelt mit erhaltenem Hue.
- **E2E (ohne Browser):** komplettes Demo-Portrait durch die Pipeline;
  Gesichts-Pixel unverändert, Hintergrund-Ecke abgedunkelt, Laufzeit gemessen.
- **Integrity:** alle in `index.html` referenzierten Dateien existieren;
  `app.js` verdrahtet genau die IDs aus dem HTML; Regressionstest, dass alle
  Parameter-Inputs am `el`-Objekt hängen (Bug: „el.hue.value" auf undefined);
  Projektstruktur in `webapp/` und Repo-Root ist vollständig.
- **Flask:** `GET /` liefert HTML, `/api/health` JSON, JS-Dateien mit
  korrektem JavaScript-MIME-Typ (wichtig für ES-Module), 404 für Unsinn,
  `POST /api/log` schreibt Browser-Logs nach `browser.log` (204/400),
  Requests landen in `server.log`.
- **GUI-Controller:** `ServerController` startet/stoppt/restartet einen echten
  Flask-Subprozess (Health-Poll, Port zu nach Stop, Logs in `gui.log`).

## Annahmen / Hinweise

- „Value heruntergesetzt“ wird im HSV-Raum skaliert (nicht per RGB-Multiplikation),
  damit der Hintergrund gedimmt statt verfärbt wirkt.
- Toleranz > 180° ist fachlich unsinnig (deckt den ganzen Farbkreis ab) und wird
  mit Fehlermeldung abgelehnt.
- Portrait-Annahme: keine Gesichtserkennung, wie in der Anforderung vorgesehen.
- Sprache: Kommentare/Doku/UI auf Deutsch, Identifiers auf Englisch.
- Git: Remote `skintones` (github.com/DeepleMass/skintones) ist konfiguriert;
  `__pycache__/`, `*.pyc` und `webapplogs/` werden per `.gitignore` ausgeschlossen.
