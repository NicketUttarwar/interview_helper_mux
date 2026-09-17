"""`frontend/src/utils/v2Phases.ts` is a hand-maintained mirror of `v2.phases.PHASES`.

`PhaseWorkbench.tsx` does not read the phase journey from the API — it imports that
mirror — so drift silently gives the operator a stale journey. The mirror has already
rotted twice (missing `low_conf_island_scan` / `connector_fuse_pass`, then the whole
`understand-a/b/c` split plus five adopted stages), which is why this parity test
exists in the same spirit as `tests/test_solver_posture.py` reading
`partialOperatorGates.ts`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from interview_mux.v2 import phases as P
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

MIRROR = Path("frontend/src/utils/v2Phases.ts")

# TS camelCase key -> Python snake_case key.
KEY_ALIASES = {"legacyId": "legacy_id", "labelDetail": "label_detail"}
COMPARED_KEYS = (
    "id",
    "label",
    "description",
    "stages",
    "gate",
    "optional",
    "nle",
    "legacy_id",
    "label_detail",
)
DEFAULTS: dict[str, Any] = {
    "gate": None,
    "optional": False,
    "nle": False,
    "legacy_id": None,
    "label_detail": None,
}


def _parse_mirror() -> list[dict[str, Any]]:
    """Read the `V2_PHASES` array literal as JSON.

    The literal is plain data (strings, string arrays, booleans, null) so the only
    non-JSON syntax to undo is bare keys and trailing commas. A literal that stops
    being parseable here is itself drift worth failing on.
    """
    src = MIRROR.read_text(encoding="utf-8")
    match = re.search(
        r"export const V2_PHASES: V2Phase\[\] = (\[.*?\n\]);", src, re.DOTALL
    )
    assert match, "V2_PHASES array literal not found in v2Phases.ts"
    body = match.group(1)
    body = re.sub(r"(?m)^(\s*)([A-Za-z_][A-Za-z0-9_]*):", r'\1"\2":', body)
    body = re.sub(r",(\s*[}\]])", r"\1", body)
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:  # pragma: no cover - failure path
        pytest.fail(f"V2_PHASES is no longer a plain data literal: {exc}")


def _normalize(phase: dict[str, Any]) -> dict[str, Any]:
    renamed = {KEY_ALIASES.get(k, k): v for k, v in phase.items()}
    out = {k: renamed.get(k, DEFAULTS.get(k)) for k in COMPARED_KEYS}
    out["stages"] = list(out["stages"] or [])
    out["optional"] = bool(out["optional"])
    out["nle"] = bool(out["nle"])
    return out


def test_mirror_matches_python_phases_exactly() -> None:
    mirrored = [_normalize(p) for p in _parse_mirror()]
    expected = [_normalize(p) for p in P.PHASES]
    assert [p["id"] for p in mirrored] == [p["id"] for p in expected]
    for got, want in zip(mirrored, expected):
        assert got == want, f"mirror drifted for phase {want['id']}"


def test_mirror_covers_every_seed_stage() -> None:
    seed = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
    mirrored: list[str] = []
    for phase in _parse_mirror():
        mirrored.extend(phase.get("stages") or [])
    assert sorted(mirrored) == sorted(seed)
    assert len(mirrored) == len(set(mirrored)) == 72


def test_mirror_keeps_the_legacy_understand_id_resolvable() -> None:
    """GUI code keyed on the pre-split `understand` id must still find its stages."""
    split = [p for p in _parse_mirror() if p.get("legacyId") == "understand"]
    assert [p["id"] for p in split] == ["understand-a", "understand-b", "understand-c"]
    legacy: list[str] = []
    for phase in split:
        legacy.extend(phase["stages"])
    assert legacy == P.phase_stage_ids("understand")


def test_mirror_exposes_the_python_phase_helpers() -> None:
    src = MIRROR.read_text(encoding="utf-8")
    for helper in ("phaseForStage", "phasesForId", "phaseStageIds"):
        assert f"export function {helper}" in src, helper
