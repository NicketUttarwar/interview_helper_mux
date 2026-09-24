"""XC-HOLLOW shared-path producer_stage matrix + thin incompleteness wiring.

ADDITIONAL coverage beyond test_land_honesty_comprehensive.py:
- Every SHARED_PATH_PRODUCER_STAGES JSON primary
- Empty/missing producer_stage → unpaid shared-path land (file exists)
- Thin incompleteness sample + _primary_artifact_thin_incompleteness wiring

MUX_FORENSICS=0. isolated_run_ctx.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

import pytest

from interview_mux.done_authority import (
    GATE_MARKER_ONLY,
    SHARED_PATH_PRODUCER_STAGES,
    land_honest,
    shared_path_producer_mismatch,
    unpaid_land_blocks_promote,
    unpaid_land_reason,
)
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    _primary_artifact_thin_incompleteness,
    stage_artifact_incompleteness,
)
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER
from run_fixtures import isolated_run_ctx, mark_done_raw

# Shared-path stages whose primary is a JSON disk artifact.
_SHARED_JSON_STAGES: list[str] = sorted(
    sid
    for sid in SHARED_PATH_PRODUCER_STAGES
    if str(STAGE_ARTIFACT_DISK_PATHS.get(sid) or "").endswith(".json")
)

# Wrong producer stamped on the shared primary (must not equal the stage id).
_WRONG_PRODUCER: dict[str, str] = {
    "gap_report_sanitize": "gap_framing_compose",
    "air_contract_sanitize": "air_script_compose",
    "selection_order_sanitize": "full_master_ranking",
    "sound_design_plan": "sound_design_palettes",
}

# Minimal non-empty bodies so thin-empty does not mask producer_stage checks.
_MINIMAL_BODY: dict[str, dict] = {
    "gap_report_sanitize": {"interviewer_lines": []},
    "air_contract_sanitize": {"version": 1},
    "selection_order_sanitize": {"ordered_segment_ids": ["seg_001"]},
    "sound_design_plan": {"version": 1},
}

# Sample of disk-mapped JSON stages for empty-object thin incompleteness (XC-HOLLOW-01).
_THIN_SAMPLE_STAGES: list[str] = [
    sid
    for sid in list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
    if sid in STAGE_ARTIFACT_DISK_PATHS
    and sid not in GATE_MARKER_ONLY
    and str(STAGE_ARTIFACT_DISK_PATHS.get(sid) or "").endswith(".json")
][:8]

# Stages whose specialized path reaches `_primary_artifact_thin_incompleteness`
# (skip early-return specialists like transcript_review_build / source_topology).
_THIN_WIRE_STAGES: list[str] = [
    "transcribe",
    "audio_probe_build",
    "interview_spine_build",
]

# Non-empty but key-thin docs still incomplete (schema / specialized / usable).
_THIN_MISSING_KEYS_STAGES: list[str] = [
    "interview_spine_build",
    "speaker_roles",
    "talking_points_compose",
    "boundary_detection",
]


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "exec_land_honesty_shared_thin")


def _write_raw_json(ctx: RunContext, rel: str, doc: dict) -> Path:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _assert_shared_json_coverage() -> None:
    assert _SHARED_JSON_STAGES, "SHARED_PATH_PRODUCER_STAGES must include JSON primaries"
    for sid in SHARED_PATH_PRODUCER_STAGES:
        rel = STAGE_ARTIFACT_DISK_PATHS.get(sid)
        assert rel, f"{sid} missing from STAGE_ARTIFACT_DISK_PATHS"
        if str(rel).endswith(".json"):
            assert sid in _SHARED_JSON_STAGES
            assert sid in _WRONG_PRODUCER
            assert sid in _MINIMAL_BODY


# ---------------------------------------------------------------------------
# 1–2. Shared-path producer_stage mismatch / match (every JSON shared stage)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sid", _SHARED_JSON_STAGES)
def test_shared_path_wrong_producer_unpaid_and_not_land_honest(
    ctx: RunContext, sid: str
) -> None:
    _assert_shared_json_coverage()
    rel = STAGE_ARTIFACT_DISK_PATHS[sid]
    wrong = _WRONG_PRODUCER[sid]
    assert wrong != sid
    body = dict(_MINIMAL_BODY[sid])
    body["_meta"] = {"producer_stage": wrong}
    _write_raw_json(ctx, rel, body)
    mark_done_raw(ctx, sid)

    reason = unpaid_land_reason(ctx, sid)
    assert reason is not None
    assert "shared-path" in reason
    assert unpaid_land_blocks_promote(ctx, sid) is True
    assert land_honest(ctx, sid) is False
    mismatch = shared_path_producer_mismatch(ctx, sid)
    assert mismatch is not None
    assert "shared-path" in mismatch


@pytest.mark.parametrize("sid", _SHARED_JSON_STAGES)
def test_shared_path_matching_producer_clears_shared_unpaid(
    ctx: RunContext, sid: str
) -> None:
    rel = STAGE_ARTIFACT_DISK_PATHS[sid]
    body = dict(_MINIMAL_BODY[sid])
    body["_meta"] = {"producer_stage": sid}
    _write_raw_json(ctx, rel, body)

    assert shared_path_producer_mismatch(ctx, sid) is None
    reason = unpaid_land_reason(ctx, sid)
    # Shared unpaid clears; other incompleteness families may still remain.
    assert reason is None or "shared-path" not in reason


# ---------------------------------------------------------------------------
# 3. Empty / missing producer_stage → unpaid (primary exists, unclaimed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sid", _SHARED_JSON_STAGES)
@pytest.mark.parametrize(
    "meta",
    [
        None,  # no _meta key
        {},  # empty _meta
        {"producer_stage": ""},  # blank producer
        {"producer_stage": "   "},  # whitespace-only
    ],
    ids=["no_meta", "empty_meta", "blank_producer", "whitespace_producer"],
)
def test_shared_path_empty_or_missing_producer_is_unpaid(
    ctx: RunContext, sid: str, meta: dict | None
) -> None:
    """Primary on disk with empty/missing producer_stage is unpaid shared-path land."""
    rel = STAGE_ARTIFACT_DISK_PATHS[sid]
    body = dict(_MINIMAL_BODY[sid])
    if meta is not None:
        body["_meta"] = meta
    _write_raw_json(ctx, rel, body)
    mark_done_raw(ctx, sid)

    mismatch = shared_path_producer_mismatch(ctx, sid)
    assert mismatch is not None
    assert "shared-path" in mismatch
    assert "missing producer_stage" in mismatch
    reason = unpaid_land_reason(ctx, sid)
    assert reason == mismatch
    assert unpaid_land_blocks_promote(ctx, sid) is True
    assert land_honest(ctx, sid) is False


# ---------------------------------------------------------------------------
# 4–5. Thin incompleteness sample + wiring through stage_artifact_incompleteness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sid", _THIN_SAMPLE_STAGES)
def test_thin_empty_object_incompleteness_and_not_land_honest(
    ctx: RunContext, sid: str
) -> None:
    rel = STAGE_ARTIFACT_DISK_PATHS[sid]
    _write_raw_json(ctx, rel, {})
    mark_done_raw(ctx, sid)

    inc = stage_artifact_incompleteness(ctx, sid)
    assert inc is not None
    assert land_honest(ctx, sid) is False


@pytest.mark.parametrize("sid", _THIN_MISSING_KEYS_STAGES)
def test_thin_missing_required_keys_incompleteness(ctx: RunContext, sid: str) -> None:
    """Non-empty but key-thin doc still refuses land (schema / specialized / thin)."""
    assert sid in STAGE_ARTIFACT_DISK_PATHS
    rel = STAGE_ARTIFACT_DISK_PATHS[sid]
    # Non-empty so empty-object thin may not fire; still incomplete without required keys.
    _write_raw_json(ctx, rel, {"_placeholder": True})
    mark_done_raw(ctx, sid)

    inc = stage_artifact_incompleteness(ctx, sid)
    assert inc is not None
    assert land_honest(ctx, sid) is False


def test_primary_artifact_thin_wired_via_stage_artifact_incompleteness(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_primary_artifact_thin_incompleteness`` must be reached for ≥3 stages."""
    assert len(_THIN_WIRE_STAGES) >= 3
    for sid in _THIN_WIRE_STAGES:
        assert sid in STAGE_ARTIFACT_DISK_PATHS
        assert str(STAGE_ARTIFACT_DISK_PATHS[sid]).endswith(".json")

    seen: list[str] = []
    real = _primary_artifact_thin_incompleteness

    def _spy(c: RunContext, stage_id: str, path: str) -> str | None:
        seen.append(str(stage_id))
        return real(c, stage_id, path)

    monkeypatch.setattr(
        "interview_mux.stage_completion._primary_artifact_thin_incompleteness",
        _spy,
    )

    for sid in _THIN_WIRE_STAGES:
        rel = STAGE_ARTIFACT_DISK_PATHS[sid]
        _write_raw_json(ctx, rel, {})
        reason = stage_artifact_incompleteness(ctx, sid)
        assert reason is not None
        # Direct helper agrees when artifact is empty object.
        direct = real(ctx, sid, rel)
        assert direct is not None
        assert "empty object" in direct or "schema-thin" in direct or "empty" in direct

    wired = {s for s in seen if s in set(_THIN_WIRE_STAGES)}
    assert len(wired) >= 3, f"thin helper not wired for enough stages; seen={seen}"


def test_shared_path_set_matches_disk_json_primaries() -> None:
    """Sanity: frozenset entries with JSON primaries are exactly the matrix under test."""
    _assert_shared_json_coverage()
    json_from_ssot = {
        sid
        for sid in SHARED_PATH_PRODUCER_STAGES
        if str(STAGE_ARTIFACT_DISK_PATHS.get(sid) or "").endswith(".json")
    }
    assert set(_SHARED_JSON_STAGES) == json_from_ssot
