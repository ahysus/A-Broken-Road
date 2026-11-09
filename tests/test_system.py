"""Automated checks. Run from the system folder with:  python -m pytest tests -q"""

import json
import random
import sys
from pathlib import Path

# The system/ folder.
ROOT = Path(__file__).resolve().parent.parent

# Let the tests import the files in src/.
sys.path.insert(0, str(ROOT / "src"))

import pytest

from analysis import dijkstra_route, isolation_report, rank_critical_roads
from dstar_lite import DStarLite
from network import RoadNetwork, load_network


def small_network():
    """A tiny road map whose correct answers are easy to work out by hand.

        A --120m-- B --120m-- C(destination)
                   |          |
                  300m      120m
                   |          |
                   E --120m-- D

    F hangs off A by a footpath, and B-C is the road we close in tests.
    Lengths are at least the straight-line distance (about 111 m per 0.001 degree),
    as on real roads. A shorter road would be physically impossible.
    """
    locations = {1: (0.000, 0.000), 2: (0.000, 0.001), 3: (0.000, 0.002),
                 4: (0.001, 0.002), 5: (0.001, 0.001), 6: (-0.001, 0.000)}
    nodes = {str(key): {"lat": lat, "lon": lon} for key, (lat, lon) in locations.items()}

    def road(number, u, v, length, drivable=True, oneway=False):
        return {"id": number, "u": u, "v": v, "length_m": length, "highway": "residential", "name": "",
                "oneway": oneway, "drivable": drivable, "line": [list(locations[u]), list(locations[v])]}

    segments = [road(0, 1, 2, 120), road(1, 2, 3, 120), road(2, 2, 5, 300), road(3, 5, 4, 120),
                road(4, 4, 3, 120), road(5, 1, 6, 120, drivable=False)]
    data = {"nodes": nodes, "segments": segments, "boundaries": []}
    points = [{"id": "A", "name": "A", "lat": 0.0, "lon": 0.0}, {"id": "F", "name": "F", "lat": -0.001, "lon": 0.0}]
    destinations = [{"id": "C", "name": "C", "type": "hospital", "lat": 0.0, "lon": 0.002}]
    return RoadNetwork(data, points, destinations)


def test_route_before_closure_uses_the_short_road():
    network = small_network()
    route = dijkstra_route(network, "vehicle", "A")
    assert route["length_m"] == pytest.approx(240)
    assert route["segments"] == [0, 1]


def test_closure_forces_the_longer_detour():
    network = small_network()
    network.set_closed(1, True)
    route = dijkstra_route(network, "vehicle", "A")
    assert route["length_m"] == pytest.approx(120 + 300 + 120 + 120)


def test_reopening_restores_the_original_route():
    network = small_network()
    network.set_closed(1, True)
    network.set_closed(1, False)
    assert dijkstra_route(network, "vehicle", "A")["length_m"] == pytest.approx(240)


def test_point_is_isolated_when_every_way_out_closes():
    network = small_network()
    network.set_closed(0, True)
    assert isolation_report(network, "vehicle")["A"] is None
    assert dijkstra_route(network, "vehicle", "A")["found"] is False


def test_footpath_is_walkable_but_not_drivable():
    network = small_network()
    assert 6 in network.graphs["walking"].nodes
    assert 6 not in network.graphs["vehicle"].nodes


def test_closure_applies_to_both_modes():
    network = small_network()
    network.set_closed(0, True)
    assert isolation_report(network, "walking")["A"] is None
    assert isolation_report(network, "vehicle")["A"] is None


def test_one_way_road_cannot_be_driven_backward_but_can_be_walked():
    nodes = {"1": {"lat": 0.0, "lon": 0.0}, "2": {"lat": 0.0, "lon": 0.001}, "3": {"lat": 0.001, "lon": 0.0}}
    def road(number, u, v, oneway, length=120):
        return {"id": number, "u": u, "v": v, "length_m": length, "highway": "residential", "name": "",
                "oneway": oneway, "drivable": True, "line": [[0, 0], [0, 0]]}
    # Vehicles can go 1->2 by the one-way road, and back by the two longer roads.
    data = {"nodes": nodes, "boundaries": [],
            "segments": [road(0, 1, 2, True), road(1, 2, 3, False, 200), road(2, 3, 1, False)]}
    network = RoadNetwork(data, [{"id": "S", "name": "S", "lat": 0.0, "lon": 0.001}],
                          [{"id": "G", "name": "G", "type": "hospital", "lat": 0.0, "lon": 0.0}])
    assert dijkstra_route(network, "vehicle", "S")["length_m"] == pytest.approx(320)
    assert dijkstra_route(network, "walking", "S")["length_m"] == pytest.approx(120)


def test_dstar_lite_matches_on_small_network_through_changes():
    network = small_network()
    start = network.points["A"]["node"]["vehicle"]
    planner = DStarLite(network, "vehicle", start, network.goals("vehicle"))
    assert planner.plan(network.closed)["time_s"] == pytest.approx(dijkstra_route(network, "vehicle", "A")["time_s"])
    network.set_closed(1, True)
    assert planner.plan(network.closed)["time_s"] == pytest.approx(dijkstra_route(network, "vehicle", "A")["time_s"])
    network.set_closed(0, True)
    assert planner.plan(network.closed)["found"] is False
    network.reset()
    assert planner.plan(network.closed)["time_s"] == pytest.approx(dijkstra_route(network, "vehicle", "A")["time_s"])


