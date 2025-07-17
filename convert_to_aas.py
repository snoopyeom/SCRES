"""Convert legacy AAS JSON files to a simplified standard structure."""
import argparse
import json
import os
from typing import Dict, Any

# Mapping of Category/Type values to process names
TYPE_PROCESS_MAP = {
    "Hot Former": "Forging",
    "CNC LATHE": "Turning",
    "Vertical Machining Center": "Milling",
    "Horizontal Machining Center": "Milling",
    "Flat surface grinder": "Grinding",
    "Cylindrical grinder": "Grinding",
    "Assembly System": "Assembly",
}

# Common mapping of irregular property names to standard idShorts
PROPERTY_NAME_MAP = {
    "Spindle_motor": "SpindlePower",
    "SpindleMotor": "SpindlePower",
    "SpindleMotorPower": "SpindlePower",
    "Spindle_Speed": "MaxOperatingSpeed",
    "SpindleSpeed": "MaxOperatingSpeed",
    "Travel_distance": "AxisTravel",
    "Swing_overbed": "SwingOverBed",
    "Distance_between_centers": "MaxTurningLength",
}


def _normalize_id_short(name: str) -> str:
    """Convert legacy idShort names to a standardised form."""
    if name in PROPERTY_NAME_MAP:
        return PROPERTY_NAME_MAP[name]
    parts = name.replace("_", " ").split()
    return "".join(p.capitalize() for p in parts)


def _copy_identification(src: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": src.get("id", ""),
        "idType": src.get("idType", "Custom"),
    }


def _convert_category(sm: Dict[str, Any]) -> Dict[str, Any]:
    machine_type = ""
    machine_role = ""
    for elem in sm.get("submodelElements", []):
        sid = elem.get("idShort")
        if sid == "Type":
            machine_type = elem.get("value", "")
        elif sid == "Role":
            machine_role = elem.get("value", "")

    new_elem = [
        {
            "idShort": "MachineType",
            "modelType": "Property",
            "value": machine_type,
            "valueType": "string",
        },
        {
            "idShort": "MachineRole",
            "modelType": "Property",
            "value": machine_role,
            "valueType": "string",
        },
    ]

    return {
        "idShort": "Category",
        "modelType": "Submodel",
        "identification": _copy_identification(sm.get("identification", {})),
        "submodelElements": new_elem,
    }


def _convert_operation(sm: Dict[str, Any]) -> Dict[str, Any]:
    status = ""
    for elem in sm.get("submodelElements", []):
        if elem.get("idShort") == "Machine_Status":
            status = elem.get("value", "")
            break

    new_elem = [
        {
            "idShort": "MachineStatus",
            "modelType": "Property",
            "value": status,
            "valueType": "string",
        },
        {"idShort": "ProcessOrder", "modelType": "Property", "value": 0, "valueType": "integer"},
        {"idShort": "ProcessID", "modelType": "Property", "value": "", "valueType": "string"},
        {"idShort": "ReplacedAASID", "modelType": "Property", "value": "", "valueType": "string"},
        {"idShort": "Candidate", "modelType": "Property", "value": False, "valueType": "boolean"},
        {"idShort": "Selected", "modelType": "Property", "value": False, "valueType": "boolean"},
    ]

    return {
        "idShort": "Operation",
        "modelType": "Submodel",
        "identification": _copy_identification(sm.get("identification", {})),
        "submodelElements": new_elem,
    }


