"""Artifact ownership constitution canaries (MUX_FORENSICS=0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_ownership import (
    ALLOW,
    DENY,
    AuthorityDenied,
    assert_execute_from_stage,
    assert_may_mark_done,
    assert_write,
    disk_paths_view,
    fail_closed,
    heal_pin_for,
    matrix_version,
    owner_of,
    primary_path_for_stage,
    write_permitted,
)
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.stage_completion import PRODUCER_PIN_TABLE, producer_pin_for_token
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.delenv("INTERVIEW_MUX_ARTIFACT_OWNERSHIP_FAIL_CLOSED", raising=False)
    return isolated_run_ctx(tmp_path, "ownership")


def test_catalog_parity_live_stages() -> None:
    live = set(ANALYSIS_ORDER) | set(DELIVERY_ORDER)
    assert STAGE_ARTIFACT_DISK_PATHS == disk_paths_view()
    assert not (live - set(STAGE_ARTIFACT_DISK_PATHS))
    assert not (set(STAGE_ARTIFACT_DISK_PATHS) - live)
    for sid in live:
        assert primary_path_for_stage(sid), sid


def test_fail_closed_default_true() -> None:
    assert fail_closed() is True


def test_deny_edl_vo_pickup(ctx) -> None:
    ok, reason = write_permitted(ctx, "vo_pickup/line.wav", "edl")
    assert ok is False
    assert "vo_pickup" in reason
    with pytest.raises(AuthorityDenied):
        assert_write(ctx, "vo_pickup/line.wav", "edl")


def test_owner_rerun_allowed(ctx) -> None:
    ok, reason = write_permitted(
        ctx, "mastering/vo_synthesize.json", "vo_synthesize"
    )
    assert ok is True
    assert reason == "owner_rerun"


def test_consumer_rerun_denied_for_owner_path(ctx) -> None:
    ok, reason = write_permitted(ctx, "master/transitions.json", "edl")
    assert ok is False


def test_nested_vo_under_edl_allow(ctx) -> None:
    ok, _ = write_permitted(ctx, "vo_pickup/x.wav", "vo_synthesize")
    assert ok is True


def test_heal_pin_no_sealed_default() -> None:
    assert producer_pin_for_token("seed_order_prereq", default="edl") == ""
    assert heal_pin_for("seed_order_prereq") == ""
    assert PRODUCER_PIN_TABLE.get("hollow_done") == ""
    assert PRODUCER_PIN_TABLE["hosted_vo_floor_unmet"] == "nugget_layup_compose"
    assert heal_pin_for("hosted_vo_floor_unmet") == "nugget_layup_compose"


def test_empty_execute_from_stage_refused_mid_pipeline(ctx) -> None:
    ctx.final_path(".stage_done", "transitions").parent.mkdir(parents=True, exist_ok=True)
    ctx.final_path(".stage_done", "transitions").write_text("1", encoding="utf-8")
    with pytest.raises(AuthorityDenied):
        assert_execute_from_stage(ctx, "")


def test_hollow_mark_refused_prepare(ctx) -> None:
    with pytest.raises(AuthorityDenied):
        assert_may_mark_done(ctx, "ingest")
    with pytest.raises(AuthorityDenied):
        assert_may_mark_done(ctx, "transcribe")
    with pytest.raises(AuthorityDenied):
        assert_may_mark_done(ctx, "audio_preclean")


def test_present_fallback_not_is_done(ctx) -> None:
    from interview_mux.homunculus.agenda import stage_outputs_present

    # Hollow stamp must not satisfy present for pipeline stages.
    ctx.final_path(".stage_done", "air_contract_sanitize").parent.mkdir(
        parents=True, exist_ok=True
    )
    ctx.final_path(".stage_done", "air_contract_sanitize").write_text(
        "1", encoding="utf-8"
    )
    assert stage_outputs_present(ctx, "air_contract_sanitize") is False


def test_hard_freeze_floor_no_catastrophe(ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.seat_authority import seat_mutation_allowed, stamp_hard_seat_freeze

    src = Path("src/interview_mux/vo_contract.py").read_text(encoding="utf-8")
    # ensure body must not call seat_mutation with catastrophe token
    ensure_body = src.split("def ensure_hosted_framing_vo_seats", 1)[1].split(
        "def _record_hosted_floor_unmet", 1
    )[0]
    assert "reason=\"catastrophe_hosted_vo_floor\"" not in ensure_body
    assert "reason='catastrophe_hosted_vo_floor'" not in ensure_body

    stamp_hard_seat_freeze(ctx, reason="vo_synthesize")
    ok, why = seat_mutation_allowed(
        ctx, reason="catastrophe_hosted_vo_floor", require_meta_gate=False
    )
    assert ok is False
    assert "hard_freeze" in why


def test_ensure_hard_freeze_pins_layup(ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.vo_contract import ensure_hosted_framing_vo_seats

    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _c: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _c: 3,
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.soft_freeze_active", lambda _c: False
    )
    # Bypass schema via mirrored write for fixture
    from interview_mux.write_staging import write_mirrored_json

    write_mirrored_json(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "layup_1",
                    "text": "hello",
                    "delivery": "synthesize",
                    "skipped_optional": True,
                    "air_script_omit": True,
                    "skip_reason": "media_ip_cta_hole",
                }
            ]
        },
    )
    reseated = ensure_hosted_framing_vo_seats(ctx)
    assert reseated == []
    assert heal_pin_for("hosted_vo_floor_unmet") == "nugget_layup_compose"


def test_clear_from_edl_keeps_vo(ctx) -> None:
    from interview_mux.write_staging import write_mirrored_json

    write_mirrored_json(
        ctx,
        "mastering/vo_synthesize.json",
        {"status": "ok", "lines": []},
    )
    vo_wav = ctx.final_path("vo_pickup", "matched", "line_a.wav")
    vo_wav.parent.mkdir(parents=True, exist_ok=True)
    vo_wav.write_bytes(b"RIFF" + b"\x00" * 64)
    ctx.final_path(".stage_done", "vo_synthesize").parent.mkdir(parents=True, exist_ok=True)
    ctx.final_path(".stage_done", "vo_synthesize").write_text("1", encoding="utf-8")
    write_mirrored_json(
        ctx,
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_001"],
            "timeline_duration_ms": 1000,
            "clips": [],
        },
    )
    ctx.final_path(".stage_done", "edl").write_text("1", encoding="utf-8")
    from interview_mux.v2.config import DELIVERY_ORDER

    ctx.clear_from("edl", DELIVERY_ORDER)
    assert ctx.is_done("vo_synthesize")
    assert vo_wav.is_file()


def test_matrix_version_stable() -> None:
    assert len(matrix_version()) == 16
    assert len(ALLOW) > 100
    assert len(DENY) >= 10


def test_one_writer_raw_allowlist() -> None:
    from interview_mux.artifact_ownership import ONE_WRITER_RAW_ALLOWLIST

    src = Path("src/interview_mux").rglob("*.py")
    hits = []
    for path in src:
        text = path.read_text(encoding="utf-8")
        if "_one_writer_raw = True" in text or '_one_writer_raw=True' in text:
            hits.append(str(path))
    # Only analysis_memory (ops scaffold) in production src.
    prod = [h for h in hits if "test" not in h]
    assert any("analysis_memory.py" in h for h in prod)
    assert "analysis_memory.ensure_analysis_workspace" in ONE_WRITER_RAW_ALLOWLIST


def test_hot_paths_match_one_writer() -> None:
    from interview_mux.artifact_ownership import HOT_PATHS
    from interview_mux.artifact_sanitize.one_writer import HOT_ARTIFACT_RELS

    assert HOT_PATHS == HOT_ARTIFACT_RELS


def test_forensics_restamps_matrix_version_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade: plain refuse mismatch; MUX_FORENSICS=1 restamps same run_id.

    exec_13159 i5b: ownership ALLOW patch mid-campaign must not brick driver
    claim under forensics.
    """
    from interview_mux.artifact_ownership import (
        MATRIX_VERSION_META_KEY,
        check_matrix_version,
        matrix_version,
        write_permitted,
    )

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "matrix_restamp_f")
    ctx.write_json(
        "run_meta.json",
        {"version": 1, MATRIX_VERSION_META_KEY: "stale_hash_0000"},
        skip_handoff=True,
    )

    ok0, msg0 = check_matrix_version(ctx)
    assert not ok0 and "matrix_version_mismatch" in msg0
    allowed0, reason0 = write_permitted(
        ctx, "master/selection.json", "full_master_ranking", role="producer"
    )
    assert not allowed0 and "matrix_version_mismatch" in reason0

    monkeypatch.setenv("MUX_FORENSICS", "1")
    ok1, msg1 = check_matrix_version(ctx)
    assert ok1 and "forensics_restamp" in msg1
    live = matrix_version()
    meta2 = ctx.read_json("run_meta.json")
    assert meta2.get(MATRIX_VERSION_META_KEY) == live
