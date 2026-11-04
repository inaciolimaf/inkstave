#!/usr/bin/env python3
"""Writes the LaTeX package names that the editor's `\\usepackage` completion offers (spec 112).

The list is the union of the Tectonic prewarm set in `infra/tectonic/packages.toml` and the curated
names below, so a package a deployer prewarms is offered without a code change. Run it after editing either
source:

    python3 scripts/build_completion_packages.py
"""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TECTONIC = ROOT / "infra" / "tectonic" / "packages.toml"
OUTPUT = ROOT / "frontend" / "src" / "modules" / "editor" / "completion" / "data" / "packages.json"

# Packages a writer reaches for: maths, graphics, tables, bibliography, layout, fonts, drawing, lists, code.
# Packages that need shell escape (minted) are left out: Tectonic cannot run them.
CURATED = [
    "abstract",
    "afterpage",
    "algorithm2e",
    "algorithmic",
    "appendix",
    "array",
    "babel",
    "babel-french",
    "babel-german",
    "bbm",
    "bm",
    "bookmark",
    "booktabs",
    "cancel",
    "changepage",
    "chemfig",
    "circuitikz",
    "cleveref",
    "colortbl",
    "csquotes",
    "csvsimple",
    "datatool",
    "dirtree",
    "doi",
    "emptypage",
    "enumitem",
    "epigraph",
    "esvect",
    "etoolbox",
    "eurosym",
    "expl3",
    "fancyhdr",
    "fancyvrb",
    "float",
    "fontenc",
    "fontspec",
    "fp",
    "forest",
    "geometry",
    "gensymb",
    "graphicx",
    "hycolor",
    "hyperref",
    "ifthen",
    "inputenc",
    "lipsum",
    "listings",
    "longtable",
    "lmodern",
    "makecell",
    "marvosym",
    "mathtools",
    "mdframed",
    "mhchem",
    "microtype",
    "morefloats",
    "multicol",
    "multirow",
    "natbib",
    "nicefrac",
    "orcidlink",
    "parskip",
    "pdflscape",
    "pdfpages",
    "pgf",
    "pgffor",
    "pgfplots",
    "pgfplotstable",
    "pifont",
    "placeins",
    "polyglossia",
    "qtree",
    "ragged2e",
    "rotating",
    "setspace",
    "siunitx",
    "soul",
    "stmaryrd",
    "subcaption",
    "subfiles",
    "tabularx",
    "tcolorbox",
    "textcomp",
    "threeparttable",
    "tikz",
    "tikz-cd",
    "tocloft",
    "titlesec",
    "titletoc",
    "todonotes",
    "trimspaces",
    "ulem",
    "units",
    "unicode-math",
    "upgreek",
    "url",
    "varioref",
    "wasysym",
    "wrapfig",
    "xcolor",
    "xltxtra",
    "xparse",
    "xstring",
    "xurl",
    "amsfonts",
    "amsmath",
    "amssymb",
    "amsthm",
    "beamer",
    "biblatex",
    "adjustbox",
    "latexsym",
]


def main() -> None:
    settings = tomllib.loads(TECTONIC.read_text(encoding="utf-8"))
    names = sorted(set(CURATED) | set(settings["packages"]["prewarm"]))
    OUTPUT.write_text(json.dumps(names, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{OUTPUT.relative_to(ROOT)}: {len(names)} packages")


if __name__ == "__main__":
    main()