def _convert_nameplate(sm: Dict[str, Any]) -> Dict[str, Any]:
    manufacturer = ""
    address = ""
    for elem in sm.get("submodelElements", []):
        sid = elem.get("idShort")
        if sid in {"Company", "Manufacturer"}:
            manufacturer = elem.get("value", "")
        elif sid in {"Physical_address", "Address"}:
            address = elem.get("value", "")

    # attempt simple address split: Street, CityTown, Country
    parts = [p.strip() for p in address.split(",")]
    street = parts[0] if parts else ""
    city = parts[1] if len(parts) > 1 else ""
    national = parts[2] if len(parts) > 2 else ""

    addr_info = {
        "idShort": "AddressInformation",
        "modelType": "SubmodelElementCollection",
        "value": [
            {"idShort": "Street", "modelType": "MultiLanguageProperty", "value": {"en": street}},
            {"idShort": "Zipcode", "modelType": "MultiLanguageProperty", "value": {"en": ""}},
            {"idShort": "CityTown", "modelType": "MultiLanguageProperty", "value": {"en": city}},
            {"idShort": "NationalCode", "modelType": "MultiLanguageProperty", "value": {"en": national}},
        ],
    }

    new_elem = [
        {"idShort": "URIOfTheProduct", "modelType": "Property", "value": "", "valueType": "string"},
        {
            "idShort": "ManufacturerName",
            "modelType": "MultiLanguageProperty",
            "value": {"en": manufacturer},
        },
        {"idShort": "ManufacturerProductDesignation", "modelType": "MultiLanguageProperty", "value": {"en": ""}},
        addr_info,
        {"idShort": "OrderCodeOfManufacturer", "modelType": "Property", "value": "", "valueType": "string"},
        {"idShort": "SerialNumber", "modelType": "Property", "value": "", "valueType": "string"},
        {"idShort": "YearOfConstruction", "modelType": "Property", "value": "", "valueType": "string"},
    ]

    return {
        "idShort": "Nameplate",
        "modelType": "Submodel",
        "identification": _copy_identification(sm.get("identification", {})),
        "submodelElements": new_elem,
    }


def _convert_technical_data(sm: Dict[str, Any], process: str) -> Dict[str, Any]:
    tech_props = []
    for elem in sm.get("submodelElements", []):
        tech_props.append(
            {
                "idShort": _normalize_id_short(elem.get("idShort", "")),
                "modelType": "Property",
                "value": elem.get("value"),
                "valueType": "string",
            }
        )

    technical_area = {
        "idShort": "TechnicalPropertyAreas",
        "modelType": "SubmodelElementCollection",
        "value": tech_props,
    }

    process_smc = {
        "idShort": process or "Process",
        "modelType": "SubmodelElementCollection",
        "value": [
            {
                "idShort": "GeneralInformation",
                "modelType": "SubmodelElementCollection",
                "value": [
                    {"idShort": "ManufacturerName", "modelType": "Property", "value": "", "valueType": "string"},
                    {"idShort": "ManufacturerProductDesignation", "modelType": "MultiLanguageProperty", "value": {"en": ""}},
                    {"idShort": "ManufacturerArticleNumber", "modelType": "Property", "value": "", "valueType": "string"},
                    {"idShort": "ManufacturerOrderCode", "modelType": "Property", "value": "", "valueType": "string"},
                ],
            },
            technical_area,
        ],
    }

    return {
        "idShort": "TechnicalData",
        "modelType": "Submodel",
        "identification": _copy_identification(sm.get("identification", {})),
        "submodelElements": [process_smc],
    }


