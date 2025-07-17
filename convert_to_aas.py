from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict

# Optional import for basyx SDK
try:
    from basyx.aas import model as aas
    from basyx.aas.adapter.json import write_aas_json_file
except Exception:
    aas = None  # type: ignore
    write_aas_json_file = None  # type: ignore

# Mapping for category/type to process names
TYPE_PROCESS_MAP = {
    "Hot Former": "Forging",
    "CNC LATHE": "Turning",
    "Vertical Machining Center": "Milling",
    "Horizontal Machining Center": "Milling",
    "Flat surface grinder": "Grinding",
    "Cylindrical grinder": "Grinding",
    "Assembly System": "Assembly",
}

# Property name normalization map
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
    """Raise error if basyx SDK is missing."""
    if aas is None or write_aas_json_file is None:
        raise RuntimeError("basyx-python-sdk is required to run this script")


def _ident(data: Any, fallback_id: str = "http://example.com/dummy-id") -> Any:
    if aas is None:
        return None
    # 디버깅: 타입 체크
    if isinstance(data, dict):
        ident = str(data.get("id", "")).strip()
        id_type = data.get("idType", "Custom")
    else:
        if isinstance(data, str):
            print(f"WARNING: _ident called with string: {data!r}")
            ident = data.strip()
            id_type = "Custom"
        else:
            print(f"WARNING: _ident called with non-dict/non-str: {type(data)} {data!r}")
            ident = str(data)
            id_type = "Custom"
    if not ident:
        ident = fallback_id
    ident = ident.replace(" ", "_")
    if not ident:
        ident = fallback_id
    try:
        return aas.Identifier(id=ident, id_type=id_type)
    except TypeError:
        # Identifier might be a simple string alias or support a
        # different constructor.  Fallback to the most permissive option.
        try:
            return aas.Identifier(ident)
        except Exception:
            return ident


def _create(cls: Any, /, *args: Any, **kwargs: Any) -> Any:
    print(f"[DEBUG] _create called: cls={cls!r}, args={args!r}, kwargs={kwargs!r}")
    if aas is None:
        return None

    if isinstance(cls, str):
        print(f"ERROR: _create called with str as cls: {cls!r}")
        raise TypeError(f"Invalid class passed to _create(): {cls!r}")
    if not hasattr(cls, "__call__"):
        print(f"ERROR: _create called with non-callable cls: {cls!r}")
        raise TypeError(f"Invalid class passed to _create(): {cls!r}")

    ident = kwargs.pop("identification", None)
    fallback_id = "http://example.com/fallback-id"

    # ident 보정
    if ident is not None and not hasattr(ident, "id"):
        print(f"WARNING: ident is not Identifier, got {type(ident)}: {ident!r}. Wrapping as Identifier.")
        try:
            ident = aas.Identifier(id=str(ident), id_type="Custom")
        except TypeError:
            ident = str(ident)

    id_value = kwargs.pop("id_", None)
    if hasattr(ident, "id"):
        id_value = ident.id
    print(f"[DEBUG] ident type: {type(ident)}, ident: {ident!r}")
    print(f"[DEBUG] id_value: {id_value!r}")

    if not id_value:
        id_value = fallback_id

    # cls가 id 인자를 받는지 체크
    accepts_id_kwarg = hasattr(cls, "__init__") and "id" in cls.__init__.__code__.co_varnames
    if accepts_id_kwarg:
        kwargs["id"] = id_value

    try:
        if ident is not None:
            return cls(*args, identification=ident, **kwargs)
        return cls(*args, **kwargs)
    except TypeError as e:
        print(f"TypeError on _create({cls}, args={args}, kwargs={kwargs}): {e}")
        import traceback
        traceback.print_exc()
        obj = cls(*args, **kwargs)
        if ident is not None:
            if hasattr(obj, "identification"):
                setattr(obj, "identification", ident)
            elif hasattr(obj, "id"):
                try:
                    setattr(obj, "id", ident.id)
                except Exception:
                    setattr(obj, "id", ident)
        return obj


def _prop(id_short: str, value: Any, value_type: str = "string") -> Any:
    if aas is None:
        return None
    return aas.Property(id_short=id_short, value=value, value_type=value_type)


def _mlp(id_short: str, value: str) -> Any:
    if aas is None:
        return None
    return aas.MultiLanguageProperty(id_short=id_short, value={"en": value})


def _collection(id_short: str, elements: list[Any]) -> Any:
    if aas is None:
        return None
    col = aas.SubmodelElementCollection(id_short=id_short)
    col.value.extend(elements)
    return col


def _list(id_short: str, elements: list[Any]) -> Any:
    if aas is None:
        return None
    sel = aas.SubmodelElementList(id_short=id_short)
    sel.value.extend(elements)
    return sel


