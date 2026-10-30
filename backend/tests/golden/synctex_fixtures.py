"""Hand-written SyncTeX fixtures with known coordinates (spec 26 tests).

All coordinates are scaled points (sp); divide by 65536 for PDF points. The
values below are chosen so the expected points are round numbers:

    6553600 sp  -> 100 pt        13107200 sp -> 200 pt
    26214400 sp -> 400 pt          655360 sp ->  10 pt
      131072 sp ->   2 pt        39321600 sp -> 600 pt   50331648 sp -> 768 pt
"""

from __future__ import annotations

import gzip

# Single-file, 2-page document. Line 10 -> page 1 @ v=200pt; line 20 -> page 1
# @ v=400pt; line 30 -> page 2 @ v=200pt.
SINGLE_FILE = """SyncTeX Version:1
Input:1:main.tex
Magnification:1000
Unit:1
X Offset:0
Y Offset:0
Content:
{1
[1,1:0,0:39321600,50331648,0
(1,10:6553600,13107200:26214400,655360,131072
x1,10:6553600,13107200
)
(1,20:6553600,26214400:26214400,655360,131072
x1,20:6553600,26214400
)
]
}
{2
[1,30:0,0:39321600,50331648,0
(1,30:6553600,13107200:26214400,655360,131072
x1,30:6553600,13107200
)
]
}
Postamble:
"""

# Multi-file document: \\input{sections/intro.tex}. Tag 2 region on page 1 at
# v=400pt maps back to "sections/intro.tex" line 5.
MULTI_FILE = """SyncTeX Version:1
Input:1:main.tex
Input:2:./sections/intro.tex
Magnification:1000
Unit:1
X Offset:0
Y Offset:0
Content:
{1
[1,1:0,0:39321600,50331648,0
(1,10:6553600,13107200:26214400,655360,131072
x1,10:6553600,13107200
)
(2,5:6553600,26214400:26214400,655360,131072
x2,5:6553600,26214400
)
]
}
Postamble:
"""


def gz(text: str) -> bytes:
    """Gzip-compress synctex text into the on-disk ``.synctex.gz`` form."""
    return gzip.compress(text.encode("utf-8"))
