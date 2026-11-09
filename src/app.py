"""The web server. It connects the backend to the page.  Start it with:  python src/app.py"""

import json

# Flask receives requests from the browser and sends back answers.
from flask import Flask, jsonify, render_template, request

import config
from analysis import describe_path, destination_names, dijkstra_route, isolation_report, rank_critical_roads
from dstar_lite import DStarLite
from network import MODES, load_network

# Tell Flask where the page and its supporting files are.
app = Flask(__name__, template_folder=str(config.ROOT / "templates"), static_folder=str(config.ROOT / "static"))

# Load the roads once when the server starts. Closures are kept here in memory,
# so restarting the server clears them.
network = load_network()

# Read the prepared demo closures.
with open(config.DATA_DIR / "scenarios.json", encoding="utf-8") as file:
    scenarios = json.load(file)

# The choices offered in the page's "Destination" menu.
TARGET_TYPES = ("any", "hospital", "fire station", "barangay hall", "evacuation center")

# Save the situation before any closure, so we can show "before" and "added" values.
baseline_times = {(mode, target): isolation_report(network, mode, target) for mode in MODES for target in TARGET_TYPES}
baseline_routes = {
    (mode, target, point_id): dijkstra_route(network, mode, point_id, target)
    for mode in MODES for target in TARGET_TYPES for point_id in network.points
}

# Finished D* Lite planners are kept here, so each one can reuse its earlier work.
planners = {}


def dstar_route(mode, target, point_id):
    """Gets the D* Lite route, creating the planner the first time it is needed."""
    key = (mode, target, point_id)
    # A new planner has to do a full first search. A saved one only repairs changes.
    first_search = key not in planners
    if first_search:
        start = network.points[point_id]["node"][mode]
        planners[key] = DStarLite(network, mode, start, network.goals(mode, target))
    result = planners[key].plan(network.closed)
    result["first_search"] = first_search
    # Add the road segments and the distance, so the page can draw the route.
    if result["found"]:
        details = describe_path(network, mode, result["nodes"])
        result.update(segments=details["segments"], length_m=details["length_m"],
                      destination=destination_names(network, mode, result["nodes"][-1]))
    return result


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
        "points": list(network.points.values()),
        "destinations": list(network.destinations.values()),
        "scenarios": [scenario["name"] for scenario in scenarios],
        "targets": TARGET_TYPES,
        "speeds": {"vehicle": config.VEHICLE_SPEED_KPH, "walking": config.WALKING_SPEED_KPH},
    })


@app.route("/api/state")
def get_state():
    """Sends the current results for the mode, destination type and point chosen."""
    # Read the page's choices from the web address, with defaults if they are missing.
    mode = request.args.get("mode", "vehicle")
    target = request.args.get("target", "any")
    point_id = request.args.get("point", next(iter(network.points)))
    # Reject anything that is not a real option, rather than crash on it.
    if mode not in MODES or target not in TARGET_TYPES or point_id not in network.points:
        return jsonify({"error": "Unknown mode, destination type or point"}), 400

    # One row per point, for both travel modes.
    current = {each: isolation_report(network, each, target) for each in MODES}
    table = [
        {
            "id": each_id,
            "name": network.points[each_id]["name"],
            "before": {each: baseline_times[(each, target)][each_id] for each in MODES},
            "now": {each: current[each][each_id] for each in MODES},
        }
        for each_id in network.points
    ]
    return jsonify({
        "closed": sorted(network.closed),
        "table": table,
        "before_route": without_nodes(baseline_routes[(mode, target, point_id)]),
        "dijkstra": without_nodes(dijkstra_route(network, mode, point_id, target)),
        "dstar": without_nodes(dstar_route(mode, target, point_id)),
    })


def without_nodes(route):
    """Removes the junction list, because the page draws routes from segment ids."""
    return {key: value for key, value in route.items() if key != "nodes"}


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
    """Clears all closures, then applies one prepared demo closure."""
    scenario = scenarios[request.get_json()["index"]]
    network.reset()
    for segment_id in scenario["segments"]:
        network.set_closed(segment_id, True)
    return jsonify({"closed": sorted(network.closed), "point": scenario["point"]})


@app.route("/api/critical")
def critical():
    """Ranks the roads whose closure would do the most harm."""
    mode = request.args.get("mode", "vehicle")
    target = request.args.get("target", "any")
    if mode not in MODES or target not in TARGET_TYPES:
        return jsonify({"error": "Unknown mode or destination type"}), 400
    return jsonify(rank_critical_roads(network, mode, target))


# Run the server only when this file is started directly.
if __name__ == "__main__":
    print("Open this address in a browser:  http://127.0.0.1:8000")
    # Port 8000, because Macs often use port 5000 for AirPlay. threaded=False handles
    # one request at a time, which keeps the closure state simple for a one-person demo.
    app.run(host="127.0.0.1", port=8000, debug=False, threaded=False)
