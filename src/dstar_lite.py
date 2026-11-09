"""D* Lite, written for this project because NetworkX does not include it.

The idea, in plain words:
- The search works BACKWARD, from the destinations toward the starting point.
- Every junction has two numbers. g is the best time we have settled on. rhs is
  what its neighbors say the best time should be right now.
- If g equals rhs, the junction is "consistent". If not, it needs fixing and waits
  in a priority queue.
- When a road closes, only the junctions affected are marked inconsistent, so only
  they get repaired. That reuse is why it can replan without starting over.

Based on Koenig and Likhachev's D* Lite algorithm. This version has several goals:
every destination simply gets rhs = 0, so "nearest destination" needs nothing extra.
"""

# heapq is Python's priority queue. It always gives back the smallest item first.
import heapq
import time

# distance_m gives the straight-line distance between two map points.
from network import distance_m

# Infinity means "no known route". Any real time is smaller than this.
INFINITY = float("inf")


class DStarLite:
    """A route planner for one mode, one starting point and one set of destinations."""

    def __init__(self, network, mode, start, goals):
        self.network = network  # the road data
        self.mode = mode  # "vehicle" or "walking"
        self.start = start  # the junction the route starts from
        self.goals = set(goals)  # the junctions a route may end at
        self.graph = network.graphs[mode]  # the full graph, including closed roads
        self.closed = set()  # the closures this planner already knows about
        self.g = {}  # settled best time for each junction; missing means infinity
        self.rhs = {}  # neighbor-based best time; missing means infinity
        self.queue = []  # priority queue of junctions needing repair
        self.queued_key = {}  # each queued junction's current key, to spot old entries
        self.km = 0.0  # correction added to keys when the start position moves
        self.expanded = 0  # counts repaired junctions, to show how much work was done
        # The fastest possible speed, so the heuristic never overestimates the time.
        self.max_speed = network.speed_mps[mode]
        # Every destination is 0 seconds from itself, and is queued to start the search.
        for goal in self.goals:
            self.rhs[goal] = 0.0
            self._push(goal)

    def _h(self, node):
        """Heuristic: a lower-bound guess of the time from the start to this junction."""
        a, b = self.network.nodes[self.start], self.network.nodes[node]
        # Straight line distance / top speed can never exceed the true travel time.
        # Multiplying by 0.99 keeps that true despite the rounding of saved lengths.
        return 0.99 * distance_m(a["lat"], a["lon"], b["lat"], b["lon"]) / self.max_speed

    def _key(self, node):
        """The queue priority of a junction. Smaller keys are repaired first."""
        best = min(self.g.get(node, INFINITY), self.rhs.get(node, INFINITY))
        # First part: estimated total time through this junction, like A*.
        # Second part: breaks ties in favor of the lower time.
        return (best + self._h(node) + self.km, best)

    def _push(self, node):
        """Puts a junction in the queue, replacing any earlier entry for it."""
        key = self._key(node)
        self.queued_key[node] = key
        heapq.heappush(self.queue, (key, node))

    def _top(self):
        """Returns the smallest valid queue entry, or None if the queue is empty."""
        while self.queue:
            key, node = self.queue[0]
            # heapq cannot update entries in place, so old ones are left in the queue.
            # An entry is old if it differs from the junction's current key.
            if self.queued_key.get(node) == key:
                return key, node
            heapq.heappop(self.queue)
        return None

    def _cost(self, u, v):
        """Travel time from u to v using the best open road, or infinity if none."""
        # .get() returns {} when no road at all joins these two junctions.
        roads = self.graph[u].get(v, {})
        # Check each road between them, skipping closed ones.
        times = [data["time_s"] for key, data in roads.items() if key not in self.closed]
        return min(times, default=INFINITY)

    def _update_vertex(self, node):
        """Recalculates a junction's rhs, and queues it if it has become inconsistent."""
        # Destinations always keep rhs = 0, so they are not recalculated.
        if node not in self.goals:
            # rhs = the best of (time to next junction + that junction's g).
            self.rhs[node] = min(
                (self._cost(node, next_node) + self.g.get(next_node, INFINITY)
                 for next_node in self.graph.successors(node)),
                default=INFINITY,
            )
        # Remove any queued entry. It only goes back if it still needs repair.
        self.queued_key.pop(node, None)
        if self.g.get(node, INFINITY) != self.rhs.get(node, INFINITY):
            self._push(node)

    def _compute(self):
        """Repairs junctions until the start's time is correct. This is the main loop."""
        while True:
            top = self._top()
            # An empty queue means nothing is left to repair.
            if top is None:
                return
            start_key = self._key(self.start)
            g_start = self.g.get(self.start, INFINITY)
            rhs_start = self.rhs.get(self.start, INFINITY)
            # Stop when the start is consistent and nothing queued could improve it.
            # All other junctions are left unrepaired, which is what saves the work.
            if top[0] >= start_key and g_start == rhs_start:
                return
            old_key, node = top
            new_key = self._key(node)
            if old_key < new_key:
                # The key is out of date because of km, so requeue it correctly.
                self._push(node)
            elif self.g.get(node, INFINITY) > self.rhs.get(node, INFINITY):
                # Overconsistent: a better time was found, so settle it, then let
                # the junctions that lead here recalculate using this better time.
                heapq.heappop(self.queue)
                self.queued_key.pop(node, None)
                self.g[node] = self.rhs[node]
                self.expanded += 1
                for previous in self.graph.predecessors(node):
                    self._update_vertex(previous)
            else:
                # Underconsistent: its time got worse, for example from a closure.
                # Forget it, then recalculate it and the junctions that depended on it.
                heapq.heappop(self.queue)
                self.queued_key.pop(node, None)
                self.g[node] = INFINITY
                self.expanded += 1
                for previous in self.graph.predecessors(node):
                    self._update_vertex(previous)
                self._update_vertex(node)

    def apply_closures(self, closed_now):
        """Tells the planner what is closed now, updating only what changed."""
        # ^ gives the segments that differ: newly closed or newly reopened.
        changed = self.closed ^ set(closed_now)
        if not changed:
            return
        # Record the new state first, so that _cost sees every change at once.
        self.closed = set(closed_now)
        edges = self.network.segment_edges[self.mode]
        for segment_id in changed:
            # A segment may not exist in this mode, such as a footpath for vehicles.
            for u, _ in edges.get(segment_id, []):
                # Only u's rhs depends on the road u->v, so only u needs recalculating.
                self._update_vertex(u)

    def move_start(self, new_start):
        """Moves the start, for example when a responder has already traveled partway."""
        # Keys were computed using the old start. Rather than recalculate every key
        # in the queue, km adds the same correction to all future keys.
        self.km += self._h(new_start)
        self.start = new_start

    def plan(self, closed_now):
        """Updates for the current closures, then returns the route and its statistics."""
        self.expanded = 0
        started = time.perf_counter()
        self.apply_closures(closed_now)
        self._compute()
        nodes = self._extract_path()
        milliseconds = (time.perf_counter() - started) * 1000
        # An empty result means no open route to any destination.
        if nodes is None:
            return {"found": False, "ms": milliseconds, "expanded": self.expanded}
        # rhs at the start is its final travel time. It is 0 if the start is a destination.
        return {"found": True, "nodes": nodes, "time_s": self.rhs[self.start],
                "ms": milliseconds, "expanded": self.expanded}

    def _extract_path(self):
        """Follows the best next junction from the start until reaching a destination."""
        # Infinity at the start means no route exists.
        if self.rhs.get(self.start, INFINITY) == INFINITY:
            return None
        nodes = [self.start]
        current = self.start
        # Keeps track of visited junctions, as a safeguard against endless loops.
        seen = {current}
        while current not in self.goals:
            # Choose the neighbor giving the lowest (road time + that neighbor's g).
            current = min(
                self.graph.successors(current),
                key=lambda next_node: self._cost(nodes[-1], next_node) + self.g.get(next_node, INFINITY),
            )
            if current in seen:
                raise RuntimeError("D* Lite path looped, which should never happen")
            seen.add(current)
            nodes.append(current)
        return nodes
