"""Chapter-close hitch: last-listen-complete recut, remap, latch, budget, authority."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from interview_mux.chapter_close_hitch import (
    INTENT_REL,
    LATCH_REL,
    NARRATIVE_REL,
    QC_PLAN_REL,
    REMAP_REL,
    STAGE_ID,
    apply_chapter_authority,
    apply_segment_id_map,
    build_segment_remap,
    compose_segment_maps,
    compute_recut_windows,
    hitch_latch_committed,
    last_listen_complete_end_ms,
    reattach_vo_to_gap_report,
    rebind_vo_pickup_files,
    remap_omit_ledger,
    rewrite_embedded_segment_ids,
    run_chapter_close_hitch,
    run_inner_walk,
    rewrite_upstream_segment_refs,
)
from interview_mux.homunculus.agenda import skip_stage
from interview_mux.homunculus.ledger import append_ledger, count_identity
from interview_mux.homunculus.loop import nested_chat_create
from interview_mux.pipeline import run_single_stage
from interview_mux.run_context import RunContext
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER
from run_fixtures import patch_executions_root


def _tok(start: int, end: int, text: str) -> dict:
    return {"start_ms": start, "end_ms": end, "text": text, "word": text}


def _close_words() -> list[dict]:
    """First legal hinge at intro. (~3500ms / 1s+ pause), payoff at completely. (17000)."""
    return [
        _tok(0, 400, "This"),
        _tok(400, 700, "is"),
        _tok(700, 1000, "the"),
        _tok(1000, 3500, "intro."),
        _tok(4800, 5200, "And"),
        _tok(5200, 5600, "we"),
        _tok(5600, 6200, "prove"),
        _tok(6200, 6600, "the"),
        _tok(6600, 7200, "talking"),
        _tok(7200, 7800, "point"),
        _tok(7800, 17000, "completely."),
        _tok(20000, 20400, "Next"),
        _tok(20400, 21000, "keeper."),
    ]


def _plan(*chapters: dict) -> dict:
    return {
        "arc_summary": "Test arc.",
        "chapters": list(chapters),
        "ordering_constraints": [],
    }


def _chapter(cid: str, title: str, ids: list[str]) -> dict:
    return {
        "chapter_id": cid,
        "title": title,
        "suggested_open_segment_id": ids[0],
        "segment_ids": ids,
    }


def _ctx(tmp_path, monkeypatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("exec_hitch_001_20260101T000000Z", create=True)


def test_last_listen_complete_prefers_payoff_over_first_pause() -> None:
    words = _close_words()
    end = last_listen_complete_end_ms(words, start_ms=0, bound_end_ms=19_920)
    assert end == 17_000


def test_recut_interior_does_not_absorb_next_keeper() -> None:
    keepers = [
        {
            "segment_id": "seg_001",
            "start_ms": 0,
            "end_ms": 4_000,
            "talking_point_id": "tp_a",
        },
        {
            "segment_id": "seg_002",
            "start_ms": 20_000,
            "end_ms": 28_000,
            "talking_point_id": "tp_a",
        },
    ]
    plan = _plan(_chapter("ch1", "One", ["seg_001", "seg_002"]))
    windows = compute_recut_windows(
        keepers=keepers,
        plan=plan,
        words=_close_words(),
        max_cut_ms=180_000,
        next_keeper_eps_ms=80,
    )
    assert windows[0]["end_ms"] == 17_000
    assert windows[0]["end_ms"] < 20_000 - 80
    assert windows[1]["start_ms"] == 20_000
    assert windows[0]["last_in_chapter"] is False


def test_recut_last_in_chapter_extends_toward_close() -> None:
    keepers = [
        {
            "segment_id": "seg_001",
            "start_ms": 0,
            "end_ms": 4_000,
            "talking_point_id": "tp_a",
        },
        {
            "segment_id": "seg_002",
            "start_ms": 40_000,
            "end_ms": 48_000,
            "talking_point_id": "tp_b",
        },
    ]
    plan = _plan(
        _chapter("ch1", "First", ["seg_001"]),
        _chapter("ch2", "Second", ["seg_002"]),
    )
    words = [w for w in _close_words() if int(w["start_ms"]) < 19_000]
    windows = compute_recut_windows(
        keepers=keepers,
        plan=plan,
        words=words,
        max_cut_ms=180_000,
        next_keeper_eps_ms=80,
    )
    assert windows[0]["last_in_chapter"] is True
    assert windows[0]["end_ms"] == 17_000
    assert windows[0]["end_ms"] > 4_000


def test_recut_extends_hanging_list_into_next_keeper_not_cta() -> None:
    keepers = [
        {
            "segment_id": "seg_004",
            "start_ms": 83_740,
            "end_ms": 95_460,
            "talking_point_id": "tp_a",
        },
        {
            "segment_id": "seg_005",
            "start_ms": 96_160,
            "end_ms": 121_660,
            "talking_point_id": "tp_b",
        },
    ]
    words = [
        {"text": "today?", "start_ms": 86_900, "end_ms": 87_160, "speaker_id": "spk_1"},
        {"text": "reshape", "start_ms": 94_040, "end_ms": 94_480, "speaker_id": "spk_1"},
        {"text": "clinical", "start_ms": 94_480, "end_ms": 94_820, "speaker_id": "spk_1"},
        {"text": "trials,", "start_ms": 94_820, "end_ms": 95_460, "speaker_id": "spk_1"},
        {"text": "drug", "start_ms": 96_160, "end_ms": 96_300, "speaker_id": "spk_0"},
        {"text": "development,", "start_ms": 96_300, "end_ms": 96_780, "speaker_id": "spk_0"},
        {"text": "and", "start_ms": 96_780, "end_ms": 97_120, "speaker_id": "spk_0"},
        {"text": "diagnostics.", "start_ms": 97_120, "end_ms": 97_920, "speaker_id": "spk_0"},
        {"text": "Well,", "start_ms": 97_920, "end_ms": 98_320, "speaker_id": "spk_0"},
        {"text": "before", "start_ms": 98_580, "end_ms": 98_780, "speaker_id": "spk_0"},
        {"text": "we", "start_ms": 98_780, "end_ms": 99_000, "speaker_id": "spk_0"},
        {"text": "begin,", "start_ms": 99_000, "end_ms": 99_220, "speaker_id": "spk_0"},
        {"text": "subscribe", "start_ms": 110_000, "end_ms": 110_400, "speaker_id": "spk_0"},
    ]
    plan = _plan(
        _chapter("ch1", "Open", ["seg_004"]),
        _chapter("ch2", "CTA", ["seg_005"]),
    )
    windows = compute_recut_windows(
        keepers=keepers,
        plan=plan,
        words=words,
        max_cut_ms=180_000,
        next_keeper_eps_ms=80,
        min_keep_ms=2500,
    )
    assert windows[0]["end_ms"] == 97_920
    assert windows[0]["hanging_extended"] is True
    assert windows[1]["start_ms"] == 97_920
    assert windows[1]["end_ms"] == 121_660


def test_remap_rewrites_brief_talking_points_and_must_keeps(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    mapping = {"seg_001": "seg_101", "seg_002": "seg_102"}
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "Tape thesis.",
            "topics": [
                {
                    "name": "Topic",
                    "summary": "Summary",
                    "approx_time_range": "00:00-00:40",
                    "segment_ids": ["seg_001", "seg_002"],
                }
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/talking_points.json",
        {
            "strategy_summary": "Strategy.",
            "talking_points": [
                {
                    "talking_point_id": "tp_a",
                    "title": "Point",
                    "importance": "must_keep",
                    "why_it_matters": "Proof",
                    "segment_ids": ["seg_001"],
                }
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/ideal_cuts_selection_seed.json",
        {"must_keep_segment_ids": ["seg_001"], "ordered_segment_ids": ["seg_001", "seg_002"]},
        skip_handoff=True,
    )
    updated = rewrite_upstream_segment_refs(ctx, mapping)
    assert "understanding/content_brief.json" in updated
    brief = ctx.read_json("understanding/content_brief.json")
    assert brief["topics"][0]["segment_ids"] == ["seg_101", "seg_102"]
    tps = ctx.read_json("understanding/talking_points.json")
    assert tps["talking_points"][0]["segment_ids"] == ["seg_101"]
    seed = ctx.read_json("understanding/ideal_cuts_selection_seed.json")
    assert seed["must_keep_segment_ids"] == ["seg_101"]
    blob = str(brief) + str(tps) + str(seed)
    assert "seg_001" not in blob
    assert "seg_002" not in blob


def test_apply_segment_id_map_does_not_drop_unmapped() -> None:
    doc = {"segment_ids": ["seg_001", "orphan_keep"], "segment_id": "seg_001"}
    out = apply_segment_id_map(doc, {"seg_001": "seg_101"})
    assert out["segment_ids"] == ["seg_101", "orphan_keep"]
    assert out["segment_id"] == "seg_101"


def test_unmatched_must_keeps_are_flagged() -> None:
    remap = build_segment_remap(
        [{"segment_id": "seg_keep", "start_ms": 0, "end_ms": 1000, "talking_point_id": "tp"}],
        [{"segment_id": "seg_new", "start_ms": 50_000, "end_ms": 51_000, "talking_point_id": "other"}],
        must_keep_ids={"seg_keep"},
    )
    assert "seg_keep" not in remap["old_to_new"]
    assert remap["unmatched_must_keep_ids"] == ["seg_keep"]


def test_clear_from_preserves_hitch_artifacts(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.write_json(
        LATCH_REL,
        {"version": 1, "status": "committed", "seq": 1},
        skip_handoff=True,
        stage_key=STAGE_ID,
    )
    ctx.write_json(INTENT_REL, _plan(_chapter("ch1", "Keep", ["seg_001"])), skip_handoff=True)
    ctx.write_json(REMAP_REL, {"old_to_new": {"seg_001": "seg_101"}}, skip_handoff=True)
    ctx.clear_from("boundary_detection", list(ANALYSIS_ORDER) + list(DELIVERY_ORDER))
    assert ctx.artifact_exists(LATCH_REL)
    assert ctx.artifact_exists(INTENT_REL)
    assert ctx.artifact_exists(REMAP_REL)
    assert hitch_latch_committed(ctx)


def _seed_hitch_run(ctx: RunContext) -> None:
    ctx.write_json(
        NARRATIVE_REL,
        _plan(_chapter("ch1", "Original chapter", ["seg_001", "seg_002"])),
        skip_handoff=True,
        stage_key="narrative_arc_plan",
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 4000,
                    "talking_point_id": "tp_a",
                    "text": "This is the intro.",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": ["test"],
                },
                {
                    "segment_id": "seg_002",
                    "start_ms": 20000,
                    "end_ms": 28000,
                    "talking_point_id": "tp_a",
                    "text": "Next keeper.",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": ["test"],
                },
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "transcript/full.json",
        {"words": _close_words()},
        skip_handoff=True,
    )


def test_second_entry_is_noop(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    _seed_hitch_run(ctx)
    monkeypatch.setattr(
        "interview_mux.chapter_close_hitch.apply_acoustic_refine",
        lambda windows, words, wav: windows,
    )
    monkeypatch.setattr(
        "interview_mux.chapter_close_hitch.run_inner_walk",
        lambda ctx, stages=None: ["boundary_detection"],
    )
    run_chapter_close_hitch(ctx)
    assert hitch_latch_committed(ctx)
    first = ctx.read_json(LATCH_REL)
    run_chapter_close_hitch(ctx)
    second = ctx.read_json(LATCH_REL)
    assert second["generated_at"] == first["generated_at"]
    assert ctx.is_done(STAGE_ID)


def test_qc_title_drift_keeps_remapped_intent(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    _seed_hitch_run(ctx)

    def _walk(ctx: RunContext, stages: list[str] | None = None) -> list[str]:
        ctx.write_json(
            NARRATIVE_REL,
            _plan(_chapter("ch1", "Drifted title", ["seg_001", "seg_002"])),
            skip_handoff=True,
            stage_key="narrative_arc_plan",
        )
        return ["narrative_arc_plan"]

    monkeypatch.setattr(
        "interview_mux.chapter_close_hitch.apply_acoustic_refine",
        lambda windows, words, wav: windows,
    )
    monkeypatch.setattr("interview_mux.chapter_close_hitch.run_inner_walk", _walk)
    run_chapter_close_hitch(ctx)
    live = ctx.read_json(NARRATIVE_REL)
    assert live["chapters"][0]["title"] == "Original chapter"
    qc = ctx.read_json(QC_PLAN_REL)
    assert qc["chapters"][0]["title"] == "Drifted title"
    latch = ctx.read_json(LATCH_REL)
    assert latch["chapter_authority"]["adopted"] == "remapped_intent"


def test_empty_remapped_chapter_adopts_qc(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    intent = _plan(
        _chapter("ch1", "Keep me", ["seg_001"]),
        _chapter("ch2", "Will empty", ["seg_002"]),
    )
    qc = _plan(
        _chapter("ch1", "QC one", ["seg_101"]),
        _chapter("ch2", "QC two", ["seg_202"]),
    )
    ctx.write_json(NARRATIVE_REL, qc, skip_handoff=True, stage_key="narrative_arc_plan")
    result = apply_chapter_authority(
        ctx,
        intent=intent,
        mapping={"seg_001": "seg_101"},
        new_ids={"seg_101", "seg_202"},
    )
    assert result["adopted"] == "qc_plan"
    live = ctx.read_json(NARRATIVE_REL)
    assert live["chapters"][1]["title"] == "QC two"


def test_inner_walk_does_not_dispatch_stage_budget(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    seen: list[tuple[str, bool]] = []

    def _stage(ctx: RunContext, stage: str) -> None:
        seen.append((stage, bool(getattr(ctx, "_homunculus_inner_stage", False))))
        ctx.mark_done(stage, force=True)

    monkeypatch.setattr("interview_mux.pipeline.run_single_stage", _stage)
    ran = run_inner_walk(ctx, stages=["boundary_detection", "narrative_arc_plan"])
    assert ran == ["boundary_detection", "narrative_arc_plan"]
    assert all(flag for _, flag in seen)
    assert count_identity(ctx, "boundary_detection") == 0
    assert count_identity(ctx, "narrative_arc_plan") == 0


def test_hitch_identity_counts_one_on_010(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    _seed_hitch_run(ctx)
    for sid in list(ANALYSIS_ORDER) + ["topic_coverage_audit", "narrative_arc_plan"]:
        ctx.mark_done(sid, force=True)
    monkeypatch.setattr(
        "interview_mux.chapter_close_hitch.apply_acoustic_refine",
        lambda windows, words, wav: windows,
    )
    monkeypatch.setattr(
        "interview_mux.chapter_close_hitch.run_inner_walk",
        lambda ctx, stages=None: ["boundary_detection", "ideal_cuts_materialize", "narrative_arc_plan"],
    )
    run_single_stage(ctx, STAGE_ID)
    assert hitch_latch_committed(ctx)
    assert count_identity(ctx, STAGE_ID) == 1
    assert count_identity(ctx, "ideal_cuts_materialize") == 0
    assert count_identity(ctx, "boundary_detection") == 0
    assert count_identity(ctx, "narrative_arc_plan") == 0


def test_nested_llm_during_hitch_inner_does_not_burn_stage_cap(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    append_ledger(ctx, {"kind": "stage", "identity": STAGE_ID, "status": "started"})
    setattr(ctx, "_chapter_close_hitch_inner", True)
    captured: list[dict] = []

    class _C:
        def create(self, **kwargs):
            captured.append(kwargs)
            return SimpleNamespace(id="r")

    client = SimpleNamespace(chat=SimpleNamespace(completions=_C()))
    nested_chat_create(
        ctx,
        "boundary_detection",
        client,
        {"model": "x", "messages": [{"role": "user", "content": "ok"}]},
    )
    assert captured
    assert count_identity(ctx, "boundary_detection") == 0
    assert count_identity(ctx, "ideal_cuts_materialize") == 0


def test_cannot_skip_hitch_until_latch_committed(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="cannot skip chapter_close_hitch"):
        skip_stage(ctx, STAGE_ID, reason="conductor whim")
    ctx.write_json(
        LATCH_REL,
        {"version": 1, "status": "committed", "seq": 1},
        skip_handoff=True,
        stage_key=STAGE_ID,
    )
    doc = skip_stage(ctx, STAGE_ID, reason="already latched")
    assert STAGE_ID in (doc.get("skipped") or [])


def _tiny_wav(path) -> None:
    import wave

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(b"\x00\x00" * 160)


def test_embedded_ids_and_composed_maps() -> None:
    mapping = {"seg_001": "seg_101", "seg_002": "seg_102"}
    assert rewrite_embedded_segment_ids("vo_seed_seg_001", mapping) == "vo_seed_seg_101"
    assert rewrite_embedded_segment_ids("vo_layup_seg_002", mapping) == "vo_layup_seg_102"
    assert rewrite_embedded_segment_ids("seg_0010", mapping) == "seg_0010"
    chained = compose_segment_maps(
        {"seg_001": "seg_101"},
        {"seg_101": "seg_201"},
    )
    assert chained["seg_001"] == "seg_201"
    assert chained["seg_101"] == "seg_201"
    doc = apply_segment_id_map(
        {
            "line_id": "vo_seed_seg_001",
            "target_segment_id": "seg_001",
            "subject_id": "vo_layup_seg_001",
        },
        mapping,
    )
    assert doc["line_id"] == "vo_seed_seg_101"
    assert doc["subject_id"] == "vo_layup_seg_101"


def test_omit_ledger_and_vo_files_follow_remap(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    mapping = {"seg_001": "seg_101"}
    ctx.write_json(
        "understanding/omit_ledger.json",
        {
            "version": 1,
            "entries": [
                {
                    "entry_id": "omit_gap_line_skip_vo_seed_seg_001_1",
                    "kind": "gap_line_skip",
                    "subject_id": "vo_seed_seg_001",
                    "target_segment_id": "seg_001",
                    "decision": "defer",
                    "reason_code": "g1_skipped_optional",
                    "owner_stage": "g1_vo_pickup",
                    "active": True,
                    "operator_override": True,
                }
            ],
            "summary": {"active_count": 1, "by_kind": {"gap_line_skip": 1}},
        },
        skip_handoff=True,
    )
    _tiny_wav(ctx.final_path("vo_pickup") / "vo_seed_seg_001.wav")
    copied = rebind_vo_pickup_files(ctx, mapping)
    assert any("vo_seed_seg_101.wav" in p for p in copied)
    assert (ctx.final_path("vo_pickup") / "vo_seed_seg_101.wav").is_file()
    assert remap_omit_ledger(ctx, mapping)
    ledger = ctx.read_json("understanding/omit_ledger.json")
    assert ledger["entries"][0]["target_segment_id"] == "seg_101"
    assert ledger["entries"][0]["subject_id"] == "vo_seed_seg_101"
    nested = apply_segment_id_map(
        {"volley_entries": [{"entry_id": "e1", "segment_id": "seg_001", "status": "active"}]},
        mapping,
    )
    assert nested["volley_entries"][0]["segment_id"] == "seg_101"


def test_reattach_vo_when_gap_report_changes_line_id(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    mapping = {"seg_001": "seg_101"}
    ctx.write_json(
        "mastering/chapter_close_hitch/vo_snapshot.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_seed_seg_001",
                    "targets_segment_id": "seg_001",
                    "delivery": "record",
                    "text": "Here is the guest.",
                    "skipped_optional": False,
                }
            ]
        },
        skip_handoff=True,
        stage_key=STAGE_ID,
    )
    _tiny_wav(ctx.final_path("vo_pickup") / "vo_seed_seg_001.wav")
    rebind_vo_pickup_files(ctx, mapping)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "line_001",
                    "targets_segment_id": "seg_101",
                    "gap_type": "missing_context",
                    "placement": "before",
                    "delivery": "record",
                    "text": "Here is the guest.",
                }
            ]
        },
        skip_handoff=True,
    )
    out = reattach_vo_to_gap_report(ctx, mapping)
    assert out["copied"] >= 1 or (ctx.final_path("vo_pickup") / "line_001.wav").is_file()
    assert (ctx.final_path("vo_pickup") / "line_001.wav").is_file() or (
        ctx.final_path("vo_pickup") / "seg_101.wav"
    ).is_file()


def test_resume_running_latch_does_not_double_recut(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    _seed_hitch_run(ctx)
    recut_calls = {"n": 0}
    walk_calls = {"n": 0}

    def _refine(windows, words, wav):
        recut_calls["n"] += 1
        return windows

    def _walk(ctx: RunContext, stages: list[str] | None = None) -> list[str]:
        walk_calls["n"] += 1
        if walk_calls["n"] == 1:
            raise RuntimeError("boom inner")
        return ["boundary_detection"]

    monkeypatch.setattr(
        "interview_mux.chapter_close_hitch.apply_acoustic_refine", _refine
    )
    monkeypatch.setattr("interview_mux.chapter_close_hitch.run_inner_walk", _walk)
    with pytest.raises(RuntimeError, match="boom inner"):
        run_chapter_close_hitch(ctx)
    latch = ctx.read_json(LATCH_REL)
    assert latch["status"] == "running"
    assert latch["wiped"] is True
    assert recut_calls["n"] == 1
    run_chapter_close_hitch(ctx)
    assert hitch_latch_committed(ctx)
    assert recut_calls["n"] == 1
    assert walk_calls["n"] == 2


def test_hitch_rewrites_vo_omit_and_keeps_chapter_title(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    _seed_hitch_run(ctx)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_seed_seg_001",
                    "targets_segment_id": "seg_001",
                    "gap_type": "missing_context",
                    "placement": "before",
                    "delivery": "record",
                    "text": "Meet the guest.",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/omit_ledger.json",
        {
            "version": 1,
            "entries": [
                {
                    "entry_id": "omit_1",
                    "kind": "gap_line_skip",
                    "subject_id": "vo_seed_seg_001",
                    "target_segment_id": "seg_001",
                    "decision": "defer",
                    "reason_code": "g1_skipped_optional",
                    "owner_stage": "g1_vo_pickup",
                    "active": True,
                    "operator_override": True,
                }
            ],
            "summary": {"active_count": 1},
        },
        skip_handoff=True,
    )
    _tiny_wav(ctx.final_path("vo_pickup") / "vo_seed_seg_001.wav")

    def _walk(ctx: RunContext, stages: list[str] | None = None) -> list[str]:
        mapping = (ctx.read_json(REMAP_REL) or {}).get("old_to_new") or {}
        n1 = mapping.get("seg_001", "seg_001")
        n2 = mapping.get("seg_002", "seg_002")
        ctx.write_json(
            NARRATIVE_REL,
            _plan(_chapter("ch1", "Drifted title", [n1, n2])),
            skip_handoff=True,
            stage_key="narrative_arc_plan",
        )
        ctx.write_json(
            "understanding/gap_report.json",
            {
                "interviewer_lines": [
                    {
                        "line_id": f"vo_seed_{n1}",
                        "targets_segment_id": n1,
                        "gap_type": "missing_context",
                        "placement": "before",
                        "delivery": "record",
                        "text": "Meet the guest.",
                    }
                ]
            },
            skip_handoff=True,
        )
        man = ctx.read_json("segments/manifest.json") if ctx.artifact_exists("segments/manifest.json") else {}
        segs = list((man or {}).get("segments") or [])
        if segs:
            segs[0]["segment_id"] = n1
            if len(segs) > 1:
                segs[1]["segment_id"] = n2
            ctx.write_json("segments/manifest.json", {"segments": segs}, skip_handoff=True)
        return ["gap_framing_compose", "narrative_arc_plan"]

    monkeypatch.setattr(
        "interview_mux.chapter_close_hitch.apply_acoustic_refine",
        lambda windows, words, wav: windows,
    )
    monkeypatch.setattr("interview_mux.chapter_close_hitch.run_inner_walk", _walk)
    run_chapter_close_hitch(ctx)
    assert hitch_latch_committed(ctx)
    live = ctx.read_json(NARRATIVE_REL)
    assert live["chapters"][0]["title"] == "Original chapter"
    remap = ctx.read_json(REMAP_REL)
    n1 = (remap.get("old_to_new") or {}).get("seg_001")
    assert n1
    assert (ctx.final_path("vo_pickup") / f"vo_seed_{n1}.wav").is_file()
    ledger = ctx.read_json("understanding/omit_ledger.json")
    assert ledger["entries"][0]["target_segment_id"] == n1
    assert ledger["entries"][0]["subject_id"] == f"vo_seed_{n1}"


def test_episode_structure_aligns_to_remapped_chapters(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_101",
                    "start_ms": 0,
                    "end_ms": 4000,
                    "type": "interviewee_answer",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "text": "Intro.",
                    "topic_tags": ["test"],
                },
                {
                    "segment_id": "seg_102",
                    "start_ms": 20000,
                    "end_ms": 28000,
                    "type": "interviewee_answer",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "text": "Next.",
                    "topic_tags": ["test"],
                },
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        NARRATIVE_REL,
        _plan(
            _chapter("ch1", "First", ["seg_101"]),
            _chapter("ch2", "Second", ["seg_102"]),
        ),
        skip_handoff=True,
        stage_key="narrative_arc_plan",
    )
    ctx.write_json(
        "understanding/episode_structure.json",
        {
            "schema_version": 1,
            "slot_plan": [
                {
                    "slot_id": "slot_01_STD_act_body",
                    "component_id": "STD_act_body",
                    "class": "standard",
                    "gate": "prefer",
                    "bound_segment_ids": ["seg_001", "seg_002"],
                    "speech_job": "interview_mass",
                    "music_transition": "under_speech",
                    "asset_role": "ambient_bed",
                    "placement": "body",
                    "priority": 50,
                    "repeat_allowed": False,
                },
                {
                    "slot_id": "slot_02_STD_chapter_hinge",
                    "component_id": "STD_chapter_hinge",
                    "class": "standard",
                    "gate": "allow",
                    "bound_segment_ids": ["seg_001"],
                    "speech_job": "chapter_reset",
                    "music_transition": "between_islands",
                    "asset_role": "chapter_stinger",
                    "placement": "body",
                    "priority": 40,
                    "repeat_allowed": False,
                },
            ],
            "segment_order": ["seg_002", "seg_001"],
            "hook_reel": {"segment_id": "seg_001", "repeat_allowed": True},
            "integrity": {"ok": True, "flags": []},
            "occupancy": {"violations": []},
            "omit_reasons": [],
            "axes": {},
            "policy_hash": "test",
            "rationale": ["hitch-test"],
        },
        skip_handoff=True,
    )
    from interview_mux.chapter_close_hitch import align_episode_structure_to_narrative

    monkeypatch.setattr(
        "interview_mux.episode_structure.persist_structure",
        lambda ctx, doc, stage: ctx.write_json(
            "understanding/episode_structure.json", doc, skip_handoff=True
        ),
    )
    result = align_episode_structure_to_narrative(
        ctx,
        mapping={"seg_001": "seg_101", "seg_002": "seg_102"},
        new_ids={"seg_101", "seg_102"},
    )
    assert result["ok"] is True
    doc = ctx.read_json("understanding/episode_structure.json")
    assert doc["segment_order"][0] == "seg_101"
    assert doc["hook_reel"]["segment_id"] == "seg_101"
    hinges = [s for s in doc["slot_plan"] if s.get("component_id") == "STD_chapter_hinge"]
    assert hinges
    assert hinges[0]["bound_segment_ids"] == ["seg_101", "seg_102"] or hinges[0][
        "bound_segment_ids"
    ][-1] == "seg_102"
