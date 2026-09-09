"""Wave 3–8 automation reliability program regressions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.air_script import gap_line_air_eligible
from interview_mux.aspirational_quality import publish_blocked_by_advisories
from interview_mux.run_context import RunContext
from interview_mux.speaker_role_evidence import enrich_content_brief_from_evidence
from run_fixtures import isolated_run_ctx


def _write_raw(ctx: RunContext, rel: str, data: dict) -> None:
    path = ctx.path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _ctx(tmp_path: Path, name: str = "auto_rel") -> RunContext:
    return isolated_run_ctx(tmp_path, name)


def test_gap_line_air_eligible() -> None:
    assert gap_line_air_eligible({"line_id": "x", "delivery": "synthesize"}) is True
    assert gap_line_air_eligible({"line_id": "x", "air_script_omit": True}) is False
    assert gap_line_air_eligible({"line_id": "x", "skipped_optional": True}) is False


def test_assert_script_authority_chain_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "auth_chain")
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_test_001",
                    "text": "Hello from the gap.",
                    "delivery": "synthesize",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                }
            ]
        },
    )
    from interview_mux.spoken_copy_guard import script_hash
    from interview_mux.vo_synthesis_audit import assert_script_authority_chain

    h = script_hash("Different synth text.")
    _write_raw(
        ctx,
        "vo_pickup/synthesis_report.json",
        {
            "entries": [
                {
                    "line_id": "vo_test_001",
                    "script_hash": h,
                    "context_hash": "c",
                    "qc_pass": True,
                }
            ]
        },
    )
    errs = assert_script_authority_chain(ctx, "vo_test_001")
    assert any("synthesis_hash_mismatch" in e for e in errs)


def test_delivery_recovery_restores_vo_pickup_wav(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "restore_vo")
    arch = ctx.run_dir / ".archived" / "20260901T120000Z" / "vo_pickup" / "synthesized"
    arch.mkdir(parents=True)
    wav = arch / "vo_layup_seg_001.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 128)
    from interview_mux.delivery_recovery import restore_master_bundle

    restored = restore_master_bundle(ctx)
    assert ctx.artifact_exists("vo_pickup/synthesized/vo_layup_seg_001.wav")
    assert any("vo_pickup" in r for r in restored)


def test_publish_blocked_by_advisories_respects_g_publish_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "adv_pub")
    ctx.write_json(
        "run_meta.json",
        {
            "quality_advisories": [{"gate_id": "listenability_contract", "failed_checks": ["x"]}],
            "g_publish_cleared": True,
        },
    )
    assert publish_blocked_by_advisories(ctx) is False


def test_publish_blocked_by_advisories_respects_upload_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.aspirational_quality import consent_g_publish_advisories

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "adv_consent")
    ctx.write_json(
        "run_meta.json",
        {
            "quality_advisories": [{"gate_id": "listenability_contract", "failed_checks": ["x"]}],
            "g_publish_pending": True,
        },
    )
    assert publish_blocked_by_advisories(ctx) is True
    consent_g_publish_advisories(ctx)
    assert publish_blocked_by_advisories(ctx) is False
    meta = ctx.read_json("run_meta.json")
    assert meta.get("g_publish_advisory_consent") is True
    assert meta.get("g_publish_pending") is True


def test_enrich_content_brief_from_speaker_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "brief_enrich")
    _write_raw(ctx, "understanding/content_brief.json", {"thesis": "oncology", "topics": []})
    _write_raw(
        ctx,
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewee", "display_name": "Mohan"},
                {"speaker_id": "spk_1", "role": "interviewer", "display_name": "Amr"},
            ]
        },
    )
    assert enrich_content_brief_from_evidence(ctx) is True
    brief = ctx.read_json("understanding/content_brief.json")
    assert brief.get("guest_name") == "Mohan"
    assert brief.get("host_name") == "Amr"


def test_unseated_required_vo_pre_mix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "unseated")
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_036",
                    "delivery": "synthesize",
                    "required": True,
                    "gap_type": "nugget_layup",
                    "text": "Required line not on air.",
                    "targets_segment_id": "seg_036",
                    "placement": "before",
                }
            ]
        },
    )
    _write_raw(ctx, "master/edl.json", {"clips": [], "version": 1})
    from interview_mux.publishability_boundary import validate_publishability

    report = validate_publishability(ctx, checkpoint="pre_mix")
    codes = [v.code for v in report.violations]
    assert "unseated_required_vo" in codes
