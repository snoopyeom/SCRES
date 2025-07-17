from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict

# Optional import for basyx SDK
try:
    from basyx.aas import model as aas
    from basyx.aas.environment import AssetAdministrationShellEnvironment
    from basyx.aas.adapter.json import write_aas_json_file
    print("[✅ SDK import 성공]")
except Exception as e:
    print(f"[❌ SDK import 실패] {e!r}")
    aas = None
    write_aas_json_file = None

import importlib.util
print(importlib.util.find_spec("basyx"))

# ── convert_to_aas.py 상단 ──

import logging
logger = logging.getLogger("AAS_Converter")

# Optional import for basyx SDK
try:
    from basyx.aas import model as aas
    # environment 클래스 여러 위치에서 시도 import
    try:
        from basyx.aas.environment import AssetAdministrationShellEnvironment
        logger.info("✅ imported AssetAdministrationShellEnvironment from basyx.aas.environment")
    except ImportError:
        try:
            from basyx.aas.model.environment import AssetAdministrationShellEnvironment
            logger.info("✅ imported AssetAdministrationShellEnvironment from basyx.aas.model.environment")
        except ImportError as e:
            logger.error(f"❌ AssetAdministrationShellEnvironment import 실패: {e!r}")
            AssetAdministrationShellEnvironment = None  # fallback
    # JSON 어댑터 import
    try:
        from basyx.aas.adapter.json import write_aas_json_file
        logger.info("✅ imported write_aas_json_file")
    except ImportError:
        logger.error("❌ write_aas_json_file import 실패")
        write_aas_json_file = None

    logger.info("✅ basyx SDK import 성공")
except Exception as e:
    logger.error(f"❌ basyx SDK 전체 import 실패: {e!r}")
    aas = None
    AssetAdministrationShellEnvironment = None
    write_aas_json_file = None

def _require_sdk() -> None:
    if aas is None or write_aas_json_file is None or AssetAdministrationShellEnvironment is None:
        raise RuntimeError("basyx-python-sdk의 필요한 모듈을 찾을 수 없습니다.")


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


import uuid
import logging

# 🔧 로그 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AAS_Converter")

def _create(cls, *args, id_=None, id_short=None, identification=None, **kwargs):
    # identification을 id_로 보정
    if identification is not None and not id_:
        id_ = identification

    # 🚨 문제 로그: id_가 비어있거나 None일 경우 경고 출력
    if not id_ or str(id_).strip() == "":
        fallback_id = f"auto-id--{uuid.uuid4()}"
        logger.warning(
            f"[ID Fallback] 클래스: {cls.__name__} | 원래 ID가 비어있어 자동 생성된 ID 사용: {fallback_id}"
        )
        id_ = fallback_id

    # 🔧 AssetAdministrationShell 특수 처리
    if cls.__name__ == "AssetAdministrationShell":
        if "asset_information" not in kwargs:
            raise ValueError("AssetAdministrationShell requires asset_information argument.")
        return cls(
            asset_information=kwargs["asset_information"],
            id_=id_,
            id_short=id_short,
            display_name=kwargs.get("display_name"),
            category=kwargs.get("category"),
            description=kwargs.get("description"),
            administration=kwargs.get("administration"),
            submodel=kwargs.get("submodel"),
            derived_from=kwargs.get("derived_from"),
            embedded_data_specifications=kwargs.get("embedded_data_specifications", ()),
            extension=kwargs.get("extension", ()),
        )

    # 🔧 AssetInformation 특수 처리
    if cls.__name__ == "AssetInformation":
        return cls(
            asset_kind=kwargs.get("asset_kind"),
            global_asset_id=kwargs.get("global_asset_id"),
            specific_asset_id=kwargs.get("specific_asset_id", ()),
            asset_type=kwargs.get("asset_type"),
            default_thumbnail=kwargs.get("default_thumbnail"),
        )

    # ✅ 일반 클래스 생성
    try:
        return cls(id_=id_, id_short=id_short, *args, **kwargs)
    except TypeError as e:
        logger.warning(
            f"[TypeError] 클래스 생성 실패 시도: {cls.__name__} | ID: {id_} | 오류: {e}"
        )
        return cls(*args, **kwargs)




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

    # 파일 로드 → data에 JSON 할당
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        data, _ = decoder.raw_decode(text)

    # 여기서 data가 정의됐으니 리스트 초기화
    submodels_list: list[Any] = []
    concepts_list: list[Any] = []

    shell_data = data.get("assetAdministrationShells", [{}])[0]
    # … identification, shell 생성 로직 …

    # Submodel 변환
    for sm in data.get("submodels", []):
        conv = _CONVERTERS.get(sm.get("idShort"))
        if not conv and sm.get("idShort") != "Technical_Data":
            continue
        new_sm = conv(sm, process=process, fallback_prefix=prefix)
        submodels_list.append(new_sm)
        shell.submodel.append(
            aas.ModelReference([ ... ])
        )

    # ConceptDescription 변환 (필요 시)
    for cd in data.get("conceptDescriptions", []):
        # conv_cd = ...
        # concepts_list.append(conv_cd)
        pass

    # 이제 안전하게 environment 생성
    if AssetAdministrationShellEnvironment is None:
        raise RuntimeError("Environment 클래스가 없어서 중단합니다.")
    env = AssetAdministrationShellEnvironment(
        asset_administration_shells=[shell],
        submodels=submodels_list,
        concept_descriptions=concepts_list,
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
