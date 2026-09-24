"""Land Honesty v2 — Cluster A hollow done / orphan promote + thin incompleteness.

MUX_FORENSICS=0. Phase 1+2 Definition of Done cascades.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

import pytest

from interview_mux.delivery_guardrails import (
    promote_complete_orphan_stage_done,
    seed_stage_complete,
)
from interview_mux.done_authority import (
    land_honest,
    may_skip_as_complete,
    unpaid_land_blocks_promote,
    unpaid_land_reason,
)
from interview_mux.mix_junction_seat import (
    begin_remaster,
    clear_remaster,
    demote_hollow_mix_done,
    ensure_speech_first_remaster,
    note_speech_first_mix,
    remaster_owner,
    speech_first_remaster_owed,
)
from interview_mux.pipeline import shared_analysis_chain_complete
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import stage_artifact_incompleteness
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER
from run_fixtures import isolated_run_ctx, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "exec_land_honesty")


def _write_assembly(ctx: RunContext) -> Path:
    path = ctx.path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)
    return path


def test_mtime_defeat_still_blocks_promote_while_remaster_owner_set(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assembly newer than remaster stamp must not greenwash unpaid remaster."""
    note_speech_first_mix(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete", lambda _c: True
    )
    assert ensure_speech_first_remaster(ctx) is True
    assert remaster_owner(ctx) == "music_epoch"

    time.sleep(0.05)
    _write_assembly(ctx)
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _sid: True,
    )

    reason = unpaid_land_reason(ctx, "mix")
    assert reason is not None
    assert "remaster owed" in reason
    assert unpaid_land_blocks_promote(ctx, "mix") is True
    assert promote_complete_orphan_stage_done(ctx, ("mix",)) == []
    assert not ctx.is_done("mix")

    clear_remaster(ctx)
    assert unpaid_land_reason(ctx, "mix") is None


def test_junction_remaster_blocks_mix_and_junction_promote(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin_remaster(ctx, owner="junction")
    _write_assembly(ctx)
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _sid: True,
    )
    # Bypass schema — only need files present for promote presence checks.
    for rel in ("master/junction_snip_qa.json", "master/seam_autopsy.json"):
        p = ctx.path(*rel.split("/"))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"version":1,"generated_at":"t"}', encoding="utf-8")

    assert unpaid_land_reason(ctx, "mix") is not None
    assert unpaid_land_reason(ctx, "junction_snip_qa") is not None
    assert promote_complete_orphan_stage_done(ctx, ("mix", "junction_snip_qa")) == []


def test_speech_first_owed_before_owner_blocks_promote(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    note_speech_first_mix(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete", lambda _c: True
    )
    _write_assembly(ctx)
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _sid: True,
    )
    assert remaster_owner(ctx) == ""
    assert speech_first_remaster_owed(ctx) is True
    assert unpaid_land_reason(ctx, "mix") is not None
    assert promote_complete_orphan_stage_done(ctx, ("mix",)) == []


def test_ensure_demotes_hollow_mix_when_remaster_owed(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    note_speech_first_mix(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete", lambda _c: True
    )
    marker = ctx.final_path(".stage_done", "mix")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("done")
    assert ctx.is_done("mix")
    assert ensure_speech_first_remaster(ctx) is True
    assert remaster_owner(ctx) == "music_epoch"
    assert not ctx.is_done("mix")


def test_stamp_alone_incompleteness_and_unpaid(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled", lambda: True
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [], "nugget_layup_authority": True},
    )
    assert not ctx.artifact_exists("understanding/nugget_layup_plan.json")
    reason = unpaid_land_reason(ctx, "gap_framing_compose")
    assert reason is not None
    assert "stamp-alone" in reason
    inc = stage_artifact_incompleteness(ctx, "gap_framing_compose")
    assert inc is not None
    assert unpaid_land_blocks_promote(ctx, "nugget_layup_compose") is True


def test_shared_analysis_chain_complete_requires_land_honest(ctx: RunContext) -> None:
    mark_done_raw(ctx, "episode_structure_compose")
    assert may_skip_as_complete(ctx, "episode_structure_compose") is False
    assert shared_analysis_chain_complete(ctx) is False
    assert land_honest(ctx, "episode_structure_compose") is False


def test_thin_empty_json_primary_incomplete(ctx: RunContext) -> None:
    # Pick a disk-mapped delivery stage with a JSON primary.
    sid = "transitions"
    rel = STAGE_ARTIFACT_DISK_PATHS.get(sid)
    assert rel
    ctx.write_json(rel, {})
    mark_done_raw(ctx, sid)
    reason = stage_artifact_incompleteness(ctx, sid)
    assert reason is not None
    assert seed_stage_complete(ctx, sid) is False


def test_disk_mapped_hollow_marker_matrix_sample(ctx: RunContext) -> None:
    """XC-HOLLOW sample: hollow marker alone is never seed-complete / promotable."""
    sample: list[str] = []
    for sid in list(ANALYSIS_ORDER) + list(DELIVERY_ORDER):
        if sid in STAGE_ARTIFACT_DISK_PATHS:
            sample.append(sid)
        if len(sample) >= 20:
            break
    assert sample
    for sid in sample:
        mark_done_raw(ctx, sid)
        assert seed_stage_complete(ctx, sid) is False
        assert land_honest(ctx, sid) is False


def test_promote_calls_unpaid_land_api_present() -> None:
    """Lint: promote_complete_orphan_stage_done must reference unpaid_land."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "interview_mux"
        / "delivery_guardrails.py"
    )
    text = src.read_text(encoding="utf-8")
    assert "unpaid_land_blocks_promote" in text
    da = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "interview_mux"
        / "done_authority.py"
    )
    da_text = da.read_text(encoding="utf-8")
    assert "def unpaid_land_reason" in da_text
    assert "def land_honest" in da_text


def test_demote_hollow_mix_when_unpaid(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    begin_remaster(ctx, owner="junction")
    marker = ctx.final_path(".stage_done", "mix")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("done")
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    assert demote_hollow_mix_done(ctx) is True
    assert not ctx.is_done("mix")