def _convert_documentation(sm: Dict[str, Any]) -> Dict[str, Any]:
    documents = []
    for elem in sm.get("submodelElements", []):
        doc = {
            "idShort": "Document",
            "modelType": "SubmodelElementCollection",
            "value": [
                {
                    "idShort": "DocumentId",
                    "modelType": "SubmodelElementCollection",
                    "value": [
                        {"idShort": "DocumentIdentifier", "modelType": "Property", "value": elem.get("idShort"), "valueType": "string"},
                        {"idShort": "DocumentDomainId", "modelType": "Property", "value": "", "valueType": "string"},
                    ],
                },
                {"idShort": "DocumentClassifications", "modelType": "SubmodelElementList", "value": []},
                {
                    "idShort": "DocumentVersions",
                    "modelType": "SubmodelElementList",
                    "value": [
                        {
                            "idShort": "DocumentVersion",
                            "modelType": "SubmodelElementCollection",
                            "value": [
                                {"idShort": "Language", "modelType": "Property", "value": "en", "valueType": "string"},
                                {"idShort": "Version", "modelType": "Property", "value": "", "valueType": "string"},
                                {"idShort": "Title", "modelType": "MultiLanguageProperty", "value": {"en": elem.get("idShort")}},
                                {"idShort": "Description", "modelType": "MultiLanguageProperty", "value": {"en": ""}},
                                {"idShort": "StatusValue", "modelType": "Property", "value": "", "valueType": "string"},
                                {"idShort": "StatusSetDate", "modelType": "Property", "value": "", "valueType": "date"},
                                {"idShort": "OrganizationShortName", "modelType": "Property", "value": "", "valueType": "string"},
                                {"idShort": "OrganizationOfficialName", "modelType": "Property", "value": "", "valueType": "string"},
                                {
                                    "idShort": "DigitalFiles",
                                    "modelType": "SubmodelElementList",
                                    "value": [
                                        {
                                            "idShort": "DigitalFile",
                                            "modelType": "SubmodelElementCollection",
                                            "value": [
                                                {"idShort": "FileFormat", "modelType": "Property", "value": "", "valueType": "string"},
                                                {"idShort": "FileName", "modelType": "Property", "value": elem.get("value"), "valueType": "string"},
                                            ],
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                },
            ],
        }
        documents.append(doc)

    return {
        "idShort": "HandoverDocumentation",
        "modelType": "Submodel",
        "identification": _copy_identification(sm.get("identification", {})),
        "submodelElements": [
            {"idShort": "Documents", "modelType": "SubmodelElementList", "value": documents}
        ],
    }


_CONVERTERS = {
    "Category": _convert_category,
    "Operational_Data": _convert_operation,
    "Nameplate": _convert_nameplate,
    "Documentation": _convert_documentation,
}


def _normalize_modeltypes(obj: Any) -> None:
    """Recursively convert ``modelType`` dicts to plain strings."""
    if isinstance(obj, dict):
        mt = obj.get("modelType")
        if isinstance(mt, dict) and "name" in mt:
            obj["modelType"] = mt["name"]
        for v in obj.values():
            _normalize_modeltypes(v)
    elif isinstance(obj, list):
        for v in obj:
            _normalize_modeltypes(v)


def convert_file(path: str) -> Dict[str, Any]:
    """Convert a legacy AAS JSON file and return the new environment."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    shell = data.get("assetAdministrationShells", [{}])[0]
    new_shell = {
        "idShort": shell.get("idShort", "Shell"),
        "modelType": "AssetAdministrationShell",
        "identification": _copy_identification(shell.get("identification", {})),
        "asset": shell.get("asset", {}),
        "submodels": [],
    }
    new_env = {
        "assetAdministrationShells": [new_shell],
        "submodels": [],
        "assets": data.get("assets", []),
        "conceptDescriptions": [],
    }

    machine_type = None
    for sm in data.get("submodels", []):
        if sm.get("idShort") == "Category":
            for elem in sm.get("submodelElements", []):
                if elem.get("idShort") == "Type":
                    machine_type = elem.get("value")
                    break
            break
    process = TYPE_PROCESS_MAP.get(machine_type, machine_type or "Process")
    for sm in data.get("submodels", []):
        cname = sm.get("idShort")
        conv = _CONVERTERS.get(cname)
        if conv:
            new_sm = conv(sm)
        elif cname == "Technical_Data":
            new_sm = _convert_technical_data(sm, process)
        else:
            continue

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
    _normalize_modeltypes(new_env)
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
            env = convert_file(inp)
        except Exception as e:  # pragma: no cover - convenience script
            print(f"Failed to convert {name}: {e}")
            continue
        with open(outp, "w", encoding="utf-8") as f:
            json.dump(env, f, ensure_ascii=False, indent=2)
        print(f"Converted {name} -> {outp}")


if __name__ == "__main__":
    main()
