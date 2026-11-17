# Skintone-Lab (Web-App)

Experiment zu Hautfarbtönen direkt im Browser: Ein Portrait wird geladen
(Upload oder Webcam), der User wählt einen **Hue-Wert + Toleranz**, und alle
Bildbereiche **außerhalb** von `hue ± toleranz` werden **stark geblurt und in
ihrem Value (Helligkeit) abgesenkt**. Das Ergebnis wird live angezeigt.

Reines JavaScript (ES-Module) — **kein Build-Schritt, keine Runtime-Dependencies**.

## Projektstruktur

```
webapp/
├── index.html               # UI: Upload, Webcam, Slider, Buttons, 2 Canvases
├── styles.css               # Stylesheet
├── package.json             # Metadaten + npm-Skripte (test, start)
├── src/
│   ├── hsv.js               # RGB<->HSV, zirkulare Hue-Distanz (Wrap bei 0/360)
│   ├── blur.js              # separabler Gaussian-Blur (RGBA + Float-Maske)
│   ├── pipeline.js          # komplette Verarbeitungsroutine (Maske -> Feather -> Blur+Darken -> Compositing)
│   ├── demo.js              # synthetisches Demo-Portrait (Sofort-Test ohne Bild)
│   └── app.js               # UI-Verdrahtung (DOM, Canvas, Webcam via getUserMedia)
├── test/                    # Node-Testrunner (node --test), ohne npm-Deps
│   ├── hsv.test.js          # Unit-Tests HSV/Hue-Distanz
│   ├── blur.test.js         # Unit-Tests Kernel + Blur
│   ├── pipeline.test.js     # Unit + Pixel-Integration (Zwei-Hue-Bild)
│   ├── e2e.test.js          # Ende-zu-Ende: Demo-Portrait komplett durch die Pipeline
│   └── project.test.js     # Integrity: index.html-Referenzen, IDs, Projektstruktur
├── flask_app/
│   ├── app.py               # Flask-Server: liefert die App statisch aus
│   ├── requirements.txt     # flask>=3.0
│   └── test_app.py          # Flask-Tests (test_client): /, /api/health, MIME-Typen
├── start.py                 # Start-Skript: Flask starten + Browser öffnen
└── start.sh                 # Wrapper: ./start.sh
```

## Schnellstart — Projekt im Browser ausprobieren (mit Flask)

```bash
cd webapp
pip install -r flask_app/requirements.txt   # einmalig: Flask installieren
python3 start.py                             # startet Flask UND öffnet den Browser
# oder: ./start.sh                          # dasselbe als Shell-Wrapper
# oder manuell: flask --app flask_app.app:app run --port 5824
```

Danach im Browser `http://127.0.0.1:5824/` öffnen und z. B. **„Demo-Portrait“**
klicken — oder eigenes Bild laden / Webcam starten.

Jeder andere statische Server geht auch, z. B. `python3 -m http.server 8000`.

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

Bilder werden vor der Verarbeitung auf max. 1280 px Kantenlänge skaliert
(Seitenverhältnis bleibt erhalten) — das hält die Pipeline im Browser flüssig.

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

Alle Tests laufen **ohne** `npm install` (Node-Testrunner ist eingebaut;
Flask-Test nutzt `unittest`):

```bash
cd webapp
node --test test/                          # 33 JS-Tests (Unit + Integration + E2E + Integrity)
python3 -m unittest flask_app/test_app.py  # Flask-Server-Tests
```

Testarten:
- **Unit:** HSV-Konvertierung (bekannte Werte, Roundtrip ±1), Hue-Distanz
  (Wrap, Symmetrie, inkl. Toleranzgrenze), Gaussian-Kernel (Summe=1,
  symmetrisch), Blur (konstantes Bild bleibt konstant, Impuls verteilt sich,
  Energieerhalt), Parameter-Validierung (Toleranz > 180° wird abgelehnt).
- **Integration (Pixel-Ebene):** synthetisches Zwei-Hue-Bild — Treffer-Hälfte
  bleibt exakt gleich, Nicht-Treffer-Hälfte wird abgedunkelt mit erhaltenem Hue.
- **E2E (ohne Browser):** komplettes Demo-Portrait durch die Pipeline;
  Gesichts-Pixel unverändert, Hintergrund-Ecke abgedunkelt, Laufzeit gemessen.
- **Integrity:** alle in `index.html` referenzierten Dateien existieren;
  `app.js` verdrahtet genau die IDs aus dem HTML.
- **Flask:** `GET /` liefert HTML, `/api/health` JSON, JS-Dateien mit
  korrektem JavaScript-MIME-Typ (wichtig für ES-Module), 404 für Unsinn.

## Annahmen / Hinweise

- „Value heruntergesetzt“ wird im HSV-Raum skaliert (nicht per RGB-Multiplikation),
  damit der Hintergrund gedimmt statt verfärbt wirkt.
- Toleranz > 180° ist fachlich unsinnig (deckt den ganzen Farbkreis ab) und wird
  mit Fehlermeldung abgelehnt.
- Portrait-Annahme: keine Gesichtserkennung, wie in der Anforderung vorgesehen.
- Sprache: Kommentare/Doku/UI auf Deutsch, Identifiers auf Englisch.
