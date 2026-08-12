"""Adaptive mono/multi segment-type allowance."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.classification_obligation import allows_all_interviewee_answer
from interview_mux.deterministic_lint import _lint_segment_classification
from run_fixtures import isolated_run_ctx


def test_allows_all_interviewee_answer_monologue(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_mono")
    ctx.write_json(
        "understanding/source_topology.json",
        {
            "topology_class": "monologue_heavy",
            "speaker_stats": [
                {"speaker_id": "spk_1", "talk_ratio": 0.95, "role_hint": "interviewee"},
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9},
            ],
        },
        skip_handoff=True,
    )
    assert allows_all_interviewee_answer(ctx).allowed is True


def test_requires_diversity_for_qa_frame(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_qa")
    ctx.write_json(
        "understanding/source_topology.json",
        {
            "topology_class": "one_on_one_asymmetric",
            "speaker_stats": [
                {"speaker_id": "spk_1", "talk_ratio": 0.70, "role_hint": "interviewee"},
                {"speaker_id": "spk_0", "talk_ratio": 0.30, "role_hint": "interviewer", "question_count": 5},
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9},
            ],
        },
        skip_handoff=True,
    )
    assert allows_all_interviewee_answer(ctx).allowed is False


def test_lint_allows_mono_all_answers(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_lint_mono")
    ctx.write_json(
        "understanding/source_topology.json",
        {
            "topology_class": "monologue_heavy",
            "speaker_stats": [{"speaker_id": "spk_1", "talk_ratio": 0.9, "role_hint": "interviewee"}],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/speakers.json",
        {"speakers": [{"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9}]},
        skip_handoff=True,
    )
    arts = {
        "segments": [
            {"segment_id": "seg_001", "type": "interviewee_answer"},
            {"segment_id": "seg_002", "type": "interviewee_answer"},
        ]
    }
    assert _lint_segment_classification(arts, ctx) == []


def test_lint_flags_qa_all_answers(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_lint_qa")
    ctx.write_json(
        "understanding/source_topology.json",
        {
            "topology_class": "one_on_one_asymmetric",
            "speaker_stats": [
                {"speaker_id": "spk_1", "talk_ratio": 0.65, "role_hint": "interviewee"},
                {"speaker_id": "spk_0", "talk_ratio": 0.35, "role_hint": "interviewer"},
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9},
            ],
        },
        skip_handoff=True,
    )
    arts = {
        "segments": [
            {"segment_id": "seg_001", "type": "interviewee_answer"},
            {"segment_id": "seg_002", "type": "interviewee_answer"},
        ]
    }
    errs = _lint_segment_classification(arts, ctx)
    assert any("all segments typed interviewee_answer" in e for e in errs)
