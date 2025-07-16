"""Quickly inspect AAS JSON files for semantic IDs and status values."""
import argparse
import json
import os

IRDI_PROCESS_MAP = {
    "0173-1#01-AKJ741#017": "Turning",
    "0173-1#01-AKJ783#017": "Milling",
    "0173-1#01-AKJ867#017": "Grinding",
}


def _find_status(elements):
    """Recursively search submodel elements for a status value."""
    for elem in elements:
        id_short = elem.get("idShort", "").lower()
        if "status" in id_short:
            return elem.get("value")
        if isinstance(elem.get("submodelElements"), list):
            status = _find_status(elem["submodelElements"])
            if status:
                return status
    return None


def main(directory: str) -> None:
    for filename in os.listdir(directory):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(directory, filename)
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:  # pragma: no cover - convenience script
            print(f"[❌] {filename} - JSON 로딩 실패: {e}")
            continue

        semantic_ids = []
        statuses = []

        for submodel in data.get("submodels", []):
            sem_keys = submodel.get("semanticId", {}).get("keys", [])
            if sem_keys:
                semantic_ids.append(sem_keys[0].get("value", ""))

            status = _find_status(submodel.get("submodelElements", []))
            if status:
                statuses.append(status)

        print(f"\n📂 {filename}")
        print(f"  - Semantic ID(s): {semantic_ids}")
        print(f"  - Status: {statuses}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect AAS JSON files")
    parser.add_argument(
        "directory",
        nargs="?",
        default=r"C:\\Users\\JeongHoon\\SCRES\\설비 json 파일",
        help="Path to directory containing AAS JSON files",
    )
    args = parser.parse_args()
    main(args.directory)
