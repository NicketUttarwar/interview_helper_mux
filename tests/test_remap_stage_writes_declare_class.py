"""A remap stage's writes on remap paths declare the remap mutation class (ISSUES 113).

Ownership refuses such a write otherwise, in every epoch; the overlap repair
carried two of them for a long time and every overlap union died there.
"""

from __future__ import annotations

import re
from pathlib import Path

import interview_mux
from interview_mux.artifact_ownership import SEGMENT_ID_REMAP_PATHS, SEGMENT_ID_REMAP_STAGES

SRC = Path(interview_mux.__file__).parent


def _remap_stage_modules() -> dict[Path, str]:
    out: dict[Path, str] = {}
    for f in SRC.rglob("*.py"):
        s = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'^STAGE_KEY\s*=\s*"([a-z_]+)"', s, re.M)
        if m and m.group(1) in SEGMENT_ID_REMAP_STAGES:
            out[f] = m.group(1)
    return out


def test_remap_stage_writes_on_remap_paths_declare_segment_id_remap() -> None:
    modules = _remap_stage_modules()
    assert modules, "no remap-stage module found; the sweep needs STAGE_KEY constants"
    offenders: list[str] = []
    for f, stage in modules.items():
        s = f.read_text(encoding="utf-8", errors="replace")
        for call in re.finditer(r'write_json\(\s*"([^"]+)"[^)]*?\)', s, re.S):
            rel = call.group(1)
            if rel not in SEGMENT_ID_REMAP_PATHS:
                continue
            txt = call.group(0)
            if "stage_key=STAGE_KEY" in txt and "mutation_class" not in txt:
                offenders.append(f"{f.name}:{stage}:{rel}")
    assert offenders == [], offenders
