import argparse
import json
import os
from math import radians, sin, cos, sqrt, atan2
from typing import Dict, Tuple

from graph import Graph, Node
from a_star import AStar

# geopy is optional in this environment
try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderServiceError
except Exception:  # pragma: no cover - geopy may not be installed
    Nominatim = None  # type: ignore
    GeocoderServiceError = Exception

# Fallback coordinates for common addresses when geopy is unavailable
ADDRESS_COORDS: Dict[str, Tuple[float, float]] = {
    "6666 W 66th St, Chicago, Illinois": (41.772, -87.782),
    "240 E Rosecrans Ave, Gardena, California": (33.901, -118.278),
    "323 E Roosevelt Ave, Zeeland, Michigan": (42.811, -86.017),
    "1043 Kaiser Rd SW, Olympia, Washington": (47.037, -122.932),
    "11755 S Austin Ave, Alsip, IL 60803 USA": (41.668, -87.736),
    "11756 S Austin Ave, Alsip, IL 60803 USA": (41.668, -87.736),
    "11757 S Austin Ave, Alsip, IL 60803 USA": (41.668, -87.736),
    "11758 S Austin Ave, Alsip, IL 60803 USA": (41.668, -87.736),
    "11759 S Austin Ave, Alsip, IL 60803 USA": (41.668, -87.736),
    "11761 S Austin Ave, Alsip, IL 60803 USA": (41.668, -87.736),
    "11762 S Austin Ave, Alsip, IL 60803 USA": (41.668, -87.736),
    "11763 S Austin Ave, Alsip, IL 60803 USA": (41.668, -87.736),
    "11764 S Austin Ave, Alsip, IL 60803 USA": (41.668, -87.736),
    "11765 S Austin Ave, Alsip, IL 60803 USA": (41.668, -87.736),
    "2019 Wood-Bridge Blvd, Bowling Green, Ohio": (41.377, -83.650),
    "196 Alwine Rd, Saxonburg, Pennsylvania": (40.756, -79.822),
    "6811 E Mission Ave, Spokane Valley, WA 99212 USA": (47.673, -117.282),
    "7081 International Dr, Louisville, Kentucky": (38.165, -85.741),
    "931 Merwin Road, Pennsylvania": (40.944, -80.308),
    "10908 County Rd 419, Texas": (30.180, -96.076),
    "450 Whitney Road West": (43.129, -77.516),
    "5349 W 161st St, Cleveland, Ohio": (41.379, -81.841),
    "2904 Scott Blvd, Santa Clara, California": (37.369, -121.972),
}


def _find_address(elements):
    """Recursively search for a Property with an address idShort."""
    for elem in elements:
        if elem.get("idShort") in {"Location", "Address", "Physical_address"}:
            val = elem.get("value")
            if isinstance(val, str):
                return val
        if isinstance(elem.get("submodelElements"), list):
            addr = _find_address(elem["submodelElements"])
            if addr:
                return addr
    return None


def load_aas_files(directory: str) -> Dict[str, Tuple[float, float]]:
    """Load AAS JSON files and convert addresses to coordinates."""
    coords: Dict[str, Tuple[float, float]] = {}
    geolocator = Nominatim(user_agent="aas_pathfinder") if Nominatim else None

    for name in os.listdir(directory):
        if not name.lower().endswith(".json"):
            continue
        path = os.path.join(directory, name)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        shells = data.get("assetAdministrationShells", [])
        if not shells:
            continue
        shell = shells[0]
        # use file name as node identifier to avoid duplicates
        node_name = os.path.splitext(name)[0]

        address = None
        for submodel in data.get("submodels", []):
            elems = submodel.get("submodelElements", [])
            address = _find_address(elems)
            if address:
                break
        if not address:
            continue
        address = address.strip()

        latlon = ADDRESS_COORDS.get(address)
        if latlon is None and geolocator:
            try:
                location = geolocator.geocode(address)
            except GeocoderServiceError:
                location = None
            if location:
                latlon = (location.latitude, location.longitude)

        if latlon is None:
            continue

        coords[node_name] = latlon

    return coords


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the Haversine distance between two points in kilometres."""
    R = 6371.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def build_graph_from_aas(coords: Dict[str, Tuple[float, float]]) -> Graph:
    graph = Graph()
    for name, (lat, lon) in coords.items():
        graph.add_node(Node(name, (lat, lon)))

    names = list(coords.keys())
    for i, a in enumerate(names):
        lat1, lon1 = coords[a]
        for b in names[i + 1 :]:
            lat2, lon2 = coords[b]
            dist = haversine(lat1, lon1, lat2, lon2)
            graph.add_edge(a, b, dist)
    return graph


def main():
    parser = argparse.ArgumentParser(description="AAS path finder")
    parser.add_argument(
        "--aas-dir",
        default="설비 json 파일",
        help="Directory containing AAS JSON files",
    )
    parser.add_argument(
        "--start",
        default="AAS_4000ton",
        help="Start node name (base file name)",
    )
    parser.add_argument(
        "--target",
        default="AAS_20AD-36",
        help="Target node name (base file name)",
    )
    args = parser.parse_args()

    coords = load_aas_files(args.aas_dir)
    if len(coords) < 2:
        print("Not enough AAS locations found.")
        return

    graph = build_graph_from_aas(coords)

    start = args.start
    target = args.target

    if not graph.find_node(start) or not graph.find_node(target):
        print("Start or target node not found in loaded AAS files.")
        return

    astar = AStar(graph, start, target)
    result = astar.search()
    if not result:
        print("No path found.")
        return

    path, total = result
    print("최단 경로: " + " → ".join(path))
    print(f"총 거리: {total:.1f} km")


if __name__ == "__main__":
    main()
