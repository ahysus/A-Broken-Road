"""Downloads the Guisad roads and facilities ONCE and saves them as JSON.

Run this only on the build PC:  python src/build_data.py
The demo never runs this file, so the demo does not depend on the map servers
and the MacBook does not need OSMnx installed.
"""

# json writes the saved files. urllib downloads from the internet.
import json
import time
import urllib.error
import urllib.request

# ElementTree reads and edits the XML format that OpenStreetMap sends.
import xml.etree.ElementTree as ElementTree

# OSMnx turns OpenStreetMap data into a graph.
import osmnx as ox

# Load our own settings.
import config

# Keep OSMnx's place-search results in a folder, so a rerun does not repeat them.
ox.settings.cache_folder = str(config.ROOT / "cache")

# The raw download, and a copy containing only the ways that are usable roads.
RAW_FILE = config.ROOT / "cache" / "guisad_raw.osm"
ROADS_FILE = config.ROOT / "cache" / "guisad_roads.osm"

# OpenStreetMap's main data service. It returns everything inside a small rectangle.
# (The Overpass servers OSMnx normally uses were overloaded when this was built.)
MAP_URL = "https://api.openstreetmap.org/api/0.6/map?bbox={},{},{},{}"

# Road types that are not usable, such as roads that are only planned.
UNUSABLE_HIGHWAY_TYPES = {
    "abandoned", "construction", "planned", "proposed", "razed", "raceway",
    "platform", "bus_guideway", "no", "rest_area", "services",
}


