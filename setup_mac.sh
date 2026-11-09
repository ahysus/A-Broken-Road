#!/bin/bash
# Run ONCE on the MacBook, with internet:  bash setup_mac.sh
# Stop at the first error, so a problem is not hidden.
set -e
# Move into the folder holding this file.
cd "$(dirname "$0")"
# Create a private Python environment for this project.
python3 -m venv .venv
# Install the libraries the demo needs. OSMnx is not needed here.
.venv/bin/python -m pip install -r requirements.txt
# Run the automated tests, to confirm that everything works on this computer.
.venv/bin/python -m pytest tests -q
echo "Setup finished. Start the demo with:  bash run_mac.sh"
