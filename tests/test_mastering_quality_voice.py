"""Voice-clone consent: prefer pickup; any on-tape speaker allowed with consent."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.mastering_feasibility import FeasibilityInputs, check_candidate
from interview_mux.mastering_voice_clone import (
    CloneNotAuthorized,
    authorization_error,
    cold_open_clone_allowed,
    grant_consent,
    load_consent,
    revoke_consent,
)
from interview_mux.run_context import RunContext
from run_fixtures import patch_executions_root


def _seed_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    """Minimal run with a confirmed pickup host and an approved reference."""
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_voice_clone", create=True)
    ctx.write_json(
        "run_meta.json",
        {"execution_id": ctx.run_id, "created_at": "2026-01-01T00:00:00Z"},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/source_topology.json",
        {
            "topology": "one_on_one_asymmetric",
            "pickup_eligible_speaker_id": "spk_host",
            "speaker_stats": [
                {"speaker_id": "spk_host", "talk_ratio": 0.2},
                {"speaker_id": "spk_guest", "talk_ratio": 0.8},
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {
                    "speaker_id": "spk_host",
                    "role": "interviewer",
                    "confidence": 0.95,
                    "evidence": ["Opening question pattern"],
                },
                {
                    "speaker_id": "spk_guest",
                    "role": "interviewee",
                    "confidence": 0.92,
                    "evidence": ["Extended answers"],
                },
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/voice_reference/spk_host.json",
        {"speaker_id": "spk_host", "approved": True, "approved_at": "2026-01-01T00:00:00Z"},
        skip_handoff=True,
    )
    return ctx


def test_guest_clone_allowed_with_on_tape_speaker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Any on-tape speaker may receive consent; prefer pickup but guest is not banned."""
    ctx = _seed_run(tmp_path, monkeypatch)
    ctx.write_json(
        "understanding/voice_reference/spk_guest.json",
        {"speaker_id": "spk_guest", "approved": True, "approved_at": "2026-01-01T00:00:00Z"},
        skip_handoff=True,
    )
    consent = grant_consent(ctx, speaker_id="spk_guest", scopes=["cold_open"])
    assert consent["speaker_id"] == "spk_guest"
    assert consent.get("is_preferred_pickup") is False


def test_authorization_allows_content_role_when_consented():
    err = authorization_error(
        {
            "granted": True,
            "scopes": ["cold_open"],
            "reference_approved": True,
            "speaker_id": "spk_guest",
        },
        speaker_id="spk_guest",
        scope="cold_open",
        pickup_speaker_id="spk_host",
        speaker_role="interviewee",
    )
    assert err is None


def test_consent_required_for_vo_clone_cold_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _seed_run(tmp_path, monkeypatch)
    ok, reason = cold_open_clone_allowed(
        ctx, {"kind": "vo_clone_open", "vo_voice_speaker_id": "spk_host"}
    )
    assert ok is False
    assert reason and "consent" in reason.lower()

    grant_consent(ctx, speaker_id="spk_host", scopes=["cold_open"])
    ok, reason = cold_open_clone_allowed(
        ctx, {"kind": "vo_clone_open", "vo_voice_speaker_id": "spk_host"}
    )
    assert ok is True
    assert reason is None


def test_bridges_scope_does_not_cover_cold_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _seed_run(tmp_path, monkeypatch)
    grant_consent(ctx, speaker_id="spk_host", scopes=["bridges"])
    ok, reason = cold_open_clone_allowed(
        ctx, {"kind": "vo_clone_open", "vo_voice_speaker_id": "spk_host"}
    )
    assert ok is False
    assert reason and "scope" in reason.lower()


def test_revocation_invalidates_consent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _seed_run(tmp_path, monkeypatch)
    grant_consent(ctx, speaker_id="spk_host", scopes=["cold_open", "bridges"])
    assert load_consent(ctx)["granted"] is True
    revoke_consent(ctx)
    consent = load_consent(ctx)
    assert consent["granted"] is False
    assert consent["revoked_at"]
    ok, _ = cold_open_clone_allowed(ctx, {"kind": "vo_clone_open"})
    assert ok is False


def test_feasibility_blocks_unconsented_vo_clone_open():
    """Feasibility treats missing clone authorization as a blocking check."""
    candidate = {
        "candidate_id": "c1",
        "cold_open": {
            "kind": "vo_clone_open",
            "vo_line_id": "vo_1",
            "vo_voice_speaker_id": "spk_host",
            "rationale": "x",
            "evidence_refs": ["a"],
            "confidence": 0.5,
        },
        "ordered_segment_ids": ["s1"],
        "evidence_refs": ["a"],
    }
    inputs = FeasibilityInputs(
        segments={"s1": {"start_ms": 0, "end_ms": 1000}},
        vo_lines={"vo_1": {"speaker_id": "spk_host", "audio_path": "vo.wav"}},
        pickup_speaker_id="spk_host",
        clone_authorized=False,
    )
    row = check_candidate(candidate, inputs)
    assert row["verdict"] == "fail"
    assert any("consent" in r.lower() or "clone" in r.lower() for r in row["blocking_reasons"])


def test_feasibility_allows_consented_non_pickup_vo_line():
    candidate = {
        "candidate_id": "c1",
        "cold_open": {"kind": "none", "rationale": "x", "evidence_refs": ["a"], "confidence": 0.5},
        "ordered_segment_ids": ["s1"],
        "vo_line_ids": ["vo_1"],
        "evidence_refs": ["a"],
    }
    inputs = FeasibilityInputs(
        segments={"s1": {"start_ms": 0, "end_ms": 1000}},
        vo_lines={"vo_1": {"speaker_id": "spk_guest", "audio_path": "vo.wav"}},
        pickup_speaker_id="spk_host",
        clone_authorized=True,
    )
    row = check_candidate(candidate, inputs)
    # Prefer pickup is editorial; consented non-pickup must not hard-fail solely for speaker class
    assert row["verdict"] != "fail" or not any("pickup" in r.lower() for r in row["blocking_reasons"])
