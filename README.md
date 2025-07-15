# SCRES A* Demo

This repository demonstrates a simple A* search implementation. The original
notebook `A star algorithm.ipynb` has been replaced by `astar_demo.py` which is
fully runnable from the command line.

``astar_demo.py`` optionally loads Asset Administration Shell (AAS) JSON files
from the given directory when the `basyx-python-sdk` is installed.  The loaded
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
