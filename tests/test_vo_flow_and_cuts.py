"""Regression tests for exec_1577 VO loop / mid-sentence / cold-open layup failures."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_repairs import (
    _drop_redundant_remapped_seeds,
    _enforce_min_vo_insert_ratio,
    repair_gap_report,
)
from interview_mux.bridge_completeness import missing_reorder_bridges
from interview_mux.gap_framing import (
    choose_seam_synthetic,
    drop_contiguous_light_bridge_lines,
    transition_redundant_with_framing,
)
from interview_mux.gap_vo_prior_context import (
    cold_open_layup_ok,
    has_forward_cue,
    vo_value_violations,
)
from interview_mux.seam_glue import default_bridge_text, mint_missing_transitions
from interview_mux.stages.assembly import _gap_lines_for_segment, build_flow1_edl
from interview_mux import config as config_mod
from run_fixtures import isolated_run_ctx, write_fixture_json


def test_gap_lines_for_segment_dedupes_line_id(tmp_path: Path) -> None:
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_seed_seg_013",
                "targets_segment_id": "seg_014",
                "placement": "before",
                "delivery": "synthesize",
                "text": "What reshaped the buyer demand?",
            }
            for _ in range(4)
        ]
    }
    emitted_ids: set[str] = set()
    emitted_sentences: set[str] = set()
    lines = _gap_lines_for_segment(
        gap,
        "seg_014",
        "before",
        emitted_line_ids=emitted_ids,
        emitted_sentence_keys=emitted_sentences,
    )
    assert len(lines) == 1
    assert list(emitted_ids) == ["vo_seed_seg_013"]

    vo_files: dict[str, Path] = {}
    p = tmp_path / "vo_seed_seg_013.wav"
    p.write_bytes(b"\x00")
    vo_files["vo_seed_seg_013"] = p
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_013", "seg_014"]},
        segments_by_id={
            "seg_013": {
                "segment_id": "seg_013",
                "speaker_id": "spk_a",
                "start_ms": 0,
                "end_ms": 300,
                "text": "Within",
            },
            "seg_014": {
                "segment_id": "seg_014",
                "speaker_id": "spk_b",
                "start_ms": 10_000,
                "end_ms": 20_000,
                "text": "We sold the company.",
            },
        },
        gap_report=gap,
        resolve_vo_path=lambda line: vo_files.get(str(line.get("line_id") or "")),
        vo_duration_ms=lambda _p: 1500,
    )
    vo_clips = [c for c in edl["clips"] if c.get("type") == "vo_pickup"]
    assert len(vo_clips) == 1
    assert vo_clips[0]["line_id"] == "vo_seed_seg_013"


def test_drop_contiguous_vo_same_speaker() -> None:
    segs = {
        "seg_008": {
            "segment_id": "seg_008",
            "speaker_id": "spk_0",
            "start_ms": 0,
            "end_ms": 8_000,
            "text": "We kept investing.",
        },
        "seg_009": {
            "segment_id": "seg_009",
            "speaker_id": "spk_0",
            "start_ms": 8_200,
            "end_ms": 16_000,
            "text": "Even when cash was thin.",
        },
        "seg_010": {
            "segment_id": "seg_010",
            "speaker_id": "spk_0",
            "start_ms": 16_300,
            "end_ms": 24_000,
            "text": "That became the turning point.",
        },
    }
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_q_seg_009",
                "targets_segment_id": "seg_009",
                "placement": "before",
                "delivery": "synthesize",
                "gap_type": "missing_followup",
                "line_category": "framing_question",
                "text": "What forced that?",
            },
            {
                "line_id": "vo_density_seg_010",
                "targets_segment_id": "seg_010",
                "placement": "before",
                "delivery": "synthesize",
                "gap_type": "missing_followup",
                "density_forced": True,
                "text": "What was the turning point as we get to 010?",
            },
        ]
    }
    cleaned, notes = drop_contiguous_light_bridge_lines(
        gap, segs, ordered_segment_ids=["seg_008", "seg_009", "seg_010"]
    )
    assert notes
    assert cleaned["interviewer_lines"] == []


def test_high_gap_seed_skips_when_real_vo_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "high_gap_seed")
    segs = [
        {
            "segment_id": "seg_013",
            "speaker_id": "spk_0",
            "speaker_role": "interviewee",
            "type": "interviewee_answer",
            "topic_tags": [],
            "start_ms": 0,
            "end_ms": 400,
            "text": "Within",
        },
        {
            "segment_id": "seg_014",
            "speaker_id": "spk_1",
            "speaker_role": "interviewee",
            "type": "interviewee_answer",
            "topic_tags": [],
            "start_ms": 5_000,
            "end_ms": 15_000,
            "text": "We closed the acquisition in under a year.",
        },
    ]
    path = ctx.path("segments", "manifest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    path.write_text(json.dumps({"segments": segs}), encoding="utf-8")
    path2 = ctx.path("master", "selection.json")
    path2.parent.mkdir(parents=True, exist_ok=True)
    path2.write_text(json.dumps({"ordered_segment_ids": ["seg_013", "seg_014"]}), encoding="utf-8")
    path3 = ctx.path("understanding", "gap_evaluations.json")
    path3.parent.mkdir(parents=True, exist_ok=True)
    path3.write_text(
        json.dumps(
            {
                "evaluations": [
                    {
                        "segment_id": "seg_013",
                        "severity": "high",
                        "gap_type": "missing_followup",
                        "listener_confusion": "needs a prompt",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = {
        "interviewer_lines": [
            {
                "line_id": "vo_q_seg_014",
                "targets_segment_id": "seg_014",
                "placement": "before",
                "delivery": "synthesize",
                "text": "What made that deal possible?",
                "rationale": "cue acquisition",
            },
            {
                "line_id": "vo_seed_seg_013",
                "targets_segment_id": "seg_014",
                "placement": "before",
                "delivery": "synthesize",
                "text": "What changed next?",
                "rationale": "remapped seed",
            },
        ]
    }
    applied: list[dict] = []
    _drop_redundant_remapped_seeds(out, applied=applied)
    assert any(a.get("action") == "drop_redundant_remapped_seed" for a in applied)
    assert all(ln.get("line_id") != "vo_seed_seg_013" for ln in out["interviewer_lines"])

    _patched, applied2 = repair_gap_report(ctx, out)
    assert not any(a.get("action") == "seed_high_gap_line" for a in applied2)


def test_density_floor_does_not_break_monologue(monkeypatch) -> None:
    monkeypatch.setattr(
        config_mod,
        "merged_config",
        lambda: {"analysis": {"gap_framing": {"min_vo_insert_ratio": 0.25}}},
    )
    ordered = [f"seg_{i:03d}" for i in range(1, 9)]
    segs = [
        {
            "segment_id": sid,
            "speaker_id": "spk_guest",
            "start_ms": i * 10_000,
            "end_ms": (i + 1) * 10_000,
            "text": f"Long same-speaker answer part {i} with enough words.",
        }
        for i, sid in enumerate(ordered)
    ]

    class _Ctx:
        def __init__(self):
            self._arts = {
                "master/selection.json": {"ordered_segment_ids": ordered},
                "master/narrative_plan.json": {"chapters": []},
                "segments/manifest.json": {"segments": segs},
            }

        def artifact_exists(self, rel: str) -> bool:
            return rel in self._arts

        def read_json(self, rel: str):
            return self._arts[rel]

    out: dict = {"interviewer_lines": []}
    applied: list[dict] = []
    _enforce_min_vo_insert_ratio(_Ctx(), out, applied=applied)
    # Same-speaker contiguous run: density must not invent mid-monologue breaks.
    assert not any(
        str(a.get("action") or "").startswith("seed_vo_density")
        and str(a.get("segment_id") or "") in set(ordered[1:-1])
        for a in applied
    )


def test_transition_skipped_when_before_vo_exists(tmp_path, monkeypatch) -> None:
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_q_seg_020",
                "targets_segment_id": "seg_020",
                "placement": "before",
                "delivery": "synthesize",
                "line_category": "framing_question",
                "text": "What changed next?",
            }
        ]
    }
    assert transition_redundant_with_framing(gap, "seg_019", "seg_020") is True
    bridges = {
        "pairs": [
            {
                "after_id": "seg_019",
                "before_id": "seg_020",
                "after_segment_id": "seg_019",
                "before_segment_id": "seg_020",
                "kind": "reorder",
                "source_gap_ms": -50_000,
            }
        ]
    }
    assert missing_reorder_bridges(bridges, gap_report=gap) == []

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "seam_skip")
    import json

    gr_path = ctx.path("understanding", "gap_report.json")
    gr_path.parent.mkdir(parents=True, exist_ok=True)
    gr_path.write_text(json.dumps(gap), encoding="utf-8")
    doc = mint_missing_transitions(
        ctx,
        [
            {
                "after_segment_id": "seg_019",
                "before_segment_id": "seg_020",
                "kind": "reorder",
                "source_gap_ms": -50_000,
                "before_excerpt": "limited resources and we could do only so much",
            }
        ],
        transitions={"transitions": []},
    )
    assert doc["transitions"] == []
    text = default_bridge_text(
        {
            "after_segment_id": "seg_019",
            "before_segment_id": "seg_020",
            "before_excerpt": "limited resources and we could do only so much",
        }
    )
    assert "limited resources" not in text.lower()


def test_mint_uses_passed_gap_when_disk_layup_would_suppress(tmp_path, monkeypatch) -> None:
    """Disk layup still active must not suppress mint when in-memory gap skipped it.

    EDL repair marks overlap VO ``skipped_optional`` in memory; mint used to
    re-read committed gap (unskipped) and skip minting while assert still saw
    the seam as uncovered — bridge_completeness thrash.
    """
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "mint_gap_mismatch")
    orig_write = ctx.write_json

    def _owner_writes(rel, data, **kwargs):
        rel_n = str(rel or "").replace("\\", "/")
        if rel_n == "master/transitions.json":
            kwargs["stage_key"] = "transitions"
        elif rel_n == "understanding/gap_report.json":
            kwargs.setdefault("stage_key", "gap_report_sanitize")
        return orig_write(rel, data, **kwargs)

    ctx.write_json = _owner_writes  # type: ignore[method-assign]
    ctx._one_writer_raw = True  # type: ignore[attr-defined]

    def _persist_transitions(c, doc, **_kwargs):
        write_fixture_json(c, "master/transitions.json", doc)
        return doc

    monkeypatch.setattr(
        "interview_mux.transition_vo.persist_transitions_doc",
        _persist_transitions,
    )
    import json

    disk_gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_024",
                "targets_segment_id": "seg_024",
                "prior_segment_id": "seg_023",
                "placement": "before",
                "delivery": "synthesize",
                "text": "The proposed answer to that clinical dilemma is sequencing.",
            }
        ]
    }
    memory_gap = {
        "interviewer_lines": [
            {
                **disk_gap["interviewer_lines"][0],
                "skipped_optional": True,
            }
        ]
    }
    gr_path = ctx.path("understanding", "gap_report.json")
    gr_path.parent.mkdir(parents=True, exist_ok=True)
    gr_path.write_text(json.dumps(disk_gap), encoding="utf-8")
    man = ctx.path("segments", "manifest.json")
    man.parent.mkdir(parents=True, exist_ok=True)
    man.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "segment_id": "seg_023",
                        "text": "Clinicians face an impossible sampling tradeoff.",
                        "start_ms": 0,
                        "end_ms": 4000,
                    },
                    {
                        "segment_id": "seg_024",
                        "text": "Single-cell sequencing plus AI can close that gap.",
                        "start_ms": 5000,
                        "end_ms": 9000,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    missing = [
        {
            "after_segment_id": "seg_023",
            "before_segment_id": "seg_024",
            "kind": "reorder",
            "source_gap_ms": 1000,
            "before_excerpt": "Single-cell sequencing plus AI can close that gap.",
            "after_excerpt": "Clinicians face an impossible sampling tradeoff.",
        }
    ]
    # Disk-only path still suppresses (layup present).
    suppressed = mint_missing_transitions(
        ctx, missing, transitions={"transitions": []}
    )
    assert suppressed["transitions"] == []
    # Same missing list with repaired in-memory gap must mint.
    minted = mint_missing_transitions(
        ctx,
        missing,
        transitions={"transitions": []},
        gap_report=memory_gap,
    )
    keys = {
        (
            str(t.get("after_segment_id") or ""),
            str(t.get("before_segment_id") or ""),
        )
        for t in minted.get("transitions") or []
    }
    assert ("seg_023", "seg_024") in keys
    assert any(str(t.get("text") or "").strip() for t in minted["transitions"])


def test_default_bridge_never_speaks_internal_segment_ids() -> None:
    pair = {
        "after_segment_id": "seg_152",
        "before_segment_id": "seg_153",
        "kind": "reorder",
        "source_gap_ms": 2_000,
    }
    text = default_bridge_text(pair)
    assert text == ""
    assert "152" not in text
    assert "153" not in text
    assert "seg_" not in text.lower()


def test_default_bridge_uses_listener_facing_topics_not_ids() -> None:
    text = default_bridge_text(
        {
            "after_segment_id": "seg_166",
            "before_segment_id": "seg_167",
            "after_topic": "fundraising constraints",
            "before_topic": "the strategic sale",
        }
    )
    assert text == (
        "Moving from fundraising constraints to the strategic sale, what changed?"
    )
    assert "166" not in text
    assert "167" not in text


def test_listener_topic_rejects_snake_case_pipeline_tags() -> None:
    """chapter_close_hitch topic_tags must not become spoken bridge copy."""
    from interview_mux.seam_glue import enrich_bridge_pair_excerpts

    pair = enrich_bridge_pair_excerpts(
        {"after_segment_id": "seg_022", "before_segment_id": "seg_026"},
        {
            "seg_022": {
                "segment_id": "seg_022",
                "topic_tags": ["chapter_close_hitch"],
                "text": (
                    "What if I found a CTC and the doctor is saying, so what? "
                    "Unless you can profile that cell further."
                ),
            },
            "seg_026": {
                "segment_id": "seg_026",
                "topic_tags": ["chapter_close_hitch"],
                "text": (
                    "Okay. So, traditional circulating tumor cell CTC, the end "
                    "point was enumeration alone."
                ),
            },
        },
    )
    assert "chapter_close_hitch" not in str(pair.get("after_topic") or "")
    assert "chapter_close_hitch" not in str(pair.get("before_topic") or "")
    text = default_bridge_text(pair)
    assert text
    assert "chapter_close_hitch" not in text
    # Collision with a prior identical hinge must not resurrect the tag label.
    assert default_bridge_text(pair, used_texts={text}) == ""


def test_default_bridge_derives_topics_from_transcript() -> None:
    from interview_mux.seam_glue import enrich_bridge_pair_excerpts

    pair = enrich_bridge_pair_excerpts(
        {"after_segment_id": "seg_077", "before_segment_id": "seg_079"},
        {
            "seg_077": {
                "segment_id": "seg_077",
                "text": (
                    "Our ultimate goal is a simple blood draw to detect way early "
                    "and reduce waiting on a CT scan."
                ),
            },
            "seg_079": {
                "segment_id": "seg_079",
                "text": (
                    "We've been living through tissue biopsies and then liquid "
                    "biopsies, and now single cell precision."
                ),
            },
        },
    )
    text = default_bridge_text(pair)
    assert text
    assert "next beat" not in text.lower()
    assert "seg_" not in text.lower()
    low = text.lower()
    assert "blood draw" in low or "liquid" in low or "moving from" in low


def test_cold_open_last_sentence_cues_first_native() -> None:
    line = {
        "line_id": "vo_q_seg_001",
        "line_category": "episode_preface",
        "targets_segment_id": "seg_001",
        "text": (
            "Welcome to the room with founders who bootstrapped Max Protein. "
            "What was the origin spark that started it all?"
        ),
        "rationale": "cold open",
    }
    target = "We were looking at M&A as the clean exit path after the ₹150 crore run."
    assert cold_open_layup_ok(line, target_text=target, ordered_ids=["seg_001"]) is False
    errs = vo_value_violations(
        [line],
        segments_by_id={"seg_001": {"segment_id": "seg_001", "text": target}},
        ordered_ids=["seg_001"],
    )
    assert any("cold-open" in e or "forward cue" in e or "origin" in e.lower() for e in errs)


def test_preface_abstract_quiz_closer_fails_and_repairs_declarative() -> None:
    """exec_017-style quiz hinge must fail cold-open and repair to a statement."""
    from interview_mux.gap_vo_prior_context import repair_last_sentence_layup

    line = {
        "line_id": "vo_preface_act1",
        "line_category": "episode_preface",
        "targets_segment_id": "seg_005",
        "text": (
            "Precision oncology relies on information about a tumour, yet the way "
            "that information is collected shapes what can be learned. What does "
            "the conventional route ask of a patient?"
        ),
    }
    target = (
        "A tissue biopsy takes a sample from a suspected cancer site, but it is "
        "invasive and can be costly."
    )
    assert cold_open_layup_ok(line, target_text=target, ordered_ids=["seg_005"]) is False
    fixed = repair_last_sentence_layup(
        line["text"],
        category="episode_preface",
        target_text=target,
        target_segment_id="seg_005",
    )
    assert not fixed.rstrip().endswith("?")
    assert cold_open_layup_ok(
        {**line, "text": fixed},
        target_text=target,
        ordered_ids=["seg_005"],
    )


def test_spoken_layup_allows_free_form_ending() -> None:
    line = {
        "line_id": "vo_sum_seg_010",
        "line_category": "story_bridge",
        "targets_segment_id": "seg_010",
        "text": "They had already put everything back into the company.",
        "rationale": "summary only",
    }
    assert has_forward_cue(line["text"]) is False
    errs = vo_value_violations(
        [line],
        segments_by_id={
            "seg_010": {
                "segment_id": "seg_010",
                "text": "But those were limited resources and we could do only so much.",
            }
        },
        ordered_ids=["seg_009", "seg_010"],
    )
    assert not any("forward cue" in e for e in errs)


def test_repair_last_sentence_layup_preserves_free_form_ending() -> None:
    """Single factual sentence may stay cue-less — no stock hinge append."""
    from interview_mux.gap_vo_prior_context import repair_last_sentence_layup

    fixed = repair_last_sentence_layup(
        "Trial enrolment is only the first decision.",
        prior=None,
        category="story_bridge",
        target_text="Imaging still takes months.",
        target_segment_id="seg_044",
    )
    assert "Trial enrolment is only the first decision" in fixed
    assert "beat lands" not in fixed.lower()
    assert "let's hear" not in fixed.lower()


def test_choose_seam_synthetic_layup_wins_over_transition() -> None:
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_036",
                "targets_segment_id": "seg_036",
                "placement": "before",
                "delivery": "synthesize",
                "text": "Here is how a live cell becomes actionable.",
            }
        ]
    }
    transitions = {
        "transitions": [
            {
                "after_segment_id": "seg_035",
                "before_segment_id": "seg_036",
                "text": "That capture model is the setup — next, what a live cell actually lets you do.",
            }
        ]
    }
    choice = choose_seam_synthetic(
        "seg_035",
        "seg_036",
        gap_report=gap,
        transitions_doc=transitions,
    )
    assert choice["kind"] == "layup"
    assert choice["line_id"] == "vo_layup_seg_036"
    assert transition_redundant_with_framing(gap, "seg_035", "seg_036") is True


def test_choose_seam_synthetic_skipped_layup_yields_transition() -> None:
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_036",
                "targets_segment_id": "seg_036",
                "placement": "before",
                "delivery": "synthesize",
                "skipped_optional": True,
                "text": "The native describes the claimed data?",
            }
        ]
    }
    transitions = {
        "transitions": [
            {
                "after_segment_id": "seg_035",
                "before_segment_id": "seg_036",
                "text": "That capture model is the setup — next, what a live cell actually lets you do.",
            }
        ]
    }
    choice = choose_seam_synthetic(
        "seg_035",
        "seg_036",
        gap_report=gap,
        transitions_doc=transitions,
    )
    assert choice["kind"] == "transition"
    assert "live cell" in (choice.get("text") or "")
    assert transition_redundant_with_framing(gap, "seg_035", "seg_036") is False
