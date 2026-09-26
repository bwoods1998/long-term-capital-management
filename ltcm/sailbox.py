"""Moved to `league/sailbox.py` (the options overhaul, Sept 26, 2026, trap 4).

This name is the SAME module object as `league.sailbox` until the full prune deletes `ltcm/`, so
`from ltcm.sailbox import SailboxClient` and `patch("ltcm.sailbox.X")` keep working and patch the
one module there is.
"""

import sys

from league import sailbox as _sailbox

sys.modules[__name__] = _sailbox