def download_tile(west, south, east, north, collected):
    """Downloads one rectangle, splitting it in four if the service says it is too big."""
    # Put the four edges of the rectangle into the web address.
    url = MAP_URL.format(west, south, east, north)
    # Identify this program politely, as the service asks clients to do.
    request = urllib.request.Request(url, headers={"User-Agent": "guisad-thesis-prototype/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            root = ElementTree.fromstring(response.read())
    except urllib.error.HTTPError as error:
        # 400 means the rectangle holds too much data. Any other error is a real
        # problem, so "raise" stops the program and shows it.
        if error.code != 400:
            raise
        # Find the middle of the rectangle, then download its four quarters.
        middle_x = (west + east) / 2
        middle_y = (south + north) / 2
        download_tile(west, south, middle_x, middle_y, collected)
        download_tile(middle_x, south, east, middle_y, collected)
        download_tile(west, middle_y, middle_x, north, collected)
        download_tile(middle_x, middle_y, east, north, collected)
        return
    # Store each object by its type and id. Objects on a tile border arrive twice,
    # and this keeps only one copy of them.
    for element in root:
        if element.tag in {"node", "way", "relation"}:
            collected[(element.tag, element.get("id"))] = element
    # Wait one second between requests, so we do not burden a free public service.
    time.sleep(1)


def download_raw_map():
    """Downloads the map data once and keeps it, so a rerun needs no internet."""
    # If we already have the file, skip the download.
    if RAW_FILE.exists():
        return
    RAW_FILE.parent.mkdir(exist_ok=True)
    collected = {}
    download_tile(*config.BBOX, collected)
    # Put the combined objects into one file, in the order nodes, ways, relations.
    root = ElementTree.Element("osm", {"version": "0.6", "generator": "guisad-prototype"})
    for kind in ["node", "way", "relation"]:
        for (tag, _), element in collected.items():
            if tag == kind:
                root.append(element)
    ElementTree.ElementTree(root).write(RAW_FILE, encoding="utf-8", xml_declaration=True)


def keep_only_roads():
    """Saves a copy of the map data containing only public road and path ways."""
    tree = ElementTree.parse(RAW_FILE)
    root = tree.getroot()
    # OSM data also holds buildings, rivers and so on. OSMnx would treat each of
    # those as a road if we left them in, so remove everything that is not a road.
    for element in list(root):
        # Relations group other objects together. A road graph does not need them.
        if element.tag == "relation":
            root.remove(element)
        elif element.tag == "way":
            # Collect this way's tags into a simple dictionary.
            tags = {tag.get("k"): tag.get("v") for tag in element.findall("tag")}
            road_type = tags.get("highway")
            is_road = (
                road_type is not None  # it has to be a highway of some kind
                and road_type not in UNUSABLE_HIGHWAY_TYPES  # and actually usable
                and tags.get("area") != "yes"  # and not an open area like a plaza
                and tags.get("access") not in {"private", "no"}  # and public
                and tags.get("service") != "private"  # and not a private service road
            )
            if not is_road:
                root.remove(element)
    tree.write(ROADS_FILE, encoding="utf-8", xml_declaration=True)


def clean_highway(value):
    """Returns one road type, because OSM sometimes stores a list of them."""
    # After simplifying, one edge can hold several types, such as [residential, path].
    # Take the first so that every segment has one simple label.
    return value[0] if isinstance(value, list) else value


def clean_name(value):
    """Returns a road name as text, or an empty string if the road has no name."""
    # Merged edges can hold a list of names, so join them.
    if isinstance(value, list):
        return " / ".join(str(item) for item in value)
    # A missing name comes back as None, so turn that into an empty string.
    return str(value) if value else ""


def segments_from_graph(graph):
    """Turns the OSMnx graph into one list of physical road segments."""
    # Maps each physical road to its finished record, so that the two directions
    # of a two-way road become ONE segment. Closing it then closes both directions.
    found = {}
    # data=True includes each edge's attributes. keys=True includes the key that
    # tells apart two different roads joining the same pair of junctions.
    for u, v, key, data in graph.edges(keys=True, data=True):
        # A road that leaves and returns to one junction cannot help any route.
        if u == v:
            continue
        # Length in meters, rounded so that both directions produce the same value.
        length = round(float(data["length"]), 1)
        # Sort the two junction ids so that u-v and v-u produce the same identity.
        identity = (min(u, v), max(u, v), length)
        # If we already saw the opposite direction, this road is two-way.
        if identity in found:
            found[identity]["oneway"] = False
            continue
        # Use the road's curved shape if it has one, or a straight line if not.
        if "geometry" in data:
            line = list(data["geometry"].coords)
        else:
            line = [
                (graph.nodes[u]["x"], graph.nodes[u]["y"]),
                (graph.nodes[v]["x"], graph.nodes[v]["y"]),
            ]
        # Save everything about this segment. Leaflet expects [latitude, longitude].
        road_type = clean_highway(data.get("highway", "unclassified"))
        found[identity] = {
            "u": int(u),  # junction at the start, following the travel direction
            "v": int(v),  # junction at the end, following the travel direction
            "length_m": length,  # length in meters
            "highway": road_type,  # OSM road type, such as residential or steps
            "name": clean_name(data.get("name")),  # street name, if known
            "oneway": True,  # stays True unless the opposite direction appears
            "drivable": road_type not in config.NOT_DRIVABLE_HIGHWAY_TYPES,
            "line": [[round(y, 6), round(x, 6)] for x, y in line],
        }
    # Number the segments so the map can refer to each one by a simple id.
    segments = []
    for number, record in enumerate(found.values()):
        record["id"] = number
        segments.append(record)
    return segments


def destinations_from_osm():
    """Downloads facilities that a route could end at."""
    # These OSM tags describe the facility types named in the study's objectives.
    # amenity=shelter is left out on purpose. In Baguio's data it mostly marks waiting
    # sheds such as jeepney stops, so it would wrongly list them as evacuation centers.
    tags = {
        "amenity": ["hospital", "fire_station", "townhall"],
        "emergency": ["assembly_point"],
    }
    # Read them from the raw download, which still contains buildings and places.
    features = ox.features_from_xml(RAW_FILE, tags=tags)
    # Translate each OSM tag into the category names used in the thesis.
    labels = {
        "hospital": "hospital",
        "fire_station": "fire station",
        "townhall": "barangay hall",
        "assembly_point": "evacuation center",
    }
    results = []
    for _, row in features.iterrows():
        # A building is stored as a shape, so use its center point as the location.
        center = row.geometry.centroid
        # Find which of the tags this row has. Blank table cells come back as NaN,
        # and NaN is the only value not equal to itself, so x == x filters them out.
        amenity = row.get("amenity")
        emergency = row.get("emergency")
        tag = amenity if amenity == amenity else emergency
        name = row.get("name")
        results.append({
            "name": name if name == name else f"Unnamed {labels[tag]}",
            "type": labels[tag],
            "lat": round(center.y, 6),
            "lon": round(center.x, 6),
            "source": "OpenStreetMap, unverified",
        })
    return results


def boundaries_from_osm():
    """Downloads the outlines of the two barangays, for display on the map only."""
    outlines = []
    for name in ["Guisad Central", "Guisad Surong"]:
        # geocode_to_gdf asks OSM's place search for the outline of a named place.
        table = ox.geocode_to_gdf(f"{name}, Baguio, Philippines")
        shape = table.geometry.iloc[0]
        # Keep only the outer ring, converted to [latitude, longitude] for Leaflet.
        ring = [[round(y, 6), round(x, 6)] for x, y in shape.exterior.coords]
        outlines.append({"name": name, "ring": ring})
    return outlines


def main():
    # Create the data folder if it does not exist yet.
    config.DATA_DIR.mkdir(exist_ok=True)

    print("Downloading the map data...")
    download_raw_map()
    keep_only_roads()

    print("Building the road network...")
    # This makes ONE network holding roads, footpaths and stairs. Simplifying merges
    # the many small pieces of a road into one edge between two junctions. Vehicle
    # and walking rules are applied to it later, which gives two graphs built from
    # the same data, as Chapter 1 describes.
    graph = ox.graph_from_xml(ROADS_FILE, bidirectional=False, simplify=True, retain_all=False)

    print("Converting the network...")
    segments = segments_from_graph(graph)
    # Save only the fields the demo needs for each junction.
    nodes = {
        str(node): {"lat": round(data["y"], 6), "lon": round(data["x"], 6)}
        for node, data in graph.nodes(data=True)
    }

    print("Downloading barangay outlines...")
    boundaries = boundaries_from_osm()

    # Write the network file that the demo will read.
    with open(config.NETWORK_FILE, "w", encoding="utf-8") as file:
        json.dump({"nodes": nodes, "segments": segments, "boundaries": boundaries}, file)

    print("Downloading facilities...")
    facilities = destinations_from_osm()
    # Write facilities to a separate review file, so the editable destination
    # list used by the demo is never overwritten by accident.
    with open(config.DATA_DIR / "osm_facilities.json", "w", encoding="utf-8") as file:
        json.dump(facilities, file, indent=2, ensure_ascii=False)

    # Print a summary, so we can see that the download looks sensible.
    drivable = sum(1 for segment in segments if segment["drivable"])
    print(f"Junctions: {len(nodes)}")
    print(f"Segments: {len(segments)}, of which drivable: {drivable}")
    print(f"Facilities: {len(facilities)}")


# Run main() only when this file is started directly.
if __name__ == "__main__":
    main()
