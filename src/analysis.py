"""Isolation checks and Dijkstra routes. Everything here reads the current closures,
unless intact=True is passed, which answers "what was it like before any closure?"."""

# time measures how long a search takes.
import time

# NetworkX provides the Dijkstra implementation.
import networkx as nx


def search_graph(network, mode, intact=False):
    """Chooses the graph to search: with closures applied, or as if nothing were closed."""
    return network.reversed_intact[mode] if intact else network.reversed_open[mode]


def isolation_report(network, mode, target="any", intact=False):
    """Returns the time, in seconds, from each point to its nearest destination.

    A value of None means the point is ISOLATED, with no open route to any destination.
    One Dijkstra search runs outward from ALL chosen destinations, along reversed
    roads, which is much faster than searching separately from every point.
    """
    goals = network.goals(mode, target)
    # This version of Dijkstra starts from several junctions at the same time, so each
    # junction gets its time to whichever destination is nearest. With no destinations,
    # nothing can be reached. Only times are needed, so it skips building the paths.
    times = (
        nx.multi_source_dijkstra_path_length(search_graph(network, mode, intact), goals, weight="time_s")
        if goals else {}
    )
    # .get() returns None when the point's junction was never reached by the search.
    return {
        point_id: times.get(point["node"][mode])
        for point_id, point in network.points.items()
    }


def cheapest_segment(graph, u, v):
    """Finds the shortest segment leading from junction u to junction v."""
    # The reversed graph stores u->v as v->u. Two roads may join the same junctions,
    # and min() picks the one with the lowest travel time.
    options = graph[v][u]
    segment_id = min(options, key=lambda key: options[key]["time_s"])
    return segment_id, options[segment_id]


def describe_path(network, mode, nodes, intact=False):
    """Turns a list of junctions into segment ids, total distance and total time."""
    graph = search_graph(network, mode, intact)
    segment_ids, length, seconds = [], 0.0, 0.0
    # zip pairs each junction with the next one, giving one pair per road piece.
    for u, v in zip(nodes, nodes[1:]):
        segment_id, data = cheapest_segment(graph, u, v)
        segment_ids.append(segment_id)
        length += data["length_m"]
        seconds += data["time_s"]
    return {"segments": segment_ids, "length_m": length, "time_s": seconds}


def destination_names(network, mode, node):
    """Names the destination(s) attached to a junction."""
    return [place["name"] for place in network.destinations.values() if place["node"][mode] == node]


def route_from_node(network, mode, start, target="any", intact=False):
    """Finds the fastest route from a junction with Dijkstra, and measures the search time."""
    goals = network.goals(mode, target)
    # perf_counter is a high-precision stopwatch.
    started = time.perf_counter()
    try:
        # target=start stops the search once the starting junction has been reached.
        _, path = nx.multi_source_dijkstra(
            search_graph(network, mode, intact), goals, target=start, weight="time_s"
        )
    except (nx.NetworkXNoPath, ValueError):
        # NetworkXNoPath means no route exists. ValueError means no destinations exist.
        return {"found": False, "ms": (time.perf_counter() - started) * 1000}
    milliseconds = (time.perf_counter() - started) * 1000
    # The path runs from destination to start, so reverse it for travel order.
    nodes = list(reversed(path))
    result = describe_path(network, mode, nodes, intact)
    result.update(found=True, ms=milliseconds, nodes=nodes,
                  destination=destination_names(network, mode, nodes[-1]))
    return result


def dijkstra_route(network, mode, point_id, target="any"):
    """Finds the fastest route from one of the saved points."""
    return route_from_node(network, mode, network.points[point_id]["node"][mode], target)


def rank_critical_roads(network, mode, target="any", limit=10):
    """Ranks open roads by how much harm closing each one would do to the points.

    It closes one road at a time, measures the damage, then reopens it. Only roads on
    a point's current route are tried, because closing any other road cannot change
    that point's fastest time. Results depend on the points, which are demo data for now.
    """
    # The current situation, used as the baseline for "added" time.
    baseline = isolation_report(network, mode, target)
    candidates = set()
    for point_id in network.points:
        route = dijkstra_route(network, mode, point_id, target)
        if route["found"]:
            candidates.update(route["segments"])
    results = []
    for segment_id in candidates:
        network.set_closed(segment_id, True)
        after = isolation_report(network, mode, target)
        # Always reopen, so this analysis leaves the officer's closures unchanged.
        network.set_closed(segment_id, False)
        isolated, added_s = 0, 0.0
        for point_id, before_s in baseline.items():
            # Skip points already isolated, because this road did not cause that.
            if before_s is None:
                continue
            if after[point_id] is None:
                isolated += 1
            else:
                added_s += after[point_id] - before_s
        results.append({
            "segment": segment_id,
            "name": network.segments[segment_id]["name"],
            "isolated": isolated,
            "added_s": added_s,
        })
    # Sort most isolated first, then most added time. Minus signs make it descending.
    results.sort(key=lambda item: (-item["isolated"], -item["added_s"]))
    return results[:limit]