def _normalize_id_short(name: str) -> str:
    if name in PROPERTY_NAME_MAP:
        return PROPERTY_NAME_MAP[name]
    parts = name.replace("_", " ").split()
    return "".join(p.capitalize() for p in parts)


def _convert_category(sm: Dict[str, Any], *, fallback_prefix: str) -> Any:
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
    ident = _ident(
        sm.get("identification", {}),
        fallback_id=f"{fallback_prefix}/Category",
    )
    submodel = _create(
        aas.Submodel,
        id_=getattr(ident, "id", None),
        id_short="Category",
        identification=ident,
    )
    submodel.submodel_element.extend(elements)
    return submodel


def _convert_operation(sm: Dict[str, Any], *, fallback_prefix: str) -> Any:
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
    ident = _ident(
        sm.get("identification", {}),
        fallback_id=f"{fallback_prefix}/Operation",
    )
    submodel = _create(
        aas.Submodel,
        id_=getattr(ident, "id", None),
        id_short="Operation",
        identification=ident,
    )
    submodel.submodel_element.extend(elements)
    return submodel


def _convert_nameplate(sm: Dict[str, Any], *, fallback_prefix: str) -> Any:
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
    ident = _ident(
        sm.get("identification", {}),
        fallback_id=f"{fallback_prefix}/Nameplate",
    )
    submodel = _create(
        aas.Submodel,
        id_=getattr(ident, "id", None),
        id_short="Nameplate",
        identification=ident,
    )
    submodel.submodel_element.extend(elements)
    return submodel


def _convert_technical_data(sm: Dict[str, Any], process: str, *, fallback_prefix: str) -> Any:
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
    ident = _ident(
        sm.get("identification", {}),
        fallback_id=f"{fallback_prefix}/TechnicalData",
    )
    submodel = _create(
        aas.Submodel,
        id_=getattr(ident, "id", None),
        id_short="TechnicalData",
        identification=ident,
    )
    submodel.submodel_element.append(process_smc)
    return submodel


def _convert_documentation(sm: Dict[str, Any], *, fallback_prefix: str) -> Any:
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
    ident = _ident(
        sm.get("identification", {}),
        fallback_id=f"{fallback_prefix}/HandoverDocumentation",
    )
    submodel = _create(
        aas.Submodel,
        id_=getattr(ident, "id", None),
        id_short="HandoverDocumentation",
        identification=ident,
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
    _require_sdk()
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        data, _ = decoder.raw_decode(text)

    shell_data = data.get("assetAdministrationShells", [{}])[0]

    # fallback ID 생성 (파일 이름 기반으로)
    base_name = os.path.splitext(os.path.basename(path))[0].replace(" ", "_")
    fallback_id = f"http://example.com/{base_name}"
    prefix = fallback_id

    # identification 객체 생성
    ident = _ident(shell_data.get("identification", {}), fallback_id=fallback_id)
    id_ = getattr(ident, "id", "") if ident else ""

    # 안전한 assetInformation 생성
    asset_info = aas.AssetInformation(
        asset_kind=aas.AssetKind.INSTANCE,
        global_asset_id="http://example.com/dummy-asset"
    )

    # AAS 객체 생성
    shell = _create(
        aas.AssetAdministrationShell,
        id_=id_,
        id_short=shell_data.get("idShort", "Shell"),
        identification=ident,
        asset_information=asset_info
    )

    # AAS 환경 생성
    env = aas.AssetAdministrationShellEnvironment(
        assetAdministrationShells=[shell],
        submodels=[],
        assets=data.get("assets", []),
        conceptDescriptions=[],
    )

    # 기계 타입 → 공정명 추출
    machine_type = None
    for sm in data.get("submodels", []):
        if sm.get("idShort") == "Category":
            for elem in sm.get("submodelElements", []):
                if elem.get("idShort") == "Type":
                    machine_type = elem.get("value")
                    break
            break
    process = TYPE_PROCESS_MAP.get(machine_type, machine_type or "Process")

    # Submodel 변환 처리
    for sm in data.get("submodels", []):
        cname = sm.get("idShort")
        conv = _CONVERTERS.get(cname)
        if conv:
            new_sm = conv(sm, fallback_prefix=prefix)
        elif cname == "Technical_Data":
            new_sm = _convert_technical_data(sm, process, fallback_prefix=prefix)
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
        except Exception as e:
            print(f"Failed to convert {name}: {e}")
            import traceback
            traceback.print_exc()
            continue
        with open(outp, "w", encoding="utf-8") as f:
            write_aas_json_file(f, env)
        print(f"Converted {name} -> {outp}")


if __name__ == "__main__":
    main()
