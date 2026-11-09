"""Chooses demo starting points and demo closures from the real road network.

Run once on the build PC:  python src/make_demo_points.py
It writes data/demo_points.json and data/scenarios.json. The demo only reads them.
These points are NOT real purok locations. They get replaced once verified puroks exist.
"""

import json

import networkx as nx

import config
from analysis import dijkstra_route
from network import RoadNetwork, distance_m, read_json

# The largest number of roads a demo closure may close at once.
MAX_CUT_SIZE = 3


def find_cuts(network, barangay_of):
    """Finds small sets of roads whose closure separates Guisad junctions from all destinations."""
    # A simple two-way version of the vehicle graph, with one extra artificial junction
    # called "SINK" joined to every destination. A cut that separates a junction from
    # SINK separates it from every destination at once.
    plain = nx.Graph(network.graphs["vehicle"])
    for goal in network.goals("vehicle"):
        plain.add_edge(goal, "SINK")
    cuts = {}
    for node in barangay_of:
        # Destinations cannot be cut off from themselves.
        if plain.has_edge(node, "SINK"):
            continue
        # The minimum edge cut is the fewest roads whose removal separates the two.
        cut = nx.minimum_edge_cut(plain, node, "SINK")
        if len(cut) > MAX_CUT_SIZE or any("SINK" in edge for edge in cut):
            continue
        cuts.setdefault(frozenset(frozenset(edge) for edge in cut), []).append(node)
    return cuts, plain


def main():
    data = read_json(config.NETWORK_FILE)
    destinations = read_json(config.DESTINATIONS_FILE)
    # Build the network with no points yet, because this file is choosing them.
    network = RoadNetwork(data, [], destinations)
    vehicle = network.graphs["vehicle"]

    # Note which barangay each vehicle junction is in, keeping only those inside Guisad.
    barangay_of = {}
    for node in vehicle.nodes:
        name = network.barangay_at(network.nodes[node]["lat"], network.nodes[node]["lon"])
        if name:
            barangay_of[node] = name

    cuts, plain = find_cuts(network, barangay_of)
    goals_walk = network.goals("walking")
    results = []
    for cut, seeds in cuts.items():
        # Find what is cut off, by removing these roads from the simple graph.
        edges = [tuple(edge) for edge in cut]
        plain.remove_edges_from(edges)
        side = nx.node_connected_component(plain, seeds[0])
        plain.add_edges_from(edges)
        cut_guisad = sorted(node for node in side if node in barangay_of)
        # List the segments in the cut, in both directions.
        segments = sorted({
            key
            for u, v in edges
            for a, b in ((u, v), (v, u))
            if vehicle.has_edge(a, b)
            for key in vehicle[a][b]
        })
        # Close them to test whether someone on foot could still leave.
        for segment_id in segments:
            network.set_closed(segment_id, True)
        reached = nx.multi_source_dijkstra_path_length(
            network.reversed_open["walking"], goals_walk, weight="time_s"
        )
        network.reset()
        # Use a junction from the middle of the sorted list of cut-off junctions.
        node = cut_guisad[len(cut_guisad) // 2]
        place = network.nodes[node]
        walk_node = network.nearest_node(place["lat"], place["lon"], "walking")
        results.append({"segments": segments, "size": len(cut_guisad), "node": node,
                        "walk_ok": walk_node in reached, "roads": len(segments)})

    # Prefer closures with few roads that cut off many junctions, so they show clearly.
    results.sort(key=lambda item: (-item["size"], item["roads"]))
    print(f"Cuts found: {len(results)}")
    print(f"  walking still possible: {sum(1 for item in results if item['walk_ok'])}")
    for item in results[:12]:
        print("  ", item)

    chosen, scenarios = [], []
    vehicle_only = [item for item in results if item["walk_ok"]]
    both_cut = [item for item in results if not item["walk_ok"]]
    if vehicle_only:
        pick = vehicle_only[0]
        chosen.append(pick["node"])
        scenarios.append({"name": "A: vehicles cut off, walking route remains",
                          "segments": pick["segments"], "point": f"P{len(chosen)}"})
    if both_cut:
        pick = both_cut[0]
        chosen.append(pick["node"])
        scenarios.append({"name": "B: cut off for vehicles and on foot",
                          "segments": pick["segments"], "point": f"P{len(chosen)}"})

    # Fill up to 10 points, spread out. Each new point is the junction farthest from
    # those already chosen, so the points cover both barangays.
    # Leave out junctions within 100 m of a destination, because a point sitting on
    # a destination shows a meaningless travel time of zero.
    guisad_nodes = [
        node for node in sorted(barangay_of)
        if all(
            distance_m(network.nodes[node]["lat"], network.nodes[node]["lon"], place["lat"], place["lon"]) > 100
            for place in network.destinations.values()
        )
    ]
    if not chosen:
        chosen.append(guisad_nodes[0])

    def distance_to_nearest_chosen(node):
        a = network.nodes[node]
        return min(
            (a["lat"] - network.nodes[c]["lat"]) ** 2 + (a["lon"] - network.nodes[c]["lon"]) ** 2
            for c in chosen
        )

    while len(chosen) < 10:
        chosen.append(max(guisad_nodes, key=distance_to_nearest_chosen))

    points = [
        {
            "id": f"P{number}",
            "name": f"Demo Point {number}",
            "lat": network.nodes[node]["lat"],
            "lon": network.nodes[node]["lon"],
            "barangay": barangay_of.get(node, ""),
            "source": "Demo location, not a purok",
        }
        for number, node in enumerate(chosen, start=1)
    ]
    with open(config.POINTS_FILE, "w", encoding="utf-8") as file:
        json.dump(points, file, indent=2)

    # Scenario C: closing a road on a point's route, where a detour exists, adds time
    # rather than isolating anyone. Try every road on each route and keep the largest.
    network = RoadNetwork(data, points, destinations)
    best = None
    for point_id in network.points:
        route = dijkstra_route(network, "vehicle", point_id)
        for segment_id in route["segments"]:
            network.set_closed(segment_id, True)
            after = dijkstra_route(network, "vehicle", point_id)
            network.set_closed(segment_id, False)
            if after["found"]:
                added = after["time_s"] - route["time_s"]
                if best is None or added > best[0]:
                    best = (added, segment_id, point_id)
    if best:
        scenarios.append({"name": "C: road closed, detour adds travel time",
                          "segments": [best[1]], "point": best[2]})

    with open(config.DATA_DIR / "scenarios.json", "w", encoding="utf-8") as file:
        json.dump(scenarios, file, indent=2)

    for point in points:
        print(point["id"], point["barangay"], point["lat"], point["lon"])
    for scenario in scenarios:
        print(scenario)


# Run main() only when this file is started directly.
if __name__ == "__main__":
    main()
