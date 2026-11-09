"""Loads the saved roads and builds the vehicle and walking graphs from them."""

# json reads the saved files. math provides sine and cosine for map distances.
import json
import math

# NetworkX provides the graph structure and shortest path tools.
import networkx as nx

# Load our own settings.
import config

# The two travel modes. Each one gets its own graph.
MODES = ("vehicle", "walking")


def distance_m(lat1, lon1, lat2, lon2):
    """Straight-line distance in meters between two map points (haversine formula)."""
    # 6371000 is the Earth's average radius in meters.
    radius = 6371000.0
    # Trigonometry functions need radians, not degrees.
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    # How far apart the two points are, north-south and east-west.
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    # The haversine formula accounts for the Earth being round.
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


class RoadNetwork:
    """Holds both graphs and remembers which road segments are closed."""

    def __init__(self, network_data, points, destinations):
        # Junctions, saved under text ids, are converted back to whole numbers.
        self.nodes = {int(key): value for key, value in network_data["nodes"].items()}
        # Look up any road segment by its id number.
        self.segments = {segment["id"]: segment for segment in network_data["segments"]}
        # Barangay outlines, used only for drawing on the map.
        self.boundaries = network_data["boundaries"]
        # The set of segment ids that are closed right now. It starts empty.
        self.closed = set()
        # Speed in meters per second, for each mode. Dividing km/h by 3.6 converts it.
        self.speed_mps = {
            "vehicle": config.VEHICLE_SPEED_KPH / 3.6,
            "walking": config.WALKING_SPEED_KPH / 3.6,
        }
        # The full graph for each mode. It never changes after this line.
        self.graphs = {mode: self._build_graph(mode) for mode in MODES}
        # A reversed copy for each mode. Closures remove edges from this copy.
        # It is reversed because we search backward, from destinations to people.
        self.reversed_open = {mode: self.graphs[mode].reverse(copy=True) for mode in MODES}
        # A second reversed copy that closures never touch, used for "before closures"
        # results. A view is enough here, since this version is only ever read.
        self.reversed_intact = {mode: self.graphs[mode].reverse(copy=False) for mode in MODES}
        # For each mode: which directed edges (from, to) belong to each segment.
        self.segment_edges = {mode: self._edges_by_segment(mode) for mode in MODES}
        # Attach each starting point to its nearest junction in each graph.
        self.points = {point["id"]: self._snap_place(point) for point in points}
        # Do the same for each destination.
        self.destinations = {place["id"]: self._snap_place(place) for place in destinations}

    def _build_graph(self, mode):
        """Builds the graph for one travel mode from the shared segment list."""
        # MultiDiGraph allows one-way edges, and two different roads between one pair
        # of junctions. Each edge's key is its segment id.
        graph = nx.MultiDiGraph()
        speed = self.speed_mps[mode]
        for segment in self.segments.values():
            # Vehicles cannot use footpaths or stairs, so skip those for vehicles.
            if mode == "vehicle" and not segment["drivable"]:
                continue
            # Travel time in seconds = distance / speed.
            weight = {"length_m": segment["length_m"], "time_s": segment["length_m"] / speed}
            # Every segment can be traveled from its start to its end.
            graph.add_edge(segment["u"], segment["v"], key=segment["id"], **weight)
            # Walkers can go both ways on any road, even a one-way road.
            # Vehicles can go the other way only on a two-way road.
            if mode == "walking" or not segment["oneway"]:
                graph.add_edge(segment["v"], segment["u"], key=segment["id"], **weight)
        # Road data has small disconnected pieces. Keep only the largest piece where
        # every junction can reach every other, so a point is never reported as
        # cut off just because of a mapping gap.
        largest = max(nx.strongly_connected_components(graph), key=len)
        return graph.subgraph(largest).copy()

    def _edges_by_segment(self, mode):
        """Lists the directed edges that make up each segment, for one mode."""
        found = {}
        # Each edge in the graph is (from junction, to junction, segment id).
        for u, v, segment_id in self.graphs[mode].edges(keys=True):
            # setdefault creates the list the first time we see this segment.
            found.setdefault(segment_id, []).append((u, v))
        return found

    def nearest_node(self, lat, lon, mode):
        """Finds the junction in a mode's graph that is closest to a map point."""
        # min() checks every junction and keeps the one with the smallest distance.
        return min(
            self.graphs[mode].nodes,
            key=lambda node: distance_m(lat, lon, self.nodes[node]["lat"], self.nodes[node]["lon"]),
        )

    def _snap_place(self, place):
        """Returns a copy of a place, with its nearest junction for each mode added."""
        snapped = dict(place)
        # Example result: {"vehicle": 123, "walking": 456}. The two can differ because
        # the nearest footpath junction might not be on a drivable road.
        snapped["node"] = {mode: self.nearest_node(place["lat"], place["lon"], mode) for mode in MODES}
        return snapped

    def is_valid_target(self, target):
        """Checks whether a destination choice from the page is a real option."""
        # A specific place looks like "place:slu". Its id has to exist.
        if target.startswith("place:"):
            return target[len("place:"):] in self.destinations
        # Otherwise it has to be "any" or the type of at least one destination.
        return target == "any" or any(place["type"] == target for place in self.destinations.values())

    def goals(self, mode, target="any"):
        """Returns the junctions of the chosen destination or destination type."""
        # One specific destination, chosen by the user. Example: "place:slu".
        if target.startswith("place:"):
            return {self.destinations[target[len("place:"):]]["node"][mode]}
        return {
            place["node"][mode]
            for place in self.destinations.values()
            # "any" accepts all destinations. Otherwise the type has to match.
            if target == "any" or place["type"] == target
        }

    def set_closed(self, segment_id, is_closed):
        """Closes or reopens one segment in BOTH graphs, since it is the same road."""
        # Do nothing if the segment is already in the requested state.
        if is_closed == (segment_id in self.closed):
            return
        # Update the record of what is closed.
        if is_closed:
            self.closed.add(segment_id)
        else:
            self.closed.remove(segment_id)
        # Update each mode's searchable graph.
        for mode in MODES:
            # A segment may be missing from a mode: vehicles do not have footpaths.
            for u, v in self.segment_edges[mode].get(segment_id, []):
                reversed_graph = self.reversed_open[mode]
                if is_closed:
                    # Reversed graph, so the edge u->v is stored as v->u.
                    reversed_graph.remove_edge(v, u, key=segment_id)
                else:
                    # Put the edge back, with its original length and time.
                    data = self.graphs[mode][u][v][segment_id]
                    reversed_graph.add_edge(v, u, key=segment_id, **data)

    def reset(self):
        """Reopens every closed segment."""
        # list() makes a copy, because set_closed changes self.closed during the loop.
        for segment_id in list(self.closed):
            self.set_closed(segment_id, False)


def read_json(path):
    """Reads one saved JSON file."""
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def load_network():
    """Reads the saved files and returns a ready-to-use RoadNetwork."""
    return RoadNetwork(
        read_json(config.NETWORK_FILE),
        read_json(config.POINTS_FILE),
        read_json(config.DESTINATIONS_FILE),
    )
