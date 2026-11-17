#!/usr/bin/env bash
# start.sh — bequemer Wrapper: startet die Skintone-Web-App und öffnet den Browser.
# Aufruf: ./start.sh [--port 8080] [--no-browser]
set -euo pipefail
cd "$(dirname "$0")"
exec python3 start.py "$@"
