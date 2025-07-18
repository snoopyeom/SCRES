import argparse
import json
import logging
import os
from math import radians, sin, cos, sqrt, atan2
from typing import Dict, Tuple, List

from dataclasses import dataclass
from pymongo import MongoClient

from graph import Graph, Node
from a_star import AStar

logger = logging.getLogger("__main__")

try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderServiceError
except Exception:
    Nominatim = None
    GeocoderServiceError = Exception

ADDRESS_COORDS: Dict[str, Tuple[float, float]] = {
    "6666 W 66th St, Chicago, Illinois": (41.772, -87.782),
    "2904 Scott Blvd, Santa Clara, California": (37.369, -121.972),
}

IRDI_PROCESS_MAP = {
    "0173-1#01-AKJ741#017": "Turning",
    "0173-1#01-AKJ783#017": "Milling",
    "0173-1#01-AKJ867#017": "Grinding",
}

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

def upload_aas_documents(input_dir: str, mongo_uri: str, db_name: str, collection_name: str) -> int:
    """Upload every JSON file in ``input_dir`` into MongoDB.

    Returns the number of successfully inserted documents.
    """
    if not os.path.isdir(input_dir):
        raise FileNotFoundError(f"input directory not found: {input_dir}")

    try:
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection = db[collection_name]
    except Exception as exc:  # pragma: no cover - connection issues
        logger.error("MongoDB 연결 실패: %s", exc)
        raise

    collection.delete_many({})

    inserted = 0
    for filename in os.listdir(input_dir):
        if not filename.lower().endswith(".json"):
            continue
        filepath = os.path.join(input_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                json_data = json.load(f)
                if "assetAdministrationShells" not in json_data:
                    logger.warning("assetAdministrationShells 누락: %s", filename)
                    continue
                if not json_data.get("submodels"):
                    logger.warning("submodels 누락: %s", filename)
                    continue
                collection.insert_one({"filename": filename, "json": json_data})
                inserted += 1
                logger.debug("업로드 완료: %s", filename)
            except Exception as exc:  # pragma: no cover - invalid file
                logger.warning("업로드 실패: %s - %s", filename, exc)

    client.close()
    logger.info("총 %d개 문서 업로드 완료", inserted)
    return inserted


def _find_address(elements):
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

def load_machines_from_mongo(mongo_uri: str, db_name: str, collection_name: str) -> Dict[str, Machine]:
    machines: Dict[str, Machine] = {}
    geolocator = Nominatim(user_agent="aas_pathfinder") if Nominatim else None
    if not geolocator:
        logger.debug("geopy not available; 주소 좌표 변환을 건너뜁니다.")

    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]

    for doc in collection.find({}):
        data = doc.get("json", {})
        name = doc.get("filename", "unknown")
        node_name = os.path.splitext(name)[0]

        shells = data.get("assetAdministrationShells", [])
        if not shells:
            continue
        shell = shells[0]

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
            continue
        address = address.strip()

        latlon = ADDRESS_COORDS.get(address)
        if latlon is None and geolocator:
            try:
                location = geolocator.geocode(address)
                if location:
                    latlon = (location.latitude, location.longitude)
            except GeocoderServiceError:
                continue

        if not latlon:
            continue
        if status is None:
            status = "Unknown"
        if process is None:
            sid = shell.get("idShort", "").lower()
            if "forging" in sid:
                process = "Forging"
            elif "assembly" in sid:
                process = "Assembly"
            else:
                continue

        machine = Machine(node_name, latlon, process, status, address)
        if machine.status.lower() == "running":
            machines[node_name] = machine

    client.close()
    return machines

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
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
        for b in names[i + 1:]:
            lat2, lon2 = coords[b]
            dist = haversine(lat1, lon1, lat2, lon2)
            graph.add_edge(a, b, dist)
    return graph

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload-dir", type=str, help="AAS JSON 파일이 있는 디렉토리")
    parser.add_argument("--mongo-uri", default="mongodb://localhost:27017")
    parser.add_argument("--db", default="test_db")
    parser.add_argument("--collection", default="aas_documents")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level)

    if args.upload_dir:
        num = upload_aas_documents(args.upload_dir, args.mongo_uri, args.db, args.collection)
        logger.info("%d documents uploaded", num)

    machines = load_machines_from_mongo(args.mongo_uri, args.db, args.collection)
    if not machines:
        logger.info("No running machines with valid locations found.")
        return

    by_process: Dict[str, List[Machine]] = {}
    for m in machines.values():
        by_process.setdefault(m.process, []).append(m)

    flow = ["Forging", "Turning", "Milling", "Grinding", "Assembly"]
    selected: List[Machine] = []
    for step in flow:
        candidates = by_process.get(step, [])
        if not candidates:
            continue
        if not selected:
            chosen = candidates[0]
        else:
            prev = selected[-1]
            chosen = min(candidates, key=lambda m: haversine(prev.coords[0], prev.coords[1], m.coords[0], m.coords[1]))
        selected.append(chosen)

    coords = {m.name: m.coords for m in selected}
    graph = build_graph_from_aas(coords)
    total_dist = 0.0
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
            folium.Marker(location=mach.coords, popup=f"{mach.name} ({mach.process}) - {mach.status}").add_to(m)
            if prev:
                folium.PolyLine([prev, mach.coords], color="blue").add_to(m)
            prev = mach.coords
        m.save("process_flow.html")
        logger.info("Saved flow visualisation to 'process_flow.html'.")
    except Exception:
        logger.info("folium not available; skipping visualisation.")

if __name__ == "__main__":
    main()