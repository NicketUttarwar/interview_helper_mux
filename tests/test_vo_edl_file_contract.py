"""VO/EDL file contract: no dangling source_path; current-pair synth; no old-neighbor reuse."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.segment_id_remap import apply_full_segment_id_remap, apply_segment_id_map
from interview_mux.stage_completion import (
    stage_artifact_incompleteness,
    vo_synthesize_should_defer_done,
)
from interview_mux.transition_vo import (
    commit_current_transition_wavs,
    current_pair_wav_usable,
    current_transition_pairs_missing,
    last_chance_synth_missing_clip,
    lint_edl_vo_source_paths,
    persist_vo_pair_gap,
    seated_vo_paths_missing,
    transition_wav_path,
)
from interview_mux.v2.config import DELIVERY_ORDER
from interview_mux.write_staging import (
    enter_stage_staging,
    exit_stage_staging,
    promote_staged_side_effects,
)
from run_fixtures import isolated_run_ctx, patch_merged_config


def _write_wav(path: Path, *, frames: int = 4800) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(48_000)
        handle.writeframes(b"\x00\x00" * frames)


def _dump(ctx: RunContext, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _transitions_doc(*pairs: tuple[str, str, str]) -> dict:
    return {
        "transitions": [
            {
                "after_segment_id": a,
                "before_segment_id": b,
                "text": text,
                "type": "bridge",
            }
            for a, b, text in pairs
        ]
    }


def test_lint_clears_dangling_source_path(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "vo_lint")
    edl = {
        "clips": [
            {
                "type": "transition",
                "after_segment_id": "seg_055",
                "before_segment_id": "seg_058",
                "text": "Meanwhile the trial enrolled.",
                "source_path": "master/transitions/tr_seg_055_seg_058.wav",
                "duration_ms": 1200,
            }
        ]
    }
    out = lint_edl_vo_source_paths(ctx, edl)
    clip = out["clips"][0]
    assert "source_path" not in clip or not clip.get("source_path")
    assert int(clip.get("duration_ms") or 0) == 0


def test_order_swap_requires_new_pair_filenames(tmp_path, monkeypatch) -> None:
    patch_merged_config(
        monkeypatch,
        {"analysis": {"gap_vo": {"post_synthesis_qc": {"enabled": False, "speech_qa_enabled": False}}}},
    )
    ctx = isolated_run_ctx(tmp_path, "vo_swap")
    _dump(
        ctx,
        "segments/manifest.json",
        {
            "segments": [
                {"segment_id": "seg_055", "text": "After the assay.", "type": "interviewee_answer", "speaker_id": "spk_0", "speaker_role": "interviewee", "topic_tags": [], "start_ms": 0, "end_ms": 1000},
                {"segment_id": "seg_061", "text": "Old neighbor.", "type": "interviewee_answer", "speaker_id": "spk_0", "speaker_role": "interviewee", "topic_tags": [], "start_ms": 1000, "end_ms": 2000},
                {"segment_id": "seg_058", "text": "New neighbor.", "type": "interviewee_answer", "speaker_id": "spk_0", "speaker_role": "interviewee", "topic_tags": [], "start_ms": 2000, "end_ms": 3000},
                {"segment_id": "seg_063", "text": "Then the readout.", "type": "interviewee_answer", "speaker_id": "spk_0", "speaker_role": "interviewee", "topic_tags": [], "start_ms": 3000, "end_ms": 4000},
            ]
        },
    )
    old_a = transition_wav_path(ctx, "seg_055", "seg_061")
    old_b = transition_wav_path(ctx, "seg_061", "seg_063")
    _write_wav(old_a)
    _write_wav(old_b)
    _dump(
        ctx,
        "master/transitions.json",
        _transitions_doc(
            ("seg_055", "seg_058", "The new neighbor changed the cut."),
            ("seg_058", "seg_063", "Then the readout landed."),
        ),
    )
    synthesized: list[tuple[str, str]] = []

    def _fake_synth(ctx_inner, *, pairs=None):
        del ctx_inner
        for a, b, _t in (
            ("seg_055", "seg_058", "x"),
            ("seg_058", "seg_063", "y"),
        ):
            if pairs is not None and (a, b) not in pairs:
                continue
            synthesized.append((a, b))
            _write_wav(transition_wav_path(ctx, a, b))
        return [{"after_segment_id": a, "before_segment_id": b, "ok": True} for a, b in synthesized]

    monkeypatch.setattr("interview_mux.transition_vo.synthesize_spoken_transitions", _fake_synth)
    still = commit_current_transition_wavs(ctx)
    del still
    assert ("seg_055", "seg_058") in synthesized
    assert ("seg_058", "seg_063") in synthesized
    assert transition_wav_path(ctx, "seg_055", "seg_058").is_file()
    assert transition_wav_path(ctx, "seg_058", "seg_063").is_file()
    assert old_a.is_file()
    assert not transition_wav_path(ctx, "seg_055", "seg_058").samefile(old_a)


def test_last_chance_does_not_reuse_other_pair(tmp_path, monkeypatch) -> None:
    patch_merged_config(
        monkeypatch,
        {
            "mix": {"missing_vo_retry_once": True},
            "analysis": {"gap_vo": {"post_synthesis_qc": {"enabled": False, "speech_qa_enabled": False}}},
        },
    )
    ctx = isolated_run_ctx(tmp_path, "vo_noreuse")
    leftover = transition_wav_path(ctx, "seg_055", "seg_061")
    _write_wav(leftover)
    _dump(
        ctx,
        "master/transitions.json",
        _transitions_doc(("seg_055", "seg_058", "Unique bridge for the new pair.")),
    )
    _dump(
        ctx,
        "segments/manifest.json",
        {
            "segments": [
                {"segment_id": "seg_055", "text": "After the assay.", "type": "interviewee_answer", "speaker_id": "spk_0", "speaker_role": "interviewee", "topic_tags": [], "start_ms": 0, "end_ms": 1000},
                {"segment_id": "seg_058", "text": "New neighbor.", "type": "interviewee_answer", "speaker_id": "spk_0", "speaker_role": "interviewee", "topic_tags": [], "start_ms": 1000, "end_ms": 2000},
            ]
        },
    )
    called: list[tuple[str, str]] = []

    def _fake_synth(ctx_inner, *, pairs=None):
        called.append(next(iter(pairs or {(None, None)})))
        a, b = next(iter(pairs or [("seg_055", "seg_058")]))
        _write_wav(transition_wav_path(ctx_inner, a, b))
        return [{"after_segment_id": a, "before_segment_id": b, "ok": True}]

    monkeypatch.setattr("interview_mux.transition_vo.synthesize_spoken_transitions", _fake_synth)
    monkeypatch.setattr(
        "interview_mux.transition_vo.resolve_transition_wav",
        lambda c, a, b: transition_wav_path(c, a, b) if transition_wav_path(c, a, b).is_file() else None,
    )
    monkeypatch.setattr("interview_mux.vo_speech_qa.vo_passes_speech_qa", lambda *_a, **_k: True)
    clip = {
        "type": "transition",
        "after_segment_id": "seg_055",
        "before_segment_id": "seg_058",
        "text": "Unique bridge for the new pair.",
        "source_path": "master/transitions/tr_seg_055_seg_058.wav",
    }
    path = last_chance_synth_missing_clip(ctx, clip, edl={"clips": [clip]})
    assert path is not None
    assert path.name == "tr_seg_055_seg_058.wav"
    assert called == [("seg_055", "seg_058")]
    assert path.resolve() != leftover.resolve()


def test_last_chance_synth_fail_returns_none(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "vo_fail")
    _dump(ctx, "master/transitions.json", _transitions_doc(("seg_a", "seg_b", "Bridge.")))
    monkeypatch.setattr(
        "interview_mux.transition_vo.synthesize_spoken_transitions",
        lambda *_a, **_k: [{"ok": False}],
    )
    monkeypatch.setattr("interview_mux.transition_vo.resolve_transition_wav", lambda *_a, **_k: None)
    clip = {
        "type": "transition",
        "after_segment_id": "seg_a",
        "before_segment_id": "seg_b",
        "text": "Bridge.",
        "source_path": "master/transitions/tr_seg_a_seg_b.wav",
    }
    assert last_chance_synth_missing_clip(ctx, clip, edl={"clips": [clip]}) is None


def test_last_chance_rejects_duplicate_seated_line(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "vo_dup")
    _dump(ctx, "master/transitions.json", _transitions_doc(("seg_a", "seg_b", "Same line.")))
    new_path = transition_wav_path(ctx, "seg_a", "seg_b")
    _write_wav(new_path)

    def _fake_synth(ctx_inner, *, pairs=None):
        del pairs
        return [{"ok": True}]

    monkeypatch.setattr("interview_mux.transition_vo.synthesize_spoken_transitions", _fake_synth)
    monkeypatch.setattr(
        "interview_mux.transition_vo.resolve_transition_wav",
        lambda *_a, **_k: new_path,
    )
    monkeypatch.setattr("interview_mux.vo_speech_qa.vo_passes_speech_qa", lambda *_a, **_k: True)
    other = {
        "type": "transition",
        "after_segment_id": "seg_x",
        "before_segment_id": "seg_y",
        "text": "Same line.",
        "source_path": "master/transitions/tr_seg_x_seg_y.wav",
    }
    clip = {
        "type": "transition",
        "after_segment_id": "seg_a",
        "before_segment_id": "seg_b",
        "text": "Same line.",
        "source_path": "master/transitions/tr_seg_a_seg_b.wav",
    }
    edl = {"clips": [other, clip]}
    assert last_chance_synth_missing_clip(ctx, clip, edl=edl) is None


def test_promote_staged_transition_wavs(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "vo_stage")
    enter_stage_staging("junction_snip_qa")
    try:
        staged = ctx.path("master", "transitions", "tr_seg_055_seg_058.wav")
        _write_wav(staged)
        promoted = promote_staged_side_effects(ctx, ("master/transitions/",), stage_id="junction_snip_qa")
    finally:
        exit_stage_staging()
    assert any(p.endswith("tr_seg_055_seg_058.wav") for p in promoted)
    assert ctx.final_path("master", "transitions", "tr_seg_055_seg_058.wav").is_file()


def test_seated_missing_detects_dangling_edl(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "vo_seated")
    _dump(
        ctx,
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_055", "seg_058"],
            "timeline_duration_ms": 0,
            "clips": [
                {
                    "type": "transition",
                    "after_segment_id": "seg_055",
                    "before_segment_id": "seg_058",
                    "source_path": "master/transitions/tr_seg_055_seg_058.wav",
                    "text": "Hole.",
                    "duration_ms": 0,
                }
            ],
        },
    )
    missing = seated_vo_paths_missing(ctx)
    assert missing == ["master/transitions/tr_seg_055_seg_058.wav"]


def _contract_edl(clips: list[dict]) -> dict:
    return {
        "version": 1,
        "ordered_segment_ids": ["seg_055", "seg_058"],
        "timeline_duration_ms": 0,
        "clips": clips,
    }


def _ghost_transition(**extra: object) -> dict:
    row = {
        "type": "transition",
        "after_segment_id": "seg_055",
        "before_segment_id": "seg_058",
        "timeline_start_ms": 0,
        "duration_ms": 1200,
        "text": "Meanwhile the trial enrolled.",
        "source_path": "master/transitions/tr_seg_055_seg_058.wav",
    }
    row.update(extra)
    return row


def test_write_json_never_persists_ghost_source_path(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "vo_write_json")
    ctx.write_json("master/edl.json", _contract_edl([_ghost_transition()]), skip_handoff=True)
    disk = ctx.read_json("master/edl.json")
    clip = disk["clips"][0]
    assert not clip.get("source_path")
    assert int(clip.get("duration_ms") or 0) == 0


def test_write_committed_json_never_persists_ghost_source_path(tmp_path) -> None:
    from interview_mux.write_staging import write_committed_json

    ctx = isolated_run_ctx(tmp_path, "vo_committed")
    write_committed_json(
        ctx,
        "master/edl.json",
        _contract_edl([_ghost_transition()]),
        stage_key="junction_snip_qa",
    )
    disk = ctx.read_json("master/edl.json")
    clip = disk["clips"][0]
    assert not clip.get("source_path")


def test_write_json_keeps_source_path_when_wav_exists(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "vo_keep")
    wav = ctx.path("master", "transitions", "tr_seg_055_seg_058.wav")
    _write_wav(wav)
    ctx.write_json("master/edl.json", _contract_edl([_ghost_transition()]), skip_handoff=True)
    disk = ctx.read_json("master/edl.json")
    assert disk["clips"][0].get("source_path") == "master/transitions/tr_seg_055_seg_058.wav"


def test_remap_rewritten_pair_path_stripped_on_write(tmp_path) -> None:
    from interview_mux.segment_id_remap import _pop_transition_source_paths, apply_segment_id_map

    ctx = isolated_run_ctx(tmp_path, "vo_remap_strip")
    _write_wav(ctx.path("master", "transitions", "tr_seg_055_seg_061.wav"))
    edl = _contract_edl(
        [
            _ghost_transition(
                before_segment_id="seg_061",
                source_path="master/transitions/tr_seg_055_seg_061.wav",
            )
        ]
    )
    edl["ordered_segment_ids"] = ["seg_055", "seg_061"]
    rewritten = apply_segment_id_map(edl, {"seg_061": "seg_058"})
    assert rewritten["clips"][0].get("source_path") == "master/transitions/tr_seg_055_seg_061.wav"
    popped = _pop_transition_source_paths(rewritten)
    ctx.write_json("master/edl.json", popped, skip_handoff=True)
    disk = ctx.read_json("master/edl.json")
    clip = disk["clips"][0]
    assert clip.get("before_segment_id") == "seg_058"
    assert not clip.get("source_path")


def test_persist_heals_dumped_ghost_edl(tmp_path) -> None:
    from interview_mux.edl_source_contract import persist_sanitized_edl

    ctx = isolated_run_ctx(tmp_path, "vo_heal")
    _dump(ctx, "master/edl.json", _contract_edl([_ghost_transition()]))
    assert seated_vo_paths_missing(ctx)
    persist_sanitized_edl(ctx)
    disk = ctx.read_json("master/edl.json")
    assert not disk["clips"][0].get("source_path")
    assert seated_vo_paths_missing(ctx) == []


def test_promote_heals_copied_ghost_edl(tmp_path) -> None:
    from interview_mux.write_staging import staged_path

    ctx = isolated_run_ctx(tmp_path, "vo_promote_edl")
    enter_stage_staging("junction_snip_qa")
    try:
        staged = staged_path(ctx, "master/edl.json", stage_id="junction_snip_qa")
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_text(json.dumps(_contract_edl([_ghost_transition()])), encoding="utf-8")
        promote_staged_side_effects(
            ctx, ("master/edl.json",), stage_id="junction_snip_qa"
        )
    finally:
        exit_stage_staging()
    disk = ctx.read_json("master/edl.json")
    assert not disk["clips"][0].get("source_path")


def test_post_edl_cross_validate_heals_ghosts(tmp_path) -> None:
    from interview_mux.artifact_cross_validate import validate_cross_artifacts

    ctx = isolated_run_ctx(tmp_path, "vo_cv")
    _dump(ctx, "master/edl.json", _contract_edl([_ghost_transition()]))
    errors = validate_cross_artifacts(ctx, "post_edl")
    disk = ctx.read_json("master/edl.json")
    assert not disk["clips"][0].get("source_path")
    assert not any("source_path names missing" in e for e in errors)


def test_file_store_write_json_strips_ghost_edl_paths(tmp_path) -> None:
    from interview_mux.file_store import read_json as fs_read_json
    from interview_mux.file_store import write_json as fs_write_json

    ctx = isolated_run_ctx(tmp_path, "vo_fs")
    path = ctx.run_dir / "master" / "edl.json"
    fs_write_json(path, _contract_edl([_ghost_transition()]))
    disk = fs_read_json(path)
    assert not disk["clips"][0].get("source_path")


def test_null_and_empty_source_path_omitted_on_write(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "vo_empty")
    clips = [
        _ghost_transition(source_path=None),
        _ghost_transition(
            after_segment_id="seg_058",
            before_segment_id="seg_063",
            source_path="  ",
        ),
    ]
    ctx.write_json("master/edl.json", _contract_edl(clips), skip_handoff=True)
    disk = ctx.read_json("master/edl.json")
    for clip in disk["clips"]:
        assert "source_path" not in clip


def test_apply_segment_id_map_does_not_rewrite_source_path() -> None:
    doc = {
        "clips": [
            {
                "type": "transition",
                "after_segment_id": "seg_061",
                "before_segment_id": "seg_063",
                "source_path": "master/transitions/tr_seg_055_seg_061.wav",
            }
        ]
    }
    out = apply_segment_id_map(doc, {"seg_061": "seg_058"})
    assert out["clips"][0]["after_segment_id"] == "seg_058"
    assert out["clips"][0]["source_path"] == "master/transitions/tr_seg_055_seg_061.wav"


def _fake_current_pair_synth(ctx: RunContext, *, after: str, before: str, text: str):
    def _synth(ctx_inner, *, pairs=None):
        del ctx_inner
        if pairs is not None and (after, before) not in pairs:
            return []
        wav = transition_wav_path(ctx, after, before)
        _write_wav(wav)
        from interview_mux.vo_synthesis_audit import record_synthesis

        record_synthesis(
            ctx,
            {
                "line_id": f"tr_{after}_{before}",
                "text": text,
                "after_segment_id": after,
                "before_segment_id": before,
            },
            backend="mlx_audio",
            out_wav=wav,
        )
        return [{"after_segment_id": after, "before_segment_id": before, "ok": True}]

    return _synth


def test_remap_061_to_058_generates_new_pair_not_rewritten_token(
    tmp_path, monkeypatch
) -> None:
    patch_merged_config(
        monkeypatch,
        {"analysis": {"gap_vo": {"post_synthesis_qc": {"enabled": False, "speech_qa_enabled": False}}}},
    )
    ctx = isolated_run_ctx(tmp_path, "vo_remap")
    leftover = transition_wav_path(ctx, "seg_055", "seg_061")
    _write_wav(leftover)
    text = "The new neighbor changed the cut."
    ctx.write_json(
        "master/transitions.json",
        _transitions_doc(("seg_055", "seg_061", text)),
        skip_handoff=True,
    )
    ctx.write_json(
        "master/edl.json",
        _contract_edl(
            [
                {
                    "type": "transition",
                    "after_segment_id": "seg_055",
                    "before_segment_id": "seg_061",
                    "timeline_start_ms": 0,
                    "duration_ms": 1200,
                    "text": text,
                    "source_path": leftover.relative_to(ctx.run_dir).as_posix(),
                }
            ]
        ),
        skip_handoff=True,
    )
    done = ctx.final_path(".stage_done", "edl")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("1", encoding="utf-8")
    monkeypatch.setattr(
        "interview_mux.transition_vo.synthesize_spoken_transitions",
        _fake_current_pair_synth(ctx, after="seg_055", before="seg_058", text=text),
    )
    apply_full_segment_id_remap(ctx, {"seg_061": "seg_058"}, rebind_vo=False)
    new_wav = transition_wav_path(ctx, "seg_055", "seg_058")
    assert new_wav.is_file()
    assert leftover.is_file()
    assert not new_wav.samefile(leftover)
    edl = ctx.read_json("master/edl.json")
    src = str((edl["clips"][0] or {}).get("source_path") or "")
    assert "061" not in src
    if src:
        assert src.endswith("tr_seg_055_seg_058.wav")
        assert ctx.final_path(*src.split("/")).is_file()
    else:
        assert "source_path" not in edl["clips"][0]
    assert not done.is_file()


def test_remaster_mix_only_commits_current_transition_wavs(tmp_path, monkeypatch) -> None:
    from interview_mux.junction_snip_qa import remaster_mix_only

    ctx = isolated_run_ctx(tmp_path, "vo_junction")
    called: list[str] = []
    monkeypatch.setattr(
        "interview_mux.transition_vo.commit_current_transition_wavs",
        lambda _ctx: called.append("commit") or [],
    )
    monkeypatch.setattr(
        "interview_mux.transition_vo.restamp_edl_transition_source_paths",
        lambda _ctx: called.append("restamp") or False,
    )
    monkeypatch.setattr(
        "interview_mux.assembly_ledger.write_assembly_ledger",
        lambda _ctx: {"complete": True},
    )
    monkeypatch.setattr(
        "interview_mux.stages.assembly.run_mix",
        lambda _ctx: called.append("mix"),
    )
    monkeypatch.setattr("interview_mux.seam_autopsy.write_render_ledger", lambda _ctx: None)
    monkeypatch.setattr(
        "interview_mux.write_staging.promote_staged_side_effects",
        lambda *_a, **_k: [],
    )
    remaster_mix_only(ctx)
    assert called[0] == "commit"
    assert "restamp" in called
    assert "mix" in called


def test_vo_synthesize_incomplete_on_old_pair_files_only(tmp_path, monkeypatch) -> None:
    from interview_mux.stages.vo_synthesize import run_vo_synthesize

    patch_merged_config(
        monkeypatch,
        {"analysis": {"gap_vo": {"post_synthesis_qc": {"enabled": False, "speech_qa_enabled": False}}}},
    )
    ctx = isolated_run_ctx(tmp_path, "vo_stage_done")
    leftover = transition_wav_path(ctx, "seg_055", "seg_061")
    _write_wav(leftover)
    text = "Meanwhile the trial enrolled."
    ctx.write_json(
        "master/transitions.json",
        _transitions_doc(("seg_055", "seg_058", text)),
        skip_handoff=True,
    )
    assert current_transition_pairs_missing(ctx) == ["seg_055->seg_058"]
    reason = stage_artifact_incompleteness(ctx, "vo_synthesize")
    assert reason is not None
    monkeypatch.setattr(
        "interview_mux.transition_vo.synthesize_spoken_transitions",
        _fake_current_pair_synth(ctx, after="seg_055", before="seg_058", text=text),
    )
    run_vo_synthesize(ctx)
    assert transition_wav_path(ctx, "seg_055", "seg_058").is_file()
    assert leftover.is_file()
    assert current_transition_pairs_missing(ctx) == []
    assert stage_artifact_incompleteness(ctx, "vo_synthesize") is None


def test_remaster_sync_unlinks_vo_synthesize_done_marker(tmp_path, monkeypatch) -> None:
    from interview_mux.timeline_optimizer.apply import remaster_sync

    assert "vo_synthesize" in DELIVERY_ORDER
    ctx = isolated_run_ctx(tmp_path, "vo_opt")
    marker = ctx.final_path(".stage_done", "vo_synthesize")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("1", encoding="utf-8")
    monkeypatch.setattr(
        "interview_mux.transition_vo.commit_current_transition_wavs",
        lambda _ctx: [],
    )
    monkeypatch.setattr("interview_mux.stages.assembly.run_edl", lambda _ctx: None)
    monkeypatch.setattr("interview_mux.stages.assembly.run_mix", lambda _ctx: None)
    remaster_sync(ctx)
    assert not marker.is_file()


def test_usable_wav_without_audit_is_not_missing(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "vo_usable")
    _dump(
        ctx,
        "master/transitions.json",
        _transitions_doc(("seg_055", "seg_058", "Meanwhile the trial enrolled.")),
    )
    wav = transition_wav_path(ctx, "seg_055", "seg_058")
    _write_wav(wav)
    assert current_pair_wav_usable(ctx, "seg_055", "seg_058") == wav
    assert current_transition_pairs_missing(ctx) == []
    assert stage_artifact_incompleteness(ctx, "vo_synthesize") is not None  # report json pending


def test_commit_persists_still_missing_pairs(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "vo_persist")
    _dump(
        ctx,
        "master/transitions.json",
        _transitions_doc(("seg_055", "seg_058", "Meanwhile the trial enrolled.")),
    )
    monkeypatch.setattr(
        "interview_mux.transition_vo.synthesize_spoken_transitions",
        lambda *_a, **_k: [],
    )
    still = commit_current_transition_wavs(ctx)
    assert still == ["seg_055->seg_058"]
    report = ctx.read_json("mastering/vo_synthesize.json")
    assert report["still_missing_pairs"] == ["seg_055->seg_058"]
    assert report["last_source"] == "commit"


def test_commit_persists_still_missing_pairs_when_synth_raises(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "vo_persist_raise")
    _dump(
        ctx,
        "master/transitions.json",
        _transitions_doc(("seg_055", "seg_058", "Meanwhile the trial enrolled.")),
    )

    def _boom(*_a, **_k):
        raise RuntimeError("s2s down")

    monkeypatch.setattr("interview_mux.transition_vo.synthesize_spoken_transitions", _boom)
    with pytest.raises(RuntimeError, match="s2s down"):
        commit_current_transition_wavs(ctx)
    report = ctx.read_json("mastering/vo_synthesize.json")
    assert report["still_missing_pairs"] == ["seg_055->seg_058"]
    assert report["last_source"] == "commit"


def test_post_edl_pair_gap_is_advisory(tmp_path) -> None:
    from interview_mux.artifact_cross_validate import validate_cross_artifacts

    ctx = isolated_run_ctx(tmp_path, "vo_post_edl_pairs")
    _dump(
        ctx,
        "master/transitions.json",
        _transitions_doc(("seg_055", "seg_058", "Meanwhile the trial enrolled.")),
    )
    _dump(ctx, "master/edl.json", _contract_edl([_ghost_transition()]))
    errors = validate_cross_artifacts(ctx, "post_edl")
    assert not any("current transition pairs" in e for e in errors)


def test_vo_synthesize_defer_done_fail_open(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "vo_defer")
    persist_vo_pair_gap(ctx, ["seg_055->seg_058"], source="test")
    _dump(
        ctx,
        "master/transitions.json",
        _transitions_doc(("seg_055", "seg_058", "Meanwhile the trial enrolled.")),
    )
    reason = vo_synthesize_should_defer_done(ctx, "vo_synthesize")
    assert reason is not None
    assert "seg_055->seg_058" in reason
    assert vo_synthesize_should_defer_done(ctx, "edl") is None