@pytest.fixture(scope="module")
def guisad():
    return load_network()


@pytest.mark.parametrize("mode", ["vehicle", "walking"])
def test_dstar_lite_matches_dijkstra_on_real_roads_during_random_closures(guisad, mode):
    """The main correctness test: same cost as Dijkstra, after every change."""
    network = guisad
    network.reset()
    # A fixed seed makes the "random" closures the same on every run.
    generator = random.Random(2026)
    segment_ids = list(network.segment_edges[mode])
    planners = {
        point_id: DStarLite(network, mode, point["node"][mode], network.goals(mode))
        for point_id, point in network.points.items()
    }
    for _ in range(60):
        # Usually close another road, and sometimes reopen one, as an officer might.
        if network.closed and generator.random() < 0.3:
            network.set_closed(generator.choice(sorted(network.closed)), False)
        else:
            network.set_closed(generator.choice(segment_ids), True)
        for point_id, planner in planners.items():
            expected = dijkstra_route(network, mode, point_id)
            actual = planner.plan(network.closed)
            assert actual["found"] == expected["found"]
            if expected["found"]:
                assert actual["time_s"] == pytest.approx(expected["time_s"], abs=1e-6)
    network.reset()


@pytest.mark.parametrize("mode", ["vehicle", "walking"])
def test_dstar_lite_matches_dijkstra_when_each_route_keeps_being_blocked(guisad, mode):
    """A harder test than random closures: always close a road ON the current route."""
    network = guisad
    network.reset()
    for point_id, point in network.points.items():
        planner = DStarLite(network, mode, point["node"][mode], network.goals(mode))
        closed_here = []
        for _ in range(25):
            expected = dijkstra_route(network, mode, point_id)
            actual = planner.plan(network.closed)
            assert actual["found"] == expected["found"]
            # Stop once the point is cut off, or already at a destination.
            if not expected["found"] or not expected["segments"]:
                break
            assert actual["time_s"] == pytest.approx(expected["time_s"], abs=1e-6)
            # Close the middle road of the current route.
            segment_id = expected["segments"][len(expected["segments"]) // 2]
            network.set_closed(segment_id, True)
            closed_here.append(segment_id)
        # Reopen everything, and check that the planner recovers the original route.
        network.reset()
        assert planner.plan(network.closed)["time_s"] == pytest.approx(
            dijkstra_route(network, mode, point_id)["time_s"], abs=1e-6)


def test_demo_scenarios_do_what_their_names_say(guisad):
    """Protects the live demo: each prepared closure must show the promised result."""
    network = guisad
    network.reset()
    with open(ROOT / "data" / "scenarios.json", encoding="utf-8") as file:
        scenarios = json.load(file)
    expected = {
        "A": (False, True),  # vehicle cut off, walking still works
        "B": (False, False),  # cut off for both
        "C": (True, True),  # route found for both, with a detour
    }
    for scenario in scenarios:
        before = dijkstra_route(network, "vehicle", scenario["point"])
        for segment_id in scenario["segments"]:
            network.set_closed(segment_id, True)
        vehicle = dijkstra_route(network, "vehicle", scenario["point"])
        walking = dijkstra_route(network, "walking", scenario["point"])
        assert (vehicle["found"], walking["found"]) == expected[scenario["name"][0]], scenario["name"]
        if scenario["name"][0] == "C":
            assert vehicle["time_s"] > before["time_s"]
        network.reset()


def test_critical_ranking_leaves_closures_unchanged(guisad):
    network = guisad
    network.reset()
    results = rank_critical_roads(network, "vehicle")
    assert results
    assert network.closed == set()
    # The ranking is sorted: no row may have more isolated points than the row above it.
    counts = [row["isolated"] for row in results]
    assert counts == sorted(counts, reverse=True)


def test_dstar_lite_still_correct_after_start_moves(guisad):
    """A responder already on the way: the start changes, and then a road closes."""
    network = guisad
    network.reset()
    point = next(iter(network.points.values()))
    start = point["node"]["vehicle"]
    goals = network.goals("vehicle")
    planner = DStarLite(network, "vehicle", start, goals)
    route = planner.plan(network.closed)
    # Move partway along the route, then close the road directly ahead.
    middle = route["nodes"][len(route["nodes"]) // 2]
    planner.move_start(middle)
    position = route["nodes"].index(middle)
    if position + 1 < len(route["nodes"]):
        ahead = list(network.graphs["vehicle"][middle][route["nodes"][position + 1]])
        for segment_id in ahead:
            network.set_closed(segment_id, True)
    result = planner.plan(network.closed)
    # Compare against a brand new planner that starts from the same spot.
    fresh = DStarLite(network, "vehicle", middle, goals).plan(network.closed)
    assert result["found"] == fresh["found"]
    if fresh["found"]:
        assert result["time_s"] == pytest.approx(fresh["time_s"], abs=1e-6)
    network.reset()
