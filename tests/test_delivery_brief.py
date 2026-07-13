"""Unit tests for delivery_brief adaptive policy."""

from __future__ import annotations

from pathlib import Path

from interview_mux.delivery_brief import build_delivery_brief, compact_delivery_brief_for_volley
from interview_mux.prompt_validation import validate_delivery_brief
from interview_mux.run_context import RunContext


def test_build_delivery_brief_clamps_and_schema(tmp_path: Path, monkeypatch) -> None:
    run = tmp_path / "exec_test"
    run.mkdir()
    (run / "understanding").mkdir()
    (run / "segments").mkdir()
    (run / "transcript").mkdir()
    (run / "transcript" / "full.json").write_text(
        '{"duration_ms": 3600000}', encoding="utf-8"
    )
    (run / "segments" / "manifest.json").write_text(
        '{"segments": [{"segment_id": "s1"}, {"segment_id": "s2"}, {"segment_id": "s3"}, '
        '{"segment_id": "s4"}, {"segment_id": "s5"}, {"segment_id": "s6"}]}',
        encoding="utf-8",
    )
    (run / "understanding" / "gap_report.json").write_text(
        '{"lines": [{"segment_id": "s1", "delivery": "record", "severity": "high", "script": "Why?"},'
        '{"segment_id": "s2", "delivery": "record", "severity": "low", "script": "Ok?"}]}',
        encoding="utf-8",
    )
    (run / "understanding" / "flow_adaptation.json").write_text(
        '{"sfx_density": {"max_beds": 2, "max_punctuators": 1, "max_foley": 1}, '
        '"ranking_weights": {"narrative_arc_fit": 0.5}, "production_style": "documentary_interview"}',
        encoding="utf-8",
    )
    ctx = RunContext(str(run))
    brief = build_delivery_brief(ctx)
    errs = validate_delivery_brief(brief)
    assert errs == [], errs
    assert brief["question_budget"]["ideal"] >= 1
    assert brief["target_duration_sec"]["ideal"] > 0
    assert brief["sfx_density"]["max_beds"] == 2
    compact = compact_delivery_brief_for_volley(brief)
    assert compact and "question_budget" in compact
