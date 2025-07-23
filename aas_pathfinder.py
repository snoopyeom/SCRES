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
from typing import Optional, Dict, Any
logger = logging.getLogger("__main__")

try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderServiceError
except Exception:
    Nominatim = None
    GeocoderServiceError = Exception

# 주소 → 위도/경도 변환 함수
def geocode_address(address: str):
    geolocator = Nominatim(user_agent="aas_locator")
    try:
        location = geolocator.geocode(address)
        if location:
            return (location.latitude, location.longitude)
    except:
        pass
    return None

# 공정 매핑 테이블
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
    "그라인더": "Grinding",
}

@dataclass
class Machine:
    name: str
    process: str
    coords: Tuple[float, float]
    status: str
    data: Optional[Dict[str, Any]] = None  # ← 이 줄 추가

# ────────────────────────────────────────────────────────────────
# AAS 문서 업로드 함수 추가
def upload_aas_documents(upload_dir: str, mongo_uri: str, db_name: str, collection_name: str) -> int:
    """Upload all ``.json`` files in ``upload_dir`` to MongoDB.

    The raw JSON string is kept alongside the parsed object so files with
    unconventional keys remain intact.
    """

    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]

    uploaded = 0
    for filename in os.listdir(upload_dir):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(upload_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
            try:
                content = json.loads(raw)
            except json.JSONDecodeError as exc:
                logger.warning("⚠️ %s JSON 파싱 실패: %s", filename, exc)
                continue

            collection.replace_one(
                {"filename": filename},
                {"filename": filename, "json": content, "raw": raw},
                upsert=True,
            )
            uploaded += 1
        except Exception as e:  # pragma: no cover - unexpected errors
            logger.warning("⚠️ %s 업로드 실패: %s", filename, str(e))

    logger.info("✅ 총 %d개 문서 업로드 완료", uploaded)
    return uploaded


# ────────────────────────────────────────────────────────────────

def _find_address(elements, depth=0):
    prefix = "  " * depth

    for elem in elements:
        id_short = elem.get("idShort", "").lower()
        print(f"{prefix}🔍 [depth {depth}] 탐색 중 idShort: {id_short}")

        if id_short == "addressinformation":
            value_list = elem.get("value", [])
            if isinstance(value_list, list):
                for item in value_list:
                    sub_id = item.get("idShort", "").lower()
                    if sub_id == "street":
                        sub_val = item.get("value")
                        print(f"{prefix}    🏡 Street 값: {sub_val}")
                        if isinstance(sub_val, list):
                            for s in sub_val:
                                if isinstance(s, dict) and "text" in s:
                                    print(f"{prefix}    ✅ Street → text: {s['text']}")
                                    return s["text"]

        if isinstance(elem.get("submodelElements"), list):
            print(f"{prefix}↘️ 재귀 진입: {id_short}")
            addr = _find_address(elem["submodelElements"], depth + 1)
            if addr:
                return addr

    print(f"{prefix}⛔ [depth {depth}] 주소 미발견 종료")
    return None




def explore_address_structure(elements, depth=0):
    prefix = "  " * depth
    for elem in elements:
        id_short = elem.get("idShort", "")
        print(f"{prefix}🔎 idShort: {id_short}")
        if "value" in elem:
            val = elem["value"]
            print(f"{prefix}📦 value type: {type(val)}, value: {val}")
        if "submodelElements" in elem:
            print(f"{prefix}🔁 재귀 진입 → {id_short}")
            explore_address_structure(elem["submodelElements"], depth + 1)






def _find_name(elements):
    for elem in elements:
        if elem.get("idShort") in ["MachineName", "Name"]:
            val = elem.get("value")
            if isinstance(val, str):
                return val
            if isinstance(val, list) and isinstance(val[0], dict):
                return val[0].get("text")
        if isinstance(elem.get("submodelElements"), list):
            name = _find_name(elem["submodelElements"])
            if name:
                return name
    return None

def _find_process(elements):
    for elem in elements:
        if elem.get("idShort") == "MachineType":
            val = elem.get("value")
            if isinstance(val, str):
                proc = TYPE_PROCESS_MAP.get(val)
                if proc:
                    return proc
        if elem.get("idShort") == "ProcessId":
            val = elem.get("value")
            if isinstance(val, str):
                proc = IRDI_PROCESS_MAP.get(val)
                if proc:
                    return proc
        if isinstance(elem.get("submodelElements"), list):
            proc = _find_process(elem["submodelElements"])
            if proc:
                return proc
    return "Unknown"

# ────────────────────────────────────────────────────────────────

def load_machines_from_mongo(mongo_uri, db_name, collection_name, verbose=False):
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]
    machines = {}

    for doc in collection.find():
        aas = doc.get("json", {})
        shells = aas.get("assetAdministrationShells", [])
        if not shells:
            continue
        shell = shells[0]

        name = shell.get("idShort", "Unnamed")
        asset_info = shell.get("assetInformation", {})
        status = asset_info.get("defaultThumbnail", {}).get("status", "unknown")
        process = TYPE_PROCESS_MAP.get(name, "Unknown")

        # 디버깅 로그
        if verbose:
            print(f"[DEBUG] submodel 참조: {shell.get('submodels')}")
            for sm in aas.get("submodels", []):
                print(f"[DEBUG] 실제 submodel idShort: {sm.get('idShort')}")

        addr = None
        for ref in shell.get("submodels", []):
            ref_id = None
            keys = ref.get("keys", [])
            for k in keys:
                if k.get("type") == "Submodel":
                    ref_id = k.get("value", "").split("/")[-1]
                    break

            if not ref_id:
                continue

            for submodel in aas.get("submodels", []):
                if submodel.get("idShort") == ref_id:
                    addr = _find_address(submodel.get("submodelElements", []))
                    if addr:
                        break
            if addr:
                break

        coords = geocode_address(addr) if addr else None
        if coords:
            # ⬇️ data 필드에 전체 AAS JSON 저장
            machines[name] = Machine(
                name=name,
                process=process,
                coords=coords,
                status=status,
                data=aas  # 전체 AAS JSON을 data로 저장
            )

    return machines




