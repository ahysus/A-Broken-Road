# Project notes

Read this first when setting up or working on this project on another computer.

## What this is
A thesis prototype for a group at the University of the Cordilleras: a graph-based rerouting system for
Barangay Guisad (Guisad Central and Guisad Surong), Baguio City, during landslide road closures.
An officer marks a road closed; the system shows which locations are cut off and the new route.
It does not detect landslides. See `CODE_NOTES.md` for how it works and `DEMO_SCRIPT.md` for the demo.

## Status
- Working prototype with a basic page. The professor asked for backend focus and a basic UI only.
- Blue route: D* Lite. Orange before-route and marker colors: Dijkstra. Dijkstra also checks D* Lite.
- 29 automated tests pass: `python -m pytest tests -q`.
- Demo data is simulated: 10 demo locations, a placeholder evacuation center, 3 demo closures, assumed speeds.
- Not done yet: verified purok points, HazardHunterPH landslide levels, slope, timed comparison of
  Dijkstra only / D* Lite only / hybrid, nearest-road (instead of nearest-junction) connections.

## Working rules
- Plan changes first and agree on them as a group before building.
- Keep the UI basic.
- Label demo data as demo data. Never present it as findings.
- Run the tests after every change.

## Running
Mac: `bash setup_mac.sh` once, then `bash run_mac.sh`, then open http://127.0.0.1:8000.
After changing `templates/index.html` or any Python file, restart the server.
The demo needs no internet except for the background street map.
