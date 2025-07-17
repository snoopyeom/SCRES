"""Convert legacy AAS JSON files using the BaSyx object model."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict

# ``basyx-python-sdk`` is required for this script.  All imports are optional so
# that the file can be parsed even when the library is missing.
try:  # pragma: no cover - basyx might not be installed
    from basyx.aas import model as aas
    from basyx.aas.adapter.json import write_aas_json_file
except Exception:  # pragma: no cover - basyx might not be installed
    aas = None  # type: ignore
    write_aas_json_file = None  # type: ignore


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


def _require_sdk() -> None:
    """Raise ``RuntimeError`` if ``basyx-python-sdk`` is missing."""

    if aas is None or write_aas_json_file is None:
        raise RuntimeError("basyx-python-sdk is required to run this script")


def _ident(data: Dict[str, Any]) -> Any:
    """Return an Identification object from ``data``."""

    if aas is None:  # pragma: no cover - handled in _require_sdk
        return None
    ident = data.get("id", "")
    id_type = data.get("idType", "Custom")
    try:
        # Older versions of the SDK accept keyword arguments
        return aas.Identifier(id=ident, id_type=id_type)
    except TypeError:
        try:
            # Newer releases might require positional arguments
            return aas.Identifier(ident, id_type)
        except TypeError:
            # Fallback for versions where ``Identifier`` is an alias of ``str``
            return aas.Identifier(ident)


def _prop(id_short: str, value: Any, value_type: str = "string") -> Any:
    if aas is None:  # pragma: no cover - handled in _require_sdk
        return None
    return aas.Property(id_short=id_short, value=value, value_type=value_type)


def _mlp(id_short: str, value: str) -> Any:
    if aas is None:  # pragma: no cover - handled in _require_sdk
        return None
    return aas.MultiLanguageProperty(id_short=id_short, value={"en": value})


def _collection(id_short: str, elements: list[Any]) -> Any:
    if aas is None:  # pragma: no cover - handled in _require_sdk
        return None
    col = aas.SubmodelElementCollection(id_short=id_short)
    col.value.extend(elements)
    return col


def _list(id_short: str, elements: list[Any]) -> Any:
    if aas is None:  # pragma: no cover - handled in _require_sdk
        return None
    sel = aas.SubmodelElementList(id_short=id_short)
    sel.value.extend(elements)
    return sel


def _normalize_id_short(name: str) -> str:
    """Convert legacy idShort names to a standardised form."""

    if name in PROPERTY_NAME_MAP:
        return PROPERTY_NAME_MAP[name]
    parts = name.replace("_", " ").split()
    return "".join(p.capitalize() for p in parts)


def _convert_category(sm: Dict[str, Any]) -> Any:
    machine_type = ""
    machine_role = ""
    for elem in sm.get("submodelElements", []):
        sid = elem.get("idShort")
        if sid == "Type":
            machine_type = elem.get("value", "")
        elif sid == "Role":
            machine_role = elem.get("value", "")

    elements = [
        _prop("MachineType", machine_type),
        _prop("MachineRole", machine_role),
    ]
    submodel = aas.Submodel(
        id_short="Category",
        identification=_ident(sm.get("identification", {})),
    )
    submodel.submodel_element.extend(elements)
    return submodel


def _convert_operation(sm: Dict[str, Any]) -> Any:
    status = ""
    for elem in sm.get("submodelElements", []):
        if elem.get("idShort") == "Machine_Status":
            status = elem.get("value", "")
            break

    elements = [
        _prop("MachineStatus", status),
        _prop("ProcessOrder", 0, "integer"),
        _prop("ProcessID", ""),
        _prop("ReplacedAASID", ""),
        _prop("Candidate", False, "boolean"),
        _prop("Selected", False, "boolean"),
    ]
    submodel = aas.Submodel(
        id_short="Operation",
        identification=_ident(sm.get("identification", {})),
    )
    submodel.submodel_element.extend(elements)
    return submodel


def _convert_nameplate(sm: Dict[str, Any]) -> Any:
    manufacturer = ""
    address = ""
    for elem in sm.get("submodelElements", []):
        sid = elem.get("idShort")
        if sid in {"Company", "Manufacturer"}:
            manufacturer = elem.get("value", "")
        elif sid in {"Physical_address", "Address"}:
            address = elem.get("value", "")

    parts = [p.strip() for p in address.split(",")]
    street = parts[0] if parts else ""
    city = parts[1] if len(parts) > 1 else ""
    national = parts[2] if len(parts) > 2 else ""

    addr_info = _collection(
        "AddressInformation",
        [
            _mlp("Street", street),
            _mlp("Zipcode", ""),
            _mlp("CityTown", city),
            _mlp("NationalCode", national),
        ],
    )

    elements = [
        _prop("URIOfTheProduct", ""),
        _mlp("ManufacturerName", manufacturer),
        _mlp("ManufacturerProductDesignation", ""),
        addr_info,
        _prop("OrderCodeOfManufacturer", ""),
        _prop("SerialNumber", ""),
        _prop("YearOfConstruction", ""),
    ]
    submodel = aas.Submodel(
        id_short="Nameplate",
        identification=_ident(sm.get("identification", {})),
    )
    submodel.submodel_element.extend(elements)
    return submodel


def _convert_technical_data(sm: Dict[str, Any], process: str) -> Any:
    tech_props = []
    for elem in sm.get("submodelElements", []):
        tech_props.append(
            _prop(_normalize_id_short(elem.get("idShort", "")), elem.get("value"))
        )

    technical_area = _collection("TechnicalPropertyAreas", tech_props)
    general_info = _collection(
        "GeneralInformation",
        [
            _prop("ManufacturerName", ""),
            _mlp("ManufacturerProductDesignation", ""),
            _prop("ManufacturerArticleNumber", ""),
            _prop("ManufacturerOrderCode", ""),
        ],
    )
    process_smc = _collection(process or "Process", [general_info, technical_area])
    submodel = aas.Submodel(
        id_short="TechnicalData",
        identification=_ident(sm.get("identification", {})),
    )
    submodel.submodel_element.append(process_smc)
    return submodel


def _convert_documentation(sm: Dict[str, Any]) -> Any:
    documents = []
    for elem in sm.get("submodelElements", []):
        digital_file = _collection(
            "DigitalFile",
            [_prop("FileFormat", ""), _prop("FileName", elem.get("value"))],
        )
        doc_version = _collection(
            "DocumentVersion",
            [
                _prop("Language", "en"),
                _prop("Version", ""),
                _mlp("Title", elem.get("idShort")),
                _mlp("Description", ""),
                _prop("StatusValue", ""),
                _prop("StatusSetDate", "", "date"),
                _prop("OrganizationShortName", ""),
                _prop("OrganizationOfficialName", ""),
                _list("DigitalFiles", [digital_file]),
            ],
        )
        versions = _list("DocumentVersions", [doc_version])
        doc = _collection(
            "Document",
            [
                _collection(
                    "DocumentId",
                    [
                        _prop("DocumentIdentifier", elem.get("idShort")),
                        _prop("DocumentDomainId", ""),
                    ],
                ),
                _list("DocumentClassifications", []),
                versions,
            ],
        )
        documents.append(doc)

    docs_list = _list("Documents", documents)
    submodel = aas.Submodel(
        id_short="HandoverDocumentation",
        identification=_ident(sm.get("identification", {})),
    )
    submodel.submodel_element.append(docs_list)
    return submodel


_CONVERTERS = {
    "Category": _convert_category,
    "Operational_Data": _convert_operation,
    "Nameplate": _convert_nameplate,
    "Documentation": _convert_documentation,
}


def convert_file(path: str) -> Any:
    """Convert a legacy AAS JSON file and return the new environment."""

    _require_sdk()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    shell_data = data.get("assetAdministrationShells", [{}])[0]
    shell = aas.AssetAdministrationShell(
        id_short=shell_data.get("idShort", "Shell"),
        identification=_ident(shell_data.get("identification", {})),
        asset=shell_data.get("asset", {}),
    )

    env = aas.AssetAdministrationShellEnvironment(
        assetAdministrationShells=[shell],
        submodels=[],
        assets=data.get("assets", []),
        conceptDescriptions=[],
    )

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

        env.submodels.append(new_sm)
        shell.submodel.append(
            aas.ModelReference(
                [
                    aas.Key(
                        type=aas.KeyTypes.SUBMODEL,
                        id_type=new_sm.identification.id_type,
                        value=new_sm.identification.id,
                        local=True,
                    )
                ]
            )
        )
    return env


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert legacy AAS JSON files using basyx-python-sdk"
    )
    parser.add_argument("input_dir", help="Directory with legacy JSON files")
    parser.add_argument("output_dir", help="Directory to write converted files")
    args = parser.parse_args()

    _require_sdk()
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
            write_aas_json_file(f, env)
        print(f"Converted {name} -> {outp}")


if __name__ == "__main__":
    main()
