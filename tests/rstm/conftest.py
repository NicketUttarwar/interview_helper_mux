from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root and tests/ are importable when pytest loads this package.
_ROOT = Path(__file__).resolve().parents[2]
_TESTS = Path(__file__).resolve().parents[1]
for p in (str(_ROOT), str(_TESTS)):
    if p not in sys.path:
        sys.path.insert(0, p)
