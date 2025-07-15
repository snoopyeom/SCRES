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
        node_name = (
            shell.get("idShort")
            or shell.get("identification", {}).get("id")
            or os.path.splitext(name)[0]
        )

        address = None
        for submodel in data.get("submodels", []):
            elems = submodel.get("submodelElements", [])
            address = _find_address(elems)
            if address:
                break
        if not address or not geolocator:
            continue

        try:
            location = geolocator.geocode(address)
        except GeocoderServiceError:
            continue
        if location is None:
            continue
        coords[node_name] = (location.latitude, location.longitude)

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
    args = parser.parse_args()

    coords = load_aas_files(args.aas_dir)
    if len(coords) < 2:
        print("Not enough AAS locations found.")
        return

    graph = build_graph_from_aas(coords)

    start = "Forging_AAS_Chicago"
    target = "Grinding_AAS_Jinju"

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
