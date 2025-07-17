"""Convert legacy AAS JSON files to a simplified standard structure."""
import argparse
import json
import os
from typing import Dict, Any


def _copy_identification(src: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": src.get("id", ""),
        "idType": src.get("idType", "Custom"),
    }


def _convert_category(sm: Dict[str, Any]) -> Dict[str, Any]:
    new_elem = []
    for elem in sm.get("submodelElements", []):
        if elem.get("idShort") == "Type":
            new_elem.append({
                "idShort": "MachineType",
                "modelType": {"name": "Property"},
                "value": elem.get("value"),
                "valueType": "string",
            })
    return {
        "idShort": "Category",
        "modelType": {"name": "Submodel"},
        "identification": _copy_identification(sm.get("identification", {})),
        "submodelElements": new_elem,
    }


def _convert_operation(sm: Dict[str, Any]) -> Dict[str, Any]:
    new_elem = []
    for elem in sm.get("submodelElements", []):
        if elem.get("idShort") == "Machine_Status":
            new_elem.append({
                "idShort": "MachineStatus",
                "modelType": {"name": "Property"},
                "value": elem.get("value"),
                "valueType": "string",
            })
    return {
        "idShort": "Operation",
        "modelType": {"name": "Submodel"},
        "identification": _copy_identification(sm.get("identification", {})),
        "submodelElements": new_elem,
    }


def _convert_nameplate(sm: Dict[str, Any]) -> Dict[str, Any]:
    manufacturer = None
    address = None
    for elem in sm.get("submodelElements", []):
        sid = elem.get("idShort")
        if sid in {"Company", "Manufacturer"}:
            manufacturer = elem.get("value")
        elif sid in {"Physical_address", "Address"}:
            address = elem.get("value")
    addr_info = {
        "idShort": "AddressInformation",
        "modelType": {"name": "SubmodelElementCollection"},
        "value": [
            {
                "idShort": "Street",
                "modelType": {"name": "MultiLanguageProperty"},
                "value": {"en": address or ""},
            }
        ],
    }
    new_elem = [
        {
            "idShort": "ManufacturerName",
            "modelType": {"name": "MultiLanguageProperty"},
            "value": {"en": manufacturer or ""},
        },
        addr_info,
    ]
    return {
        "idShort": "Nameplate",
        "modelType": {"name": "Submodel"},
        "identification": _copy_identification(sm.get("identification", {})),
        "submodelElements": new_elem,
    }


_CONVERTERS = {
    "Category": _convert_category,
    "Operational_Data": _convert_operation,
    "Nameplate": _convert_nameplate,
}


def convert_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    shell = data.get("assetAdministrationShells", [{}])[0]
    new_env = {
        "assetAdministrationShells": [
            {
                "idShort": shell.get("idShort", "Shell"),
                "modelType": {"name": "AssetAdministrationShell"},
                "identification": _copy_identification(shell.get("identification", {})),
                "submodels": [],
            }
        ],
        "submodels": [],
        "assets": data.get("assets", []),
        "conceptDescriptions": [],
    }
    for sm in data.get("submodels", []):
        cname = sm.get("idShort")
        conv = _CONVERTERS.get(cname)
        if conv:
            new_sm = conv(sm)
            new_env["submodels"].append(new_sm)
            new_env["assetAdministrationShells"][0]["submodels"].append({
                "keys": [
                    {
                        "type": "Submodel",
                        "idType": new_sm["identification"]["idType"],
                        "value": new_sm["identification"]["id"],
                        "local": True,
                    }
                ]
            })
    return new_env


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert legacy AAS JSON files")
    parser.add_argument("input_dir", help="Directory with legacy JSON files")
    parser.add_argument("output_dir", help="Directory to write converted files")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    for name in os.listdir(args.input_dir):
        if not name.lower().endswith(".json"):
            continue
        inp = os.path.join(args.input_dir, name)
        outp = os.path.join(args.output_dir, name)
        try:
            new_env = convert_file(inp)
        except Exception as e:  # pragma: no cover - convenience script
            print(f"Failed to convert {name}: {e}")
            continue
        with open(outp, "w", encoding="utf-8") as f:
            json.dump(new_env, f, ensure_ascii=False, indent=2)
        print(f"Converted {name} -> {outp}")


if __name__ == "__main__":
    main()
