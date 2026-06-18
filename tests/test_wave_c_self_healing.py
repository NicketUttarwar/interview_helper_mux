"""Wave C self-healing — H-ORC-02 / H-ORC-03 hardening tests."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from interview_mux.analysis_memory import enqueue_investigations, load_queue
from interview_mux.analysis_orchestrator import drain_investigation_queue
from interview_mux.coherence.analyze import maybe_run_coherence_analysis
from interview_mux.coherence.duration_gate import build_gate
from interview_mux.journey_orchestrator import (
    NEXT_ACTION_UNDERSTAND_INVESTIGATIONS,
    build_journey_snapshot,
)
from interview_mux.session_log import read_log
from interview_mux.value_analysis.extract import (
    _spine_orchestration_investigations,
    maybe_enqueue_orchestration_investigations,
)
from run_fixtures import isolated_run_ctx, patch_merged_config, populated_analysis_state


def _minimal_spine(*, boundary_events: list[dict] | None = None) -> dict:
    events = boundary_events or []
    normalized_events = []
    for ev in events:
        row = dict(ev)
        row.setdefault("confidence", 0.8)
        row.setdefault("sources", ["test"])
        normalized_events.append(row)
    return {
        "schema_version": 1,
        "derived_from": {
            "normalized_wav": "ingest/normalized.wav",
            "transcript": "transcript/full.json",
            "computed_at": "2026-06-18T00:00:00Z",
            "stage": "interview_spine_build",
        },
        "encoders": {"dsp": "numpy_rms_v1", "clap": None, "ssl": None},
        "window_policy": {"window_sec": 10, "hop_sec": 5, "align_to": "words"},
        "windows": [],
        "boundary_events": normalized_events,
        "retrieval": {
            "enabled": False,
            "model_id": None,
            "sidecar_path": None,
            "vector_dim": None,
            "window_count": 0,
        },
        "speaker_stats": [],
    }


def _seed_duration(ctx, duration_ms: int) -> None:
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                {"text": "start", "start_ms": 0, "end_ms": 1000, "confidence": 0.99},
                {"text": "end", "start_ms": duration_ms - 1000, "end_ms": duration_ms, "confidence": 0.99},
            ],
        },
        skip_handoff=True,
    )


def test_enqueue_dedupe_skips_duplicate_open_item(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "wc_dedupe")
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"investigation_dedupe": True}}})
    base = {
        "kind": "acoustic_anomaly",
        "question": "dup",
        "suggested_action": {"type": "rerun_stage", "stage": "content_context"},
        "target": {"segment_id": "trust_dip_5000", "time_ms": 5000},
    }
    assert enqueue_investigations(ctx, [base], created_by_stage="content_context") == 1
    assert enqueue_investigations(ctx, [base], created_by_stage="content_context") == 0
    queue = load_queue(ctx)
    assert len([it for it in queue["items"] if it["status"] == "open"]) == 1


def test_trust_dip_with_low_confidence_enqueues_item(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "wc_trust")
    patch_merged_config(
        monkeypatch,
        {
            "value_analysis": {"enabled": True},
            "interview_spine": {"enabled": True},
        },
    )
    ctx.write_json(
        "understanding/interview_spine.json",
        _minimal_spine(boundary_events=[{"time_ms": 5000, "type": "trust_dip", "confidence": 0.9}]),
        skip_handoff=True,
    )
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                {"text": "uh", "start_ms": 4800, "end_ms": 5200, "confidence": 0.5},
            ],
        },
        skip_handoff=True,
    )
    items = _spine_orchestration_investigations(ctx)
    assert len(items) == 1
    assert "5000" in items[0]["question"] or "5s" in items[0]["question"]


def test_topic_shift_stub_suppressed_when_orc03_active(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "wc_stub_off")
    _seed_duration(ctx, 31 * 60 * 1000)
    patch_merged_config(
        monkeypatch,
        {
            "value_analysis": {"enabled": True, "orc03_enabled": True},
            "coherence": {"enabled": True, "replace_stub_topic_shift_hints": True},
        },
    )
    ctx.write_json(
        "understanding/interview_spine.json",
        _minimal_spine(boundary_events=[{"time_ms": 900_000, "type": "topic_shift_hint", "confidence": 0.8}]),
        skip_handoff=True,
    )
    assert _spine_orchestration_investigations(ctx) == []


def test_topic_shift_stub_enqueued_when_orc03_inactive(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "wc_stub_on")
    patch_merged_config(
        monkeypatch,
        {
            "value_analysis": {"enabled": True, "orc03_enabled": False},
            "coherence": {"enabled": False},
        },
    )
    ctx.write_json(
        "understanding/interview_spine.json",
        _minimal_spine(boundary_events=[{"time_ms": 60_000, "type": "topic_shift_hint", "confidence": 0.8}]),
        skip_handoff=True,
    )
    items = _spine_orchestration_investigations(ctx)
    assert len(items) == 1
    assert items[0]["kind"] == "topic_drift"


def test_spine_investigations_capped_at_six(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "wc_cap6")
    patch_merged_config(monkeypatch, {"coherence": {"enabled": False}})
    events = [
        {"time_ms": i * 1000, "type": "topic_shift_hint", "confidence": 0.8}
        for i in range(1, 12)
    ]
    ctx.write_json("understanding/interview_spine.json", _minimal_spine(boundary_events=events), skip_handoff=True)
    assert len(_spine_orchestration_investigations(ctx)) == 6


def test_quality_trajectory_flags_capped_at_five(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "wc_cap5")
    patch_merged_config(monkeypatch, {"value_analysis": {"enabled": True}})
    flags = [
        {
            "start_ms": i * 1000,
            "end_ms": i * 1000 + 500,
            "dip_ratio": 0.4,
            "note": f"flag {i}",
        }
        for i in range(10)
    ]
    ctx.write_json(
        "understanding/value_features.json",
        {"profiles": {"transcript": {"quality_trajectory_flags": flags}}},
        skip_handoff=True,
    )
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                {"text": "x", "start_ms": ms, "end_ms": ms + 200, "confidence": 0.5}
                for ms in range(0, 10_000, 1000)
            ],
        },
        skip_handoff=True,
    )
    with patch(
        "interview_mux.stage_enrichment.trust_dip_corroborated",
        return_value=True,
    ):
        count = maybe_enqueue_orchestration_investigations(ctx)
    assert count == 5


def test_orc02_enqueue_logs_structured_line(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "wc_log")
    patch_merged_config(monkeypatch, {"value_analysis": {"enabled": True}, "coherence": {"enabled": False}})
    ctx.write_json(
        "understanding/interview_spine.json",
        _minimal_spine(boundary_events=[{"time_ms": 1000, "type": "topic_shift_hint"}]),
        skip_handoff=True,
    )
    maybe_enqueue_orchestration_investigations(ctx)
    messages = [e.get("message", "") for e in read_log(ctx.run_dir)]
    assert any(m.startswith("investigation_enqueue orc02") for m in messages)
    assert any(m.startswith("investigation_enqueue count=") for m in messages)


def test_short_run_writes_inactive_coherence_report(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "wc_inactive")
    _seed_duration(ctx, 20 * 60 * 1000)
    patch_merged_config(
        monkeypatch,
        {"value_analysis": {"enabled": True, "orc03_enabled": True}, "coherence": {"enabled": True}},
    )
    maybe_run_coherence_analysis(ctx, phase="post_content_context")
    report = ctx.read_json("understanding/coherence_report.json")
    assert report["gate"]["activated"] is False
    assert report.get("risks") == []


@pytest.mark.parametrize(
    ("duration_ms", "expected"),
    [
        (1_800_000 - 1000, False),
        (1_800_000, True),
    ],
)
def test_duration_gate_exact_30m_edge(tmp_path, monkeypatch, duration_ms, expected):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, f"edge_{duration_ms}")
    _seed_duration(ctx, duration_ms)
    gate = build_gate(ctx)
    assert gate["activated"] is expected


def test_drain_rerun_cap_leaves_investigation_open(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "wc_cap_rerun")
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"max_investigation_reruns_per_kind": 1}}},
    )
    ctx.write_json(
        "understanding/investigation_queue.json",
        {
            "items": [
                {
                    "id": "inv_cap",
                    "kind": "topic_drift",
                    "status": "open",
                    "question": "drift",
                    "suggested_action": {"type": "rerun_stage", "stage": "content_context"},
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/analysis_orchestration.json",
        {"investigation_rerun_counts": {"topic_drift": 1}},
        skip_handoff=True,
    )

    drain_investigation_queue(ctx, {"content_context": lambda: None})
    logs = read_log(ctx.run_dir)
    assert any("rerun cap reached" in e.get("message", "") for e in logs)
    queue = ctx.read_json("understanding/investigation_queue.json")
    assert queue["items"][0]["status"] == "open"


def test_journey_snapshot_open_investigations_next_action(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "wc_journey")
    ctx.mark_done("ingest")
    ctx.mark_done("transcript_review")
    ctx.mark_done("content_context")
    ctx.write_json(
        "understanding/investigation_queue.json",
        {
            "items": [
                {
                    "id": "inv_1",
                    "kind": "acoustic_anomaly",
                    "status": "open",
                    "question": "check",
                    "suggested_action": {"type": "rerun_stage", "stage": "content_context"},
                }
            ]
        },
        skip_handoff=True,
    )
    state = populated_analysis_state(ctx.run_id)
    ctx.write_json("understanding/analysis_state.json", state, skip_handoff=True)
    snap = build_journey_snapshot(ctx)
    assert snap.get("open_investigations") == 1
    assert snap.get("phase") == "understand"
    assert snap.get("next_action") == NEXT_ACTION_UNDERSTAND_INVESTIGATIONS


def test_replace_stub_prevents_double_topic_drift_on_long_run(tmp_path, monkeypatch):
    """When ORC-03 active + replace_stub, spine stub is suppressed (WC-12)."""
    ctx = isolated_run_ctx(tmp_path, "wc_ortho")
    _seed_duration(ctx, 31 * 60 * 1000)
    patch_merged_config(
        monkeypatch,
        {
            "value_analysis": {"enabled": True, "orc03_enabled": True},
            "coherence": {"enabled": True, "replace_stub_topic_shift_hints": True},
            "analysis": {"flow_hardening": {"investigation_dedupe": True}},
        },
    )
    window_id = "win_drift_01"
    ctx.write_json(
        "understanding/interview_spine.json",
        _minimal_spine(
            boundary_events=[{"time_ms": 900_000, "type": "topic_shift_hint", "window_id": window_id}],
        ),
        skip_handoff=True,
    )
    stub_items = _spine_orchestration_investigations(ctx)
    assert stub_items == []
    orc03_item = {
        "kind": "topic_drift",
        "question": "drift at 15m",
        "target": {"window_id": window_id},
        "suggested_action": {"type": "rerun_stage", "stage": "content_brief_reanchor"},
    }
    enqueue_investigations(ctx, [orc03_item], created_by_stage="coherence")
    queue = load_queue(ctx)
    open_drifts = [it for it in queue["items"] if it["kind"] == "topic_drift" and it["status"] == "open"]
    assert len(open_drifts) == 1
