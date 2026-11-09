"""Tests the web server the way the page uses it, without needing a browser."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import app as server


def client():
    # Flask's test client sends requests straight to the app, with no real network.
    server.network.reset()
    return server.app.test_client()


def test_page_and_map_library_load():
    web = client()
    assert web.get("/").status_code == 200
    assert web.get("/static/leaflet/leaflet.js").status_code == 200
    assert web.get("/static/leaflet/leaflet.css").status_code == 200


def test_network_lists_roads_points_and_scenarios():
    data = client().get("/api/network").get_json()
    assert len(data["segments"]) > 1000
    assert len(data["points"]) == 10
    assert len(data["scenarios"]) == 3
    # Every demo point has to stay clearly labeled as a demo.
    assert all(point["name"].startswith("Demo Point") for point in data["points"])


def test_clicking_a_road_closes_then_reopens_it():
    web = client()
    route = web.get("/api/state?mode=vehicle&point=P1").get_json()["dijkstra"]
    road = route["segments"][0]
    assert web.post("/api/toggle", json={"segment": road}).get_json()["closed"] == [road]
    assert road in web.get("/api/state?mode=vehicle&point=P1").get_json()["closed"]
    assert web.post("/api/toggle", json={"segment": road}).get_json()["closed"] == []


def test_the_two_algorithms_agree_in_every_mode_and_destination_type():
    web = client()
    for mode in ["vehicle", "walking"]:
        for target in ["any", "hospital", "fire station", "barangay hall", "evacuation center"]:
            state = web.get("/api/state", query_string={"mode": mode, "target": target, "point": "P3"}).get_json()
            assert state["dijkstra"]["found"] == state["dstar"]["found"]
            assert abs(state["dijkstra"]["time_s"] - state["dstar"]["time_s"]) < 1e-6


def test_scenario_a_shows_vehicle_cut_off_with_walking_route():
    web = client()
    answer = web.post("/api/scenario", json={"index": 0}).get_json()
    state = web.get("/api/state", query_string={"mode": "vehicle", "point": answer["point"]}).get_json()
    assert state["dijkstra"]["found"] is False
    assert state["dstar"]["found"] is False
    row = next(each for each in state["table"] if each["id"] == answer["point"])
    assert row["now"]["vehicle"] is None
    assert row["now"]["walking"] is not None


def test_reset_clears_closures():
    web = client()
    web.post("/api/scenario", json={"index": 1})
    assert web.post("/api/reset", json={}).get_json()["closed"] == []
    assert web.get("/api/state").get_json()["closed"] == []


def test_bad_input_gets_an_error_not_a_crash():
    web = client()
    assert web.get("/api/state?mode=boat").status_code == 400
    assert web.post("/api/toggle", json={"segment": -1}).status_code == 400


def test_critical_endpoint_returns_rows():
    rows = client().get("/api/critical?mode=vehicle").get_json()
    assert rows and {"segment", "isolated", "added_s"} <= set(rows[0])
