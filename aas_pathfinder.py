import argparse
import json
import os
import logging
from math import radians, sin, cos, sqrt, atan2
from typing import Dict, Tuple, List

from dataclasses import dataclass
from graph import Graph, Node
from a_star import AStar

logger = logging.getLogger(__name__)

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

# Mapping of IRDI codes to process steps
IRDI_PROCESS_MAP = {
    "0173-1#01-AKJ741#017": "Turning",
    "0173-1#01-AKJ783#017": "Milling",
    "0173-1#01-AKJ867#017": "Grinding",
}

# Mapping of Category/Type values to process steps
TYPE_PROCESS_MAP = {
    "Hot Former": "Forging",
    "CNC LATHE": "Turning",
    "Vertical Machining Center": "Milling",
    "Horizontal Machining Center": "Milling",
    "Flat surface grinder": "Grinding",
    "Cylindrical grinder": "Grinding",
    "Assembly System": "Assembly",
}


@dataclass
class Machine:
    name: str
    coords: Tuple[float, float]
    process: str
    status: str
    address: str


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


def _find_status(elements):
    """Recursively search for a Property with an idShort containing 'status'."""
    for elem in elements:
        id_short = elem.get("idShort", "").lower()
        if "status" in id_short:
            val = elem.get("value")
            if isinstance(val, str):
                return val
        if isinstance(elem.get("submodelElements"), list):
            status = _find_status(elem["submodelElements"])
            if status:
                return status
    return None


def _find_type_process(elements):
    """Recursively search for a 'Type' property and map it to a process."""
    for elem in elements:
        if elem.get("idShort") == "Type":
            val = elem.get("value")
            if isinstance(val, str):
                proc = TYPE_PROCESS_MAP.get(val)
                if proc:
                    return proc
        if isinstance(elem.get("submodelElements"), list):
            proc = _find_type_process(elem["submodelElements"])
            if proc:
                return proc
    return None


def load_machines(directory: str) -> Dict[str, Machine]:
    """Load AAS JSON files and return running machines with coordinates."""
    machines: Dict[str, Machine] = {}
    geolocator = Nominatim(user_agent="aas_pathfinder") if Nominatim else None

    for name in os.listdir(directory):
        logger.debug("Processing file: %s", name)
        if not name.lower().endswith(".json"):
            logger.debug("  Skipped (not JSON)")
            continue
        path = os.path.join(directory, name)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.debug("  Failed to load JSON: %s", e)
            continue

        shells = data.get("assetAdministrationShells", [])
        if not shells:
            logger.debug("  No shells found")
            continue
        shell = shells[0]
        node_name = os.path.splitext(name)[0]

        address = None
        status = None
        process = None
        for submodel in data.get("submodels", []):
            elems = submodel.get("submodelElements", [])
            if address is None:
                address = _find_address(elems)
            if status is None:
                status = _find_status(elems)
            if submodel.get("idShort") == "Category" and process is None:
                process = _find_type_process(elems)
            sem_id = (
                submodel.get("semanticId", {})
                .get("keys", [{}])[0]
                .get("value")
            )
            if sem_id in IRDI_PROCESS_MAP and process is None:
                process = IRDI_PROCESS_MAP[sem_id]
            if address and status and process:
                break
        if not address:
            logger.debug("  No address found")
            continue
        address = address.strip()
        logger.debug("  Address: %s", address)

        latlon = ADDRESS_COORDS.get(address)
        if latlon is None and geolocator:
            try:
                location = geolocator.geocode(address)
            except GeocoderServiceError:
                location = None
            if location:
                latlon = (location.latitude, location.longitude)
        if status is not None:
            logger.debug("  Status: %s", status)
        if process is not None:
            logger.debug("  Process: %s", process)

        if latlon is None:
            logger.debug("  Unable to determine coordinates for %s", address)
            continue

        if status is None:
            status = "Unknown"

        if process is None:
            # fall back to shell idShort heuristics
            sid = shell.get("idShort", "").lower()
            if "forging" in sid:
                process = "Forging"
            elif "assembly" in sid:
                process = "Assembly"
            else:
                continue

        machine = Machine(node_name, latlon, process, status, address)
        if machine.status.lower() == "running":
            logger.debug("  Added running machine: %s", machine)
            machines[node_name] = machine

    return machines


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


