"""Pytest hooks for tests/e2e — ensure e2e_runner is importable from repo .venv."""

from __future__ import annotations

import sys
from pathlib import Path

_E2E_ROOT = Path(__file__).resolve().parent
if str(_E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(_E2E_ROOT))
