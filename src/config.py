"""Settings for the Guisad rerouting prototype."""

# pathlib builds file paths that work on both Windows and Mac.
from pathlib import Path

# Path(__file__) is this file. .parent is src/. The second .parent is the system/ folder.
ROOT = Path(__file__).resolve().parent.parent

# Every data file used by the system lives in system/data/.
DATA_DIR = ROOT / "data"

# The saved road network. build_data.py creates it, and the demo only reads it.
NETWORK_FILE = DATA_DIR / "guisad_network.json"

# Editable list of starting points. Replace these with verified purok points later.
POINTS_FILE = DATA_DIR / "demo_points.json"

# Editable list of hospitals, fire stations, barangay halls and evacuation centers.
DESTINATIONS_FILE = DATA_DIR / "destinations.json"

# The rectangle of roads to download, as (west, south, east, north) in degrees.
# It is wider than Guisad itself so that routes can reach hospitals and fire
# stations outside the two barangays, and so detours can leave the barangay.
# The south edge reaches 16.3960 so it includes Baguio General Hospital (BGH).
BBOX = (120.5700, 16.3960, 120.6050, 16.4350)

# ASSUMED travel speeds, in kilometers per hour. These are placeholders, not
# measured values. Thesis 2 should replace them, including slope for walking.
VEHICLE_SPEED_KPH = 20.0
WALKING_SPEED_KPH = 4.0

# Road types a rescue vehicle cannot use. Everything else counts as drivable.
# A walker may use every road type in the downloaded network.
NOT_DRIVABLE_HIGHWAY_TYPES = {
    "footway",     # sidewalks and foot-only paths
    "path",        # narrow unpaved paths
    "steps",       # stairs
    "pedestrian",  # pedestrian-only streets
    "corridor",    # indoor walkways
    "cycleway",    # bicycle paths
    "bridleway",   # horse paths
    "elevator",    # lifts
    "escalator",   # moving stairs
    "track",       # rough tracks a rescue vehicle may not manage
}
