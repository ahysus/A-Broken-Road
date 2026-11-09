#!/bin/bash
# Run ONCE on the MacBook:  bash setup_mac.sh
# Works without internet, using the library files in the wheels/ folder.

# Move into the folder holding this file.
cd "$(dirname "$0")"

# 1. Check that Python 3.9 or newer is installed.
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Install it from https://www.python.org/downloads/ and run this again."
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "Python 3.9 or newer is needed. This Mac has: $(python3 --version)"
  exit 1
fi
echo "Using $(python3 --version)"

# 2. Create a private Python environment for this project.
python3 -m venv .venv || { echo "Could not create the environment."; exit 1; }

# 3. Install the libraries. Try the bundled files first (no internet needed),
#    and use the internet only if that fails.
if .venv/bin/python -m pip install --no-index --find-links wheels -r requirements.txt; then
  echo "Libraries installed from the bundled files."
elif .venv/bin/python -m pip install -r requirements.txt; then
  echo "Libraries installed from the internet."
else
  echo "Installing the libraries failed. Connect to the internet and run this again."
  exit 1
fi

# 4. Run the automated tests, to confirm that everything works on this Mac.
if .venv/bin/python -m pytest tests -q; then
  echo ""
  echo "Setup finished. Start the demo with:  bash run_mac.sh"
else
  echo ""
  echo "Some tests failed. The demo may still run, but check the messages above."
fi
