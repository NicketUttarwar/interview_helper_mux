"""Static + behavioral enforcement of read_path vs path for upstream artifacts."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "interview_mux"

ALLOWLIST = {
    SRC / "write_staging.py",
    SRC / "run_context.py",
}

READ_TRAP_PAT = re.compile(
    r"ctx\.path\([^)]+\)\.(?:is_file|read_text|read_bytes|exists)\("
)


def _py_files() -> list[Path]:
    return [p for p in SRC.rglob("*.py") if p not in ALLOWLIST]


def test_no_ctx_path_read_traps_outside_allowlist():
    violations: list[str] = []
    for path in _py_files():
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if READ_TRAP_PAT.search(line) and "resolve_write_path" not in line:
                violations.append(f"{path.relative_to(REPO)}:{i}: {line.strip()}")
    assert violations == [], "Use ctx.read_path/artifact_exists/read_json for upstream reads:\n" + "\n".join(
        violations[:20]
    )


def test_nle_state_uses_read_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from interview_mux.nle_state import load_nle
    from interview_mux.run_context import RunContext
    from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    ctx.write_json("segments/nle_edits.json", {"sequence_order": ["s1"]}, skip_handoff=True)
    enter_stage_staging("full_master_ranking")
    try:
        assert not ctx.path("segments/nle_edits.json").is_file()
        nle = load_nle(ctx)
        assert nle.get("sequence_order") == ["s1"]
    finally:
        exit_stage_staging()


def test_sfx_mmaudio_loads_crafted_prompts_via_read_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from interview_mux.stages.sfx_mmaudio import _load_crafted_prompts
    from interview_mux.run_context import RunContext
    from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    prompts = ctx.final_path("sound_design", "sfx_prompts.json")
    prompts.parent.mkdir(parents=True, exist_ok=True)
    prompts.write_text(
        '{"prompts":[{"asset_id":"a1","sfx_prompt":"whoosh","duration_seconds":2,"negative_prompt":""}]}',
        encoding="utf-8",
    )
    enter_stage_staging("mmaudio_sfx")
    try:
        rows = _load_crafted_prompts(ctx)
        assert "a1" in rows
    finally:
        exit_stage_staging()
