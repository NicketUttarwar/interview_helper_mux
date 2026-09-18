"""Unit tests for delivery_brief adaptive policy."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux import artifact_lifecycle as al
from interview_mux.artifact_lifecycle import LifecyclePhase, run_phase_checks
from interview_mux.defect_ledger import read_defect_ledger
from interview_mux.delivery_brief import build_delivery_brief, compact_delivery_brief_for_volley
from interview_mux.prompt_validation import validate_delivery_brief
from interview_mux.run_context import RunContext
from interview_mux.stage_contract import load_contract
from run_fixtures import isolated_run_ctx


_GAP_REPORT = "understanding/gap_report.json"
_BRIEF_STAGE = "delivery_brief_build"


def test_delivery_brief_contract_drops_circular_gap_compose_consumer() -> None:
    """DBB-B1: gap_framing_compose seeds before brief — not a downstream consumer."""
    contract = load_contract(_BRIEF_STAGE)
    assert contract is not None
    assert "gap_framing_compose" not in (contract.consumers or [])


def test_delivery_brief_missing_gap_report_prestage_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DBB-B2: hard gap_report absent → recorded prestage refusal, not a crash."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.delenv("MUX_CONTRACT_HARD_INPUT_STRICT", raising=False)
    ctx = isolated_run_ctx(tmp_path, "dbb_missing_gap")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "run_mode": "full-auto"},
        skip_handoff=True,
    )
    assert not ctx.artifact_exists(_GAP_REPORT)

    contract = load_contract(_BRIEF_STAGE)
    assert contract is not None
    hard_gap = [
        d
        for d in contract.inputs
        if d.hard and d.path == _GAP_REPORT and not d.when
    ]
    assert hard_gap, "delivery_brief_build must hard-require gap_report"
    assert hard_gap[0].producer == "gap_framing_compose"

    errors = run_phase_checks(ctx, _BRIEF_STAGE, LifecyclePhase.PRESTAGE)
    assert errors == [], "absent hard input must refuse, not raise via PRESTAGE errors"

    refusals = al.prestage_refusals(ctx, _BRIEF_STAGE)
    assert any(
        r.get("blocker") == al.MISSING_HARD_INPUT_BLOCKER
        and r.get("artifact") == _GAP_REPORT
        for r in refusals
    ), refusals

    defects = (read_defect_ledger(ctx).get("defects") or {}).values()
    rows = [
        row
        for row in defects
        if row.get("blocker") == al.MISSING_HARD_INPUT_BLOCKER
        and row.get("artifact") == _GAP_REPORT
        and row.get("stage") == _BRIEF_STAGE
    ]
    assert rows, "missing hard gap_report must leave a defect row"


def test_build_delivery_brief_from_words_when_duration_ms_missing(
    tmp_path: Path, monkeypatch
) -> None:
    """Regression: words-only transcripts must not collapse ideal to min_duration_sec."""
    run = tmp_path / "exec_words"
    run.mkdir()
    (run / "understanding").mkdir()
    (run / "segments").mkdir()
    (run / "transcript").mkdir()
    # ~56 min interview — same shape as MLX STT (words, no top-level duration_ms)
    (run / "transcript" / "full.json").write_text(
        '{"text": "hello", "words": ['
        '{"text": "So", "start_ms": 5140, "end_ms": 5740},'
        '{"text": "way", "start_ms": 3347610, "end_ms": 3347850}'
        "]}",
        encoding="utf-8",
    )
    (run / "segments" / "manifest.json").write_text(
        '{"segments": [{"segment_id": "s1"}, {"segment_id": "s2"}, {"segment_id": "s3"}, '
        '{"segment_id": "s4"}, {"segment_id": "s5"}, {"segment_id": "s6"}]}',
        encoding="utf-8",
    )
    (run / "understanding" / "gap_report.json").write_text(
        '{"lines": []}', encoding="utf-8"
    )
    ctx = RunContext(str(run))
    brief = build_delivery_brief(ctx)
    assert brief["source_duration_ms"] == 3347850
    # ideal ≈ 65% of ~3347s → ~2176s, not the 600s min_duration_sec fallback
    assert brief["target_duration_sec"]["ideal"] > 2000
    assert brief["target_duration_sec"]["ideal"] < 2500


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
