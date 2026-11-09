"""The web server. It connects the backend to the page.  Start it with:  python src/app.py"""

# Flask receives requests from the browser and sends back answers.
from flask import Flask, jsonify, render_template, request

import config
from analysis import describe_path, destination_names, isolation_report, rank_critical_roads, route_from_node
from dstar_lite import DStarLite
from network import MODES, distance_m, load_network, read_json

# Tell Flask where the page and its supporting files are.
app = Flask(__name__, template_folder=str(config.ROOT / "templates"), static_folder=str(config.ROOT / "static"))

# Load the roads once when the server starts. Closures are kept here in memory,
# so restarting the server clears them.
network = load_network()

# Read the prepared demo closures.
scenarios = read_json(config.DATA_DIR / "scenarios.json")

# Finished D* Lite planners are kept here, so each one can reuse its earlier work.
planners = {}

# The most planners to keep. Every new clicked start creates one, so this limits memory.
MAX_PLANNERS = 300


def dstar_route(mode, target, start):
    """Gets the D* Lite route, creating the planner the first time it is needed."""
    key = (mode, target, start)
    # A new planner has to do a full first search. A saved one only repairs changes.
    first_search = key not in planners
    if first_search:
        if len(planners) >= MAX_PLANNERS:
            planners.clear()
        planners[key] = DStarLite(network, mode, start, network.goals(mode, target))
    result = planners[key].plan(network.closed)
    result["first_search"] = first_search
    # Add the road segments and the distance, so the page can draw the route.
    if result["found"]:
        details = describe_path(network, mode, result["nodes"])
        result.update(segments=details["segments"], length_m=details["length_m"],
                      destination=destination_names(network, mode, result["nodes"][-1]))
    return result


def without_nodes(route):
    """Removes the junction list, because the page draws routes from segment ids."""
    return {key: value for key, value in route.items() if key != "nodes"}


def read_choices():
    """Reads the travel mode and destination. Returns None if either is not a real option."""
    # Use the defaults if the request leaves them out.
    mode = request.args.get("mode", "vehicle")
    target = request.args.get("target", "any")
    if mode not in MODES or not network.is_valid_target(target):
        return None
    return mode, target


def read_start():
    """Reads the clicked map position from the request.

    Returns (lat, lon), or None if no start has been chosen yet. Raises ValueError
    if the values are not valid map coordinates.
    """
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    if lat is None or lon is None:
        return None
    lat, lon = float(lat), float(lon)
    # Reject positions that are not on Earth. The comparison also rejects NaN.
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Coordinates are out of range")
    return lat, lon


@app.route("/")
def home():
    """Sends the page itself."""
    return render_template("index.html")


@app.route("/api/network")
def get_network():
    """Sends everything that does not change: roads, points, destinations and settings."""
    return jsonify({
        "segments": [
            {key: segment[key] for key in ("id", "line", "drivable", "name", "highway", "length_m")}
            for segment in network.segments.values()
        ],
        "boundaries": network.boundaries,
        "points": [{key: point[key] for key in ("id", "name", "lat", "lon")} for point in network.points.values()],
        "destinations": [
            {key: place[key] for key in ("id", "name", "type", "lat", "lon", "source")}
            for place in network.destinations.values()
        ],
        "speeds": {"vehicle": config.VEHICLE_SPEED_KPH, "walking": config.WALKING_SPEED_KPH},
    })


@app.route("/api/state")
def get_state():
    """Sends the current results for the chosen mode, destination and starting position."""
    # Reject anything that is not a real option, rather than crash on it.
    choices = read_choices()
    if choices is None:
        return jsonify({"error": "Unknown mode or destination"}), 400
    mode, target = choices
    try:
        start_position = read_start()
    except ValueError:
        return jsonify({"error": "Invalid map position"}), 400

    # Which demo points are cut off now. The page uses this to color the markers.
    cut_off = [point_id for point_id, seconds in isolation_report(network, mode, target).items() if seconds is None]
    state = {"closed": sorted(network.closed), "cut_off": cut_off, "start": None}

    if start_position is not None:
        lat, lon = start_position
        # Connect the clicked position to the nearest junction in this mode's graph.
        start = network.nearest_node(lat, lon, mode)
        place = network.nodes[start]
        route = route_from_node(network, mode, start, target)
        state.update({
            "start": {
                "lat": place["lat"],
                "lon": place["lon"],
                "snap_m": distance_m(lat, lon, place["lat"], place["lon"]),
            },
            "before_route": without_nodes(route_from_node(network, mode, start, target, intact=True)),
            "dijkstra": without_nodes(route),
            "dstar": without_nodes(dstar_route(mode, target, start)),
        })
        # With no route in this mode, check the other mode so the page can suggest it.
        if not route["found"]:
            other_mode = "walking" if mode == "vehicle" else "vehicle"
            other_start = network.nearest_node(lat, lon, other_mode)
            other_route = route_from_node(network, other_mode, other_start, target)
            state["other_mode"] = {"mode": other_mode, "found": other_route["found"], "time_s": other_route.get("time_s")}
    return jsonify(state)


@app.route("/api/toggle", methods=["POST"])
def toggle():
    """Closes an open road, or reopens a closed one. This is the officer's report."""
    segment_id = request.get_json()["segment"]
    if segment_id not in network.segments:
        return jsonify({"error": "Unknown road segment"}), 400
    network.set_closed(segment_id, segment_id not in network.closed)
    return jsonify({"closed": sorted(network.closed)})


@app.route("/api/reset", methods=["POST"])
def reset():
    """Reopens every road."""
    network.reset()
    return jsonify({"closed": []})


@app.route("/api/scenario", methods=["POST"])
def load_scenario():
    """Clears all closures, applies one prepared demo closure, and gives its starting position."""
    scenario = scenarios[request.get_json()["index"]]
    network.reset()
    for segment_id in scenario["segments"]:
        network.set_closed(segment_id, True)
    point = network.points[scenario["point"]]
    return jsonify({"closed": sorted(network.closed), "lat": point["lat"], "lon": point["lon"]})


@app.route("/api/critical")
def critical():
    """Ranks the roads whose closure would do the most harm."""
    choices = read_choices()
    if choices is None:
        return jsonify({"error": "Unknown mode or destination"}), 400
    return jsonify(rank_critical_roads(network, *choices))


# Run the server only when this file is started directly.
if __name__ == "__main__":
    print("Open this address in a browser:  http://127.0.0.1:8000")
    # Port 8000, because Macs often use port 5000 for AirPlay. threaded=False handles
    # one request at a time, which keeps the closure state simple for a one-person demo.
    app.run(host="127.0.0.1", port=8000, debug=False, threaded=False)
