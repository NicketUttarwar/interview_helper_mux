"""A host present only as reactions is not a starved host packet (ISSUES 103)."""

from __future__ import annotations

import json

from run_fixtures import isolated_run_ctx

from interview_mux.llm_preflight import _preflight_missing_framing


def _seed(ctx, host_types: list[str]) -> None:
    sp = ctx.final_path("understanding", "speakers.json")
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(
        json.dumps(
            {
                "speakers": [
                    {"speaker_id": "spk_0", "role": "interviewee"},
                    {"speaker_id": "spk_2", "role": "interviewer"},
                ]
            }
        ),
        encoding="utf-8",
    )
    segs = [
        {
            "segment_id": f"seg_{i:03d}",
            "start_ms": i * 10_000,
            "end_ms": i * 10_000 + 9_000,
            "text": "words",
            "type": "interviewee_answer",
            "speaker_id": "spk_0",
            "speaker_role": "interviewee",
            "topic_tags": [],
        }
        for i in range(1, 5)
    ]
    for j, typ in enumerate(host_types):
        segs.append(
            {
                "segment_id": f"seg_h{j}",
                "start_ms": 100_000 + j * 2_000,
                "end_ms": 100_000 + j * 2_000 + 1_500,
                "text": "Right.",
                "type": typ,
                "speaker_id": "spk_2",
                "speaker_role": "interviewer",
                "topic_tags": [],
            }
        )
    man = ctx.final_path("segments", "manifest.json")
    man.parent.mkdir(parents=True, exist_ok=True)
    man.write_text(json.dumps({"version": 1, "segments": segs}), encoding="utf-8")


def _starved(errors: list[str]) -> bool:
    return any("starved_host_packet" in e for e in errors)


def test_reaction_rows_count_as_host_tape(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_host_reactions")
    _seed(ctx, ["interviewer_reaction", "interviewer_reaction"])
    assert not _starved(_preflight_missing_framing(ctx))


def test_no_host_rows_at_all_is_still_starved(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_host_absent")
    _seed(ctx, [])
    assert _starved(_preflight_missing_framing(ctx))


def test_question_rows_still_count(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_host_questions")
    _seed(ctx, ["interviewer_question"])
    assert not _starved(_preflight_missing_framing(ctx))