# ────────────────────────────────────────────────────────────────

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

# ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload-dir", type=str)
    parser.add_argument("--mongo-uri", default="mongodb://localhost:27017")
    parser.add_argument("--db", default="test_db")
    parser.add_argument("--collection", default="aas_documents")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--explore-address", action="store_true", help="주소 구조만 탐색하고 종료")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level)

    # ✅ explore-address가 켜져 있으면 여기서 바로 처리하고 종료
    if args.explore_address:
        client = MongoClient(args.mongo_uri)
        db = client[args.db]
        collection = db[args.collection]
        for doc in collection.find().limit(1):
            shell = doc.get("json", {}).get("assetAdministrationShells", [])[0]
            for ref in shell.get("submodels", []):
                submodel_id = ref.get("idShort")
                print(f"🔍 서브모델: {submodel_id}")
                for submodel in doc["json"].get("submodels", []):
                    if submodel.get("idShort") == submodel_id:
                        print(f"✅ {submodel_id} 구조 탐색 시작")
                        explore_address_structure(submodel.get("submodelElements", []))
                        break
        return  # ✅ 탐색만 하고 프로그램 종료

    if args.upload_dir:
        num = upload_aas_documents(args.upload_dir, args.mongo_uri, args.db, args.collection)
        logger.info("%d documents uploaded", num)

    machines = load_machines_from_mongo(args.mongo_uri, args.db, args.collection, verbose=args.verbose)

    # ✅ 구조 확인용: 첫 machine의 원본 AAS JSON 구조를 출력
    if machines:
        import json
        sample = list(machines.values())[0]
        logger.info("🔍 샘플 장비: %s (%s)", sample.name, sample.process)
        print("📂 전체 AAS 구조 (주소 파싱 디버깅용):")
        print(json.dumps(sample.data, indent=2))
    else:
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
