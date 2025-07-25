# SCRES A* Demo

This repository demonstrates a simple A* search implementation. The original
notebook `A star algorithm.ipynb` has been replaced by `astar_demo.py` which is
fully runnable from the command line.

``astar_demo.py`` optionally loads Asset Administration Shell (AAS) JSON files
from the given directory when the bundled BaSyx SDK is available. The loaded
AAS `idShort` values and their submodel names are printed before running the
search.

To execute the demo with the default AAS directory:

```bash
python astar_demo.py
```

You may specify an alternate directory with `--aas-dir`:

```bash
python astar_demo.py --aas-dir "path/to/aas/files"
```

The script prints the discovered path length and visualises the route using a
small ASCII grid.

``aas_pathfinder.py`` can load the same directory of AAS JSON files to select
machines for each manufacturing step.  It determines the machine's process by
reading the ``Type`` property inside the ``Category`` submodel, mapping values
such as ``"Hot Former"`` or ``"CNC LATHE"`` to steps like Forging or Turning.
This approach is more reliable than depending on IRDI codes.

## Converting legacy AAS files

`convert_to_aas.py` converts the irregular JSON files found in `설비 json 파일/` to a simplified structure that matches the normalised AAS layout.  The tool relies on the BaSyx SDK bundled in the `sdk/` directory to write the JSON output.

```bash
python convert_to_aas.py "설비 json 파일" converted
```

Converted files will be written to the specified output directory.

`convert_to_aas.py` automatically generates a fallback identifier for any
AAS or Submodel that is missing an `id`. The fallback is derived from the file
name, so each converted file receives deterministic IDs without manual edits.

## Building AAS with BaSyx

`export_aasx.py` (not included here) demonstrates how to load the normalised JSON files
produced by `convert_to_aas.py` and export them as an `.aasx` package using the
bundled BaSyx SDK.

The resulting `example.aasx` can be opened in any compliant AAS tool.
