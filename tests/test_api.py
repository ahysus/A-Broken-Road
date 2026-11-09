"""Tests the web server the way the page uses it, without needing a browser."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import app as server

# A spot inside Guisad, used as the "clicked" starting point.
CLICK = {"lat": 16.4195, "lon": 120.5825}


def client():
    # Flask's test client sends requests straight to the app, with no real network.
    server.network.reset()
    return server.app.test_client()


def state(web, **choices):
    return web.get("/api/state", query_string=choices).get_json()


def test_page_and_map_library_load():
    web = client()
    assert web.get("/").status_code == 200
    assert web.get("/static/leaflet/leaflet.js").status_code == 200
    assert web.get("/static/leaflet/leaflet.css").status_code == 200


def test_network_lists_roads_and_points():
    data = client().get("/api/network").get_json()
    assert len(data["segments"]) > 1000
    assert len(data["points"]) == 10
    # Every demo marker has to stay clearly labeled as a demo.
    assert all(point["name"].startswith("Demo Point") for point in data["points"])


def test_no_start_chosen_returns_no_route_but_still_checks_isolation():
    answer = state(client())
    assert answer["start"] is None
    assert "dijkstra" not in answer
    assert answer["cut_off"] == []


def test_clicking_any_spot_gives_a_route():
    answer = state(client(), mode="vehicle", **CLICK)
    assert answer["start"]["snap_m"] < 100
    assert answer["dijkstra"]["found"] is True
    assert answer["dijkstra"]["segments"]


def test_user_can_choose_one_specific_destination():
    web = client()
    for place in server.network.destinations.values():
        answer = state(web, mode="vehicle", target="place:" + place["id"], **CLICK)
        assert answer["dijkstra"]["destination"] == [place["name"]]


def test_nearest_of_a_type_only_goes_to_that_type():
    web = client()
    hospitals = {p["name"] for p in server.network.destinations.values() if p["type"] == "hospital"}
    answer = state(web, mode="walking", target="hospital", **CLICK)
    assert set(answer["dijkstra"]["destination"]) <= hospitals


def test_closing_a_road_on_the_route_changes_it_and_shows_added_time():
    web = client()
    first = state(web, mode="vehicle", target="place:slu", **CLICK)["dijkstra"]
    road = first["segments"][len(first["segments"]) // 2]
    assert web.post("/api/toggle", json={"segment": road}).get_json()["closed"] == [road]
    answer = state(web, mode="vehicle", target="place:slu", **CLICK)
    assert road in answer["closed"]
    # "Before" must ignore the closure, and the new route must avoid the closed road.
    assert answer["before_route"]["time_s"] == first["time_s"]
    if answer["dijkstra"]["found"]:
        assert road not in answer["dijkstra"]["segments"]
        assert answer["dijkstra"]["time_s"] >= first["time_s"]
    assert web.post("/api/toggle", json={"segment": road}).get_json()["closed"] == []


def test_the_two_algorithms_agree_for_every_mode_and_destination():
    web = client()
    targets = ["any", "hospital", "fire station", "barangay hall", "evacuation center"]
    targets += ["place:" + key for key in server.network.destinations]
    for mode in ["vehicle", "walking"]:
        for target in targets:
            answer = state(web, mode=mode, target=target, **CLICK)
            assert answer["dijkstra"]["found"] == answer["dstar"]["found"]
            assert abs(answer["dijkstra"]["time_s"] - answer["dstar"]["time_s"]) < 1e-6


def test_scenario_a_shows_vehicle_cut_off_with_walking_route():
    web = client()
    spot = web.post("/api/scenario", json={"index": 0}).get_json()
    answer = state(web, mode="vehicle", lat=spot["lat"], lon=spot["lon"])
    assert answer["dijkstra"]["found"] is False
    assert answer["dstar"]["found"] is False
    assert answer["other_mode"]["found"] is True
    assert answer["cut_off"]


def test_reset_clears_closures():
    web = client()
    web.post("/api/scenario", json={"index": 1})
    assert web.post("/api/reset", json={}).get_json()["closed"] == []
    assert state(web)["closed"] == []


def test_bad_input_gets_an_error_not_a_crash():
    web = client()
    assert web.get("/api/state?mode=boat").status_code == 400
    assert web.get("/api/state?target=place:nowhere").status_code == 400
    assert web.get("/api/state?lat=abc&lon=1").status_code == 400
    assert web.get("/api/state?lat=999&lon=1").status_code == 400
    assert web.post("/api/toggle", json={"segment": -1}).status_code == 400


def test_starting_point_outside_guisad_is_refused():
    web = client()
    # Session Road area, outside both barangays.
    answer = web.get("/api/state", query_string={"lat": 16.4120, "lon": 120.5980})
    assert answer.status_code == 400
    assert "Guisad" in answer.get_json()["error"]
    # Every demo marker is inside Guisad, so all of them are accepted.
    for point in server.network.points.values():
        assert web.get("/api/state", query_string={"lat": point["lat"], "lon": point["lon"]}).status_code == 200


def test_roads_are_marked_inside_or_outside_guisad():
    segments = client().get("/api/network").get_json()["segments"]
    inside = sum(1 for segment in segments if segment["in_study_area"])
    # Guisad is a small part of the downloaded area, but it does contain roads.
    assert 0 < inside < len(segments) / 2


def test_critical_endpoint_returns_rows():
    rows = client().get("/api/critical?mode=vehicle").get_json()
    assert rows and {"segment", "isolated", "added_s"} <= set(rows[0])
