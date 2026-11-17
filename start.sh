#!/usr/bin/env bash
# start.sh — bequemer Wrapper: startet die Skintone-Web-App und öffnet den Browser.
# Liegt im Repo-Root, start.py findet das webapp/-Verzeichnis automatisch.
# Aufruf (aus dem Repo-Root): ./start.sh [--port 8080] [--no-browser]
set -euo pipefail
cd "$(dirname "$0")"
exec python3 start.py "$@"
