"""Export AASX package from a normalised AAS JSON file using basyx-python-sdk."""
import argparse
import sys

try:
    from basyx.aas.adapter.json import read_aas_json_file
    from basyx.aas.adapter.aasx import write_aasx
except Exception:  # pragma: no cover - basyx may not be installed
    read_aas_json_file = None  # type: ignore
    write_aasx = None  # type: ignore


def export_aasx(input_json: str, output_aasx: str) -> None:
    if read_aas_json_file is None or write_aasx is None:
        raise RuntimeError(
            "basyx-python-sdk is required to run this script"
        )
    with open(input_json, "r", encoding="utf-8") as f:
        env = read_aas_json_file(f)
    with open(output_aasx, "wb") as f:
        write_aasx(f, env)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load a normalised AAS JSON file and export it as an .aasx package"
    )
    parser.add_argument("input_json", help="Path to input AAS JSON file")
    parser.add_argument("output_aasx", help="Path of the output .aasx package")
    args = parser.parse_args()

    export_aasx(args.input_json, args.output_aasx)
    print(f"Wrote {args.output_aasx}")


if __name__ == "__main__":
    main()