def path_distance(graph: Graph, path: List[str]) -> float:
    total = 0.0
    for a, b in zip(path, path[1:]):
        node = graph.find_node(a)
        for neigh, w in node.neighbors:
            if neigh.value == b:
                total += w
                break
    return total


def dijkstra_path(graph: Graph, start: str, goal: str) -> Tuple[List[str], float]:
    from heapq import heappush, heappop

    start_node = graph.find_node(start)
    goal_node = graph.find_node(goal)
    queue = [(0.0, start_node)]
    dist = {start_node.value: 0.0}
    prev: Dict[str, str] = {}
    visited = set()

    while queue:
        d, node = heappop(queue)
        if node.value in visited:
            continue
        visited.add(node.value)
        if node == goal_node:
            break
        for neigh, w in node.neighbors:
            nd = d + w
            if nd < dist.get(neigh.value, float("inf")):
                dist[neigh.value] = nd
                prev[neigh.value] = node.value
                heappush(queue, (nd, neigh))

    if goal_node.value not in dist:
        return [], float("inf")

    path = [goal]
    cur = goal
    while cur != start:
        cur = prev[cur]
        path.append(cur)
    path.reverse()
    return path, dist[goal]


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
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug output",
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(message)s")
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)


    machines = load_machines(args.aas_dir)
    if not machines:
        logger.info("No running machines with valid locations found.")
        return

    # Organise machines by process step
    by_process: Dict[str, List[Machine]] = {}
    for m in machines.values():
        by_process.setdefault(m.process, []).append(m)
    logger.debug(
        "Loaded machines: %s",
        {k: [m.name for m in v] for k, v in by_process.items()},
    )

    # Print available machine counts per process
    logger.info("Available machines by process:")
    for step in ["Forging", "Turning", "Milling", "Grinding", "Assembly"]:
        names = [m.name for m in by_process.get(step, [])]
        if names:
            logger.info("  %s: %d", step, len(names))
        else:
            logger.info("  %s: none", step)

    flow = ["Forging", "Turning", "Milling", "Grinding", "Assembly"]
    selected: List[Machine] = []

    for step in flow:
        candidates = by_process.get(step, [])
        logger.debug("Step '%s' candidates: %s", step, [c.name for c in candidates])
        if not candidates:
            logger.debug("No candidates for %s", step)
            continue
        if not selected:
            chosen = candidates[0]
        else:
            prev = selected[-1]
            chosen = min(
                candidates,
                key=lambda m: haversine(
                    prev.coords[0], prev.coords[1], m.coords[0], m.coords[1]
                ),
            )
        logger.debug("Chosen for %s: %s", step, chosen.name)
        selected.append(chosen)
        by_process[step] = [c for c in candidates if c != chosen]

    if not selected:
        logger.info("No machines selected for the flow.")
        return

    logger.info("\nSelected machines:")
    for mach in selected:
        logger.info(
            "  %s (%s)\n    %s\n    lat %.3f, lon %.3f",
            mach.name,
            mach.process,
            mach.address,
            mach.coords[0],
            mach.coords[1],
        )

    logger.info(" → ".join(m.name for m in selected))

    coords = {m.name: m.coords for m in selected}
    graph = build_graph_from_aas(coords)

    total_dist = 0.0
    logger.info("\nSegment distances:")
    for a, b in zip(selected, selected[1:]):
        path, d = dijkstra_path(graph, a.name, b.name)
        total_dist += d
        logger.info("%s → %s: %.1f km", a.name, b.name, d)
    logger.info("Total distance: %.1f km", total_dist)
    try:
        import folium

        m = folium.Map(location=selected[0].coords, zoom_start=5)
        prev = None
        for mach in selected:
            folium.Marker(
                location=mach.coords,
                popup=f"{mach.name} ({mach.process}) - {mach.status}",
            ).add_to(m)
            if prev:
                folium.PolyLine([prev, mach.coords], color="blue").add_to(m)
            prev = mach.coords
        m.save("process_flow.html")
        logger.info("Saved flow visualisation to 'process_flow.html'.")
    except Exception:
        logger.info("folium not available; skipping visualisation.")


if __name__ == "__main__":
    main()
