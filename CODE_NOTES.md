# Code notes: how the Guisad rerouting system works

Every code file also has plain-English comments on each step. This page gives the big picture.

## The files
| File | What it does | Runs when |
|---|---|---|
| `src/config.py` | All settings: file locations, the download area, assumed speeds, which road types vehicles can use | Always |
| `src/build_data.py` | Downloads OpenStreetMap roads and facilities once, and saves them as JSON | Only when rebuilding the data, on the Windows PC |
| `src/make_demo_points.py` | Picks the 10 demo locations and the 3 demo closures | Only when rebuilding the data |
| `src/network.py` | Loads the saved roads, builds the vehicle and walking graphs, tracks closures | Every time the server starts |
| `src/analysis.py` | Dijkstra: isolation check, routes, critical road ranking | Every update |
| `src/dstar_lite.py` | D* Lite, written by us because NetworkX does not have it | Every update |
| `src/app.py` | The web server: receives clicks from the page and sends back results | While the demo runs |
| `templates/index.html` | The page: map, controls, legend | In the browser |
| `tests/` | Automated checks, 29 in total | `python -m pytest tests -q` |
| `data/` | Saved roads, demo points, destinations, demo closures | Read at startup |

## What the road data looks like
- A **junction** (node) is where roads meet. Each has a latitude and longitude.
- A **segment** (edge) is a piece of road between two junctions. Each has a length, a road type
  (residential, footway, steps...), a name if known, and whether it is one-way.
- Travel time on a segment = length / speed. Vehicles: 20 km/h. Walking: 4 km/h. Both are assumptions.

## Two graphs from one set of roads (`network.py`)
- **Vehicle graph:** leaves out footpaths, stairs, tracks and similar. One-way roads only go one way.
- **Walking graph:** every road and path, in both directions.
- Each graph keeps only its largest connected part, so a tiny unconnected piece of mapping does not
  look like an isolated area.
- Closing a segment removes it from **both** graphs, because a landslide blocks walkers and vehicles alike.

## Why the search runs backward
The code keeps a **reversed** copy of each graph and searches from the destinations outward.
One search from all destinations at once gives every junction its time to the nearest destination.
That is much faster than searching separately from every location.

## What happens when you click
1. **The page** sends the choice to the server, for example `/api/state?mode=vehicle&target=place:bgh&lat=...&lon=...`.
2. **`app.py`** checks the location is inside Guisad (`barangay_at`), then snaps it to the nearest junction.
3. It runs:
   - **Isolation check** (`isolation_report`, Dijkstra): which demo locations cannot reach the destination. These dots turn red.
   - **Before route** (`route_from_node` with `intact=True`, Dijkstra): the route as if nothing were closed. Drawn orange.
   - **Current route** (`DStarLite.plan`): drawn blue.
   - **Dijkstra check** (`route_from_node`): the same route by Dijkstra, kept to confirm D* Lite.
4. **The page** colors the roads and markers and updates the legend.

Closing a road sends `/api/toggle` with the segment id. The server marks it closed in both graphs.

## Dijkstra in one paragraph
Start at the destination with time 0. Repeatedly take the unvisited junction with the smallest known
time, and update its neighbors: if going through it is quicker, record the new time. When the starting
junction is reached, its time is the fastest route. NetworkX provides this (`multi_source_dijkstra`).

## D* Lite, step by step (`dstar_lite.py`)
D* Lite is the hardest part to explain, so here it is slowly.

**Two numbers per junction**
- `g`: the travel time to a destination that the search has settled on.
- `rhs`: what the neighbors say the time should be now: the best of (road time + that neighbor's `g`).

If `g` equals `rhs`, the junction is **consistent** and needs nothing. If not, it goes into a
**priority queue** to be fixed. Destinations always have `rhs = 0`.

**The first search** works like Dijkstra from the destinations, but stops as soon as the starting
junction's time is certain. Junctions it did not need are left alone.

**After a closure**
1. `apply_closures` finds which roads changed.
2. For each changed road u -> v, only u's `rhs` can change, so only u is recalculated (`_update_vertex`).
3. If u is now inconsistent, it goes into the queue.
4. `_compute` takes junctions from the queue in order and fixes them:
   - **Overconsistent** (`g > rhs`, a better time appeared): set `g = rhs`, then tell the junctions leading to it.
   - **Underconsistent** (`g < rhs`, its time got worse, e.g. its road closed): forget `g` (set it to infinity),
     then recalculate it and the junctions that depended on it.
5. It stops once the start is consistent and nothing in the queue could improve it.

**This is the point of D* Lite:** after a closure, it only fixes the junctions affected, instead of
searching the whole graph again. The page's route comes from `_extract_path`, which walks from the start,
always choosing the neighbor with the lowest (road time + neighbor's `g`), until it reaches a destination.

**The key and the heuristic**
- The queue order uses a key: (best time + an estimate of the distance to the start, best time).
- The estimate (`_h`) is straight-line distance / top speed. It never overestimates, which keeps the result exact.
- `km` is a correction used when the start moves (a responder already on the way). It avoids recalculating every key.

**Where it came from:** Koenig and Likhachev's D* Lite. Ours allows several destinations by giving each one `rhs = 0`.

## How we know it works (`tests/`)
- Small hand-made maps where the right answer is known: shortest route, detour after a closure, isolation, one-way roads, footpaths.
- **D* Lite against Dijkstra** on the real Guisad roads: 60 random closures and reopenings, and repeated
  closures right on the current route, for every demo location. Route times always match.
- The web server is tested like the page uses it, including bad input and starts outside Guisad.
- The demo closures are tested to do what their names say.

## Things to be honest about
- Demo locations, the evacuation center and speeds are placeholders.
- Facilities and roads come from OpenStreetMap and are not yet verified.
- The Guisad boundary is OpenStreetMap's outline, not necessarily the official one.
- Destinations connect to the nearest junction, not their real entrance.
- Landslide susceptibility and slope are not in the prototype yet.
- Timings on screen are single runs, not test results.

## Rebuilding the data (Windows PC only)
```
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe src\build_data.py
.venv\Scripts\python.exe src\make_demo_points.py
```
Delete `cache/guisad_raw.osm` first to download fresh data. Rebuilding renumbers the roads.
