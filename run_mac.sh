#!/bin/bash
# Starts the demo on the MacBook:  bash run_mac.sh
# Then open http://127.0.0.1:8000 in a browser. Press Control+C here to stop the server.
cd "$(dirname "$0")"
.venv/bin/python src/app.py
