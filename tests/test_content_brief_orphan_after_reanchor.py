"""A segment that leaves the manifest after reanchor must not halt delivery (ISSUES 139).

On a client machine the one-hour source stopped at 36/72: content_brief topics
still cited seg_018, a 1.5-second clip that was in segments/boundaries.json but
no longer in segments/manifest.json. The post_reanchor cross-check called it an
orphan, topic_coverage_audit refused to start, and the attempt memo refused
every retry on the same fingerprint.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx


def _put(ctx, rel: str, doc: dict) -> None:
    dest = ctx.final_path(*rel.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc), encoding="utf-8")


def _get(ctx, rel: str) -> dict:
    return json.loads(ctx.final_path(*rel.split("/")).read_text(encoding="utf-8"))


def _row(sid: str, start: int, end: int) -> dict:
    return {
        "segment_id": sid,
        "start_ms": start,
        "end_ms": end,
        "speaker_id": "spk_1",
        "speaker_role": "interviewee",
        "type": "interviewee_answer",
        "topic_tags": [],
        "text": "It changes how we treat them.",
    }


BOUNDS = [
    _row("seg_017", 0, 60_000),
    _row("seg_018", 60_000, 61_500),
    _row("seg_019", 61_500, 120_000),
    _row("seg_020", 120_000, 180_000),
]


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "exec_brief_orphan")
    _put(c, "segments/boundaries.json", {"boundaries": BOUNDS})
    # seg_018 left the manifest after reanchor; its tape now sits in seg_017.
    _put(
        c,
        "segments/manifest.json",
        {
            "segments": [
                _row("seg_017", 0, 61_500),
                _row("seg_019", 61_500, 120_000),
                _row("seg_020", 120_000, 180_000),
            ]
        },
    )
    _put(
        c,
        "understanding/content_brief.json",
        {
            "thesis": "x",
            "topics": [
                {"name": "a", "summary": "s", "segment_ids": ["seg_018", "seg_020"]},
                {"name": "b", "summary": "s", "segment_ids": ["seg_017", "seg_018"]},
            ],
            "key_claims": [{"claim": "c", "evidence_segment_ids": ["seg_018", "seg_099"]}],
        },
    )
    return c


def _orphans(ctx) -> list[str]:
    from interview_mux.artifact_cross_validate import validate_cross_artifacts

    return [e for e in validate_cross_artifacts(ctx, "post_reanchor") if "orphan" in e]


def test_orphan_points_at_live_segment_carrying_its_tape(ctx) -> None:
    from interview_mux.artifact_repairs import heal_content_brief_orphan_segment_ids

    assert _orphans(ctx)
    mapping = heal_content_brief_orphan_segment_ids(ctx)

    assert mapping == {"seg_018": "seg_017", "seg_099": None}
    brief = _get(ctx, "understanding/content_brief.json")
    assert brief["topics"][0]["segment_ids"] == ["seg_017", "seg_020"]
    assert brief["topics"][1]["segment_ids"] == ["seg_017"]
    assert brief["key_claims"][0]["evidence_segment_ids"] == ["seg_017"]
    assert _orphans(ctx) == []


def test_split_parent_maps_to_overlapping_child(ctx) -> None:
    from interview_mux.artifact_repairs import heal_content_brief_orphan_segment_ids

    _put(
        ctx,
        "segments/manifest.json",
        {
            "segments": [
                _row("seg_017", 0, 60_000),
                _row("seg_018a", 60_000, 61_500),
                _row("seg_019", 61_500, 120_000),
                _row("seg_020", 120_000, 180_000),
            ]
        },
    )
    assert heal_content_brief_orphan_segment_ids(ctx)["seg_018"] == "seg_018a"
    assert _orphans(ctx) == []


def test_no_orphans_leaves_brief_untouched(ctx) -> None:
    from interview_mux.artifact_repairs import heal_content_brief_orphan_segment_ids

    heal_content_brief_orphan_segment_ids(ctx)
    before = ctx.final_path("understanding", "content_brief.json").read_bytes()
    assert heal_content_brief_orphan_segment_ids(ctx) == {}
    assert ctx.final_path("understanding", "content_brief.json").read_bytes() == before


def test_topic_coverage_audit_input_check_has_no_orphan_block(ctx) -> None:
    from interview_mux.stage_input_checks import collect_stage_input_issues

    issues = collect_stage_input_issues(ctx, "topic_coverage_audit")
    assert not [i.message for i in issues if "orphan" in i.message]


# The same class past the brief: any cross-check that would halt on a stale id
# repairs the ids it names, then re-checks.


def _evals(ids: list[str]) -> dict:
    return {"evaluations": [{"segment_id": s, "self_explanatory": True} for s in ids]}


def test_post_gaps_stale_evaluation_id_is_repaired_before_halting(ctx) -> None:
    from interview_mux.artifact_cross_validate import (
        validate_cross_artifacts,
        validate_cross_artifacts_healing,
    )

    _put(ctx, "understanding/gap_evaluations.json", _evals(["seg_017", "seg_018", "seg_019"]))
    assert validate_cross_artifacts(ctx, "post_gaps") == [
        "gap_evaluation segment_id seg_018 not in manifest"
    ]
    assert validate_cross_artifacts_healing(ctx, "post_gaps") == []
    ids = [r["segment_id"] for r in _get(ctx, "understanding/gap_evaluations.json")["evaluations"]]
    assert ids == ["seg_017", "seg_017", "seg_019"]


def test_vernacular_child_id_resolves_from_resplit_report(ctx) -> None:
    from interview_mux.artifact_repairs import resolve_stale_segment_ids

    _put(
        ctx,
        "vernacular/resplit_report.json",
        {
            "rows": [
                {
                    "parent": "seg_019",
                    "children": [
                        {"segment_id": "seg_019a", "start_ms": 61_500, "end_ms": 62_400},
                        {"segment_id": "seg_019b", "start_ms": 62_400, "end_ms": 120_000},
                    ],
                }
            ]
        },
    )
    assert resolve_stale_segment_ids(ctx, ["seg_019a", "seg_019"]) == {"seg_019a": "seg_019"}


def test_fuse_remap_wins_over_span(ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux import segment_fuse
    from interview_mux.artifact_repairs import resolve_stale_segment_ids

    monkeypatch.setattr(segment_fuse, "fused_id_remap", lambda _ctx: {"seg_018": "seg_019"})
    assert resolve_stale_segment_ids(ctx, ["seg_018"]) == {"seg_018": "seg_019"}


def test_unrelated_errors_touch_nothing(ctx) -> None:
    from interview_mux.artifact_repairs import heal_stale_segment_refs_from_errors

    before = ctx.final_path("understanding", "content_brief.json").read_bytes()
    assert heal_stale_segment_refs_from_errors(ctx, ["content_brief.json missing thesis"]) == {}
    assert ctx.final_path("understanding", "content_brief.json").read_bytes() == before


def test_palette_stale_ids_route_to_the_sound_design_plan() -> None:
    from interview_mux.artifact_repairs import _stale_ref_targets

    assert _stale_ref_targets(["palette segment seg_009 not in manifest"]) == {
        "understanding/sound_design_plan.json": {"seg_009"}
    }


def test_a_skipped_write_is_not_reported_as_healed(ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    """A gate below the ownership table (the seat freeze) can skip and return normally."""
    from interview_mux import artifact_repairs
    from interview_mux.artifact_repairs import heal_stale_segment_refs_from_errors

    _put(ctx, "understanding/gap_evaluations.json", _evals(["seg_018"]))
    monkeypatch.setattr(artifact_repairs, "persist_segment_id_remap", lambda c, rel, doc: True)
    assert heal_stale_segment_refs_from_errors(
        ctx, ["gap_evaluation segment_id seg_018 not in manifest"]
    ) == {}
