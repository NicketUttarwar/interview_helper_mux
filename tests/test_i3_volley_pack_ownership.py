"""i3: Homunculus volley packs must be ALLOW operational under ownership.

exec_11871: speaker_roles LLM failed repeatedly with
authority_denied:persist:mastering/homunculus/volley_packs/speaker_roles_*.json
:speaker_roles:pre_soft_freeze:(unknown_path) because the path was uncataloged
under fail-closed ownership.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_ownership import write_permitted
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "i3_volley_packs")


def test_i3_volley_pack_persist_allowed_for_speaker_roles(ctx: RunContext) -> None:
    rel = "mastering/homunculus/volley_packs/speaker_roles_deadbeef.json"
    ok, reason = write_permitted(ctx, rel, "speaker_roles", role="producer", verb="persist")
    assert ok is True, reason
    assert reason == "operational"


def test_i3_speaker_roles_can_write_volley_pack(ctx: RunContext) -> None:
    rel = "mastering/homunculus/volley_packs/speaker_roles_cafe1234.json"
    ctx.write_json(rel, {"version": 1, "stage": "speaker_roles", "turns": []}, stage_key="speaker_roles")
    assert ctx.artifact_exists(rel)
