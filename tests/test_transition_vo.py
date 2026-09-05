"""Spoken transitions must carry real duration when WAV exists; QC blocks zeros."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.stages.assembly import build_flow1_edl
from interview_mux.transition_vo import (
    assert_spoken_transitions_audible,
    resolve_transition_wav,
    transition_wav_path,
)
from interview_mux.vo_synthesis_audit import record_synthesis
from run_fixtures import isolated_run_ctx, patch_executions_root, patch_merged_config


def test_build_flow1_edl_transition_duration_from_wav(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    tr = tmp_path / "tr.wav"
    tr.write_bytes(b"x")

    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_001", "seg_002"]},
        segments_by_id={
            "seg_001": {"start_ms": 0, "end_ms": 1000},
            "seg_002": {"start_ms": 1000, "end_ms": 2000},
        },
        transitions={
            "transitions": [
                {
                    "after_segment_id": "seg_001",
                    "before_segment_id": "seg_002",
                    "text": "Next up.",
                    "type": "bridge",
                }
            ]
        },
        resolve_transition_path=lambda a, b: tr,
        vo_duration_ms=lambda _p: 1500,
        vo_relpath=lambda p: p.as_posix(),
    )
    tr_clips = [c for c in edl["clips"] if c.get("type") == "transition"]
    assert len(tr_clips) == 1
    assert tr_clips[0]["duration_ms"] == 1500
    assert tr_clips[0].get("source_path")
    # Speech + transition + optional air pads around the spoken hinge.
    silence_ms = sum(
        int(c.get("duration_ms") or 0)
        for c in edl["clips"]
        if c.get("type") == "silence"
    )
    assert edl["timeline_duration_ms"] == 1000 + 1500 + 1000 + silence_ms


def test_assert_spoken_transitions_blocks_zero_duration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    patch_merged_config(monkeypatch, {"creative_delivery": {"required": True}})
    ctx = RunContext("exec_tr_qc", create=True)
    edl = {
        "clips": [
            {
                "type": "transition",
                "after_segment_id": "seg_001",
                "before_segment_id": "seg_002",
                "text": "Bridge text",
                "duration_ms": 0,
                "source_path": "master/transitions/tr_seg_001_seg_002.wav",
            }
        ]
    }
    with pytest.raises(SystemExit, match="spoken transitions"):
        assert_spoken_transitions_audible(ctx, edl)


def test_transition_resolver_rejects_stale_copy(tmp_path, monkeypatch) -> None:
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "gap_vo": {
                    "post_synthesis_qc": {
                        "enabled": False,
                        "speech_qa_enabled": False,
                    }
                }
            }
        },
    )
    ctx = isolated_run_ctx(tmp_path, "transition_freshness")
    transitions = {
        "transitions": [
            {
                "after_segment_id": "seg_a",
                "before_segment_id": "seg_b",
                "text": "Protein buyers rewrote the addressable market.",
                "source_gap_ms": 1000,
            }
        ]
    }
    ctx.path("master", "transitions.json").parent.mkdir(parents=True, exist_ok=True)
    ctx.path("master", "transitions.json").write_text(
        json.dumps(transitions), encoding="utf-8"
    )
    manifest = {
        "segments": [
            {"segment_id": "seg_a", "text": "The first decision was made."},
            {"segment_id": "seg_b", "text": "The buyer arrived later."},
        ]
    }
    ctx.path("segments", "manifest.json").parent.mkdir(parents=True, exist_ok=True)
    ctx.path("segments", "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    out = transition_wav_path(ctx, "seg_a", "seg_b")
    with wave.open(str(out), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(48_000)
        handle.writeframes(b"\x00\x00" * 4800)
    line = {
        "line_id": "tr_seg_a_seg_b",
        "text": "Protein buyers rewrote the addressable market.",
        "targets_segment_id": "seg_a",
        "placement": "after",
        "after_segment_id": "seg_a",
        "before_segment_id": "seg_b",
        "before_excerpt": "The first decision was made.",
        "after_excerpt": "The buyer arrived later.",
        "source_gap_ms": 1000,
    }
    record_synthesis(ctx, line, backend="mlx_audio", out_wav=out)
    assert resolve_transition_wav(ctx, "seg_a", "seg_b") == out

    transitions["transitions"][0]["text"] = "What made the deal possible?"
    ctx.path("master", "transitions.json").write_text(
        json.dumps(transitions), encoding="utf-8"
    )
    assert resolve_transition_wav(ctx, "seg_a", "seg_b") is None


def test_transition_resolver_rejects_tiny_wav(tmp_path, monkeypatch) -> None:
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "gap_vo": {
                    "post_synthesis_qc": {
                        "enabled": False,
                        "speech_qa_enabled": False,
                    }
                }
            }
        },
    )
    ctx = isolated_run_ctx(tmp_path, "transition_tiny")
    transitions = {
        "transitions": [
            {
                "after_segment_id": "seg_a",
                "before_segment_id": "seg_b",
                "text": "Next beat.",
                "type": "bridge",
            }
        ]
    }
    ctx.write_json("master/transitions.json", transitions)
    out = transition_wav_path(ctx, "seg_a", "seg_b")
    out.write_bytes(b"tiny")
    line = {
        "line_id": "tr_seg_a_seg_b",
        "text": "Next beat.",
        "targets_segment_id": "seg_a",
        "placement": "after",
        "after_segment_id": "seg_a",
        "before_segment_id": "seg_b",
    }
    record_synthesis(ctx, line, backend="mlx_audio", out_wav=out)
    assert resolve_transition_wav(ctx, "seg_a", "seg_b") is None


def test_synthesize_transitions_writeback_guarded_text(tmp_path, monkeypatch) -> None:
    import json as _json

    from interview_mux.transition_vo import synthesize_spoken_transitions

    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "gap_vo": {
                    "post_synthesis_qc": {
                        "enabled": False,
                        "speech_qa_enabled": False,
                    }
                }
            }
        },
    )
    monkeypatch.setattr(
        "interview_mux.vo_speech_qa.vo_passes_speech_qa",
        lambda *_a, **_k: True,
    )
    ctx = isolated_run_ctx(tmp_path, "transition_writeback")
    tr_path = ctx.path("master", "transitions.json")
    tr_path.parent.mkdir(parents=True, exist_ok=True)
    tr_path.write_text(
        _json.dumps(
            {
                "transitions": [
                    {
                        "after_segment_id": "seg_a",
                        "before_segment_id": "seg_b",
                        "text": "Original hinge text here.",
                        "type": "bridge",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    man_path = ctx.path("segments", "manifest.json")
    man_path.parent.mkdir(parents=True, exist_ok=True)
    man_path.write_text(
        _json.dumps(
            {
                "segments": [
                    {"segment_id": "seg_a", "text": "First answer about the buyer."},
                    {"segment_id": "seg_b", "text": "Second answer about the deal."},
                ]
            }
        ),
        encoding="utf-8",
    )

    def _fake_guard(text, *, evidence=None, purpose="", seen_texts=None, ctx=None, exclude_line_id=None):
        return {
            "text": "Guarded rewrite about the buyer deal.",
            "action": "rewrite",
            "script_hash": "abc",
            "context_hash": "def",
        }

    def _fake_synth(ctx, line, mode="synthesize", dest_dir=None):
        out = transition_wav_path(ctx, "seg_a", "seg_b")
        with wave.open(str(out), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(48_000)
            handle.writeframes(b"\x01\x00" * 24_000)
        record_synthesis(ctx, line, backend="mlx_audio", out_wav=out)
        return out

    monkeypatch.setattr(
        "interview_mux.spoken_copy_guard.assert_guarded_spoken_copy", _fake_guard
    )
    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _fake_synth)
    # Avoid schema on writeback of guarded row.
    monkeypatch.setattr(
        ctx,
        "write_json",
        lambda rel, doc, **_k: ctx.path(*rel.split("/")).write_text(
            _json.dumps(doc), encoding="utf-8"
        )
        or None,
    )
    rows = synthesize_spoken_transitions(ctx)
    assert rows
    doc = _json.loads(tr_path.read_text(encoding="utf-8"))
    assert doc["transitions"][0]["text"] == "Guarded rewrite about the buyer deal."
    assert doc["transitions"][0].get("spoken_copy_guard", {}).get("action") == "rewrite"


def test_committed_transition_wav_skips_synth_during_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """vo_synthesize staging must not re-Chatterbox a committed usable pair WAV."""
    from interview_mux.transition_vo import current_pair_wav_usable
    from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "gap_vo": {
                    "post_synthesis_qc": {
                        "enabled": False,
                        "speech_qa_enabled": False,
                    }
                }
            }
        },
    )
    ctx = isolated_run_ctx(tmp_path, "tr_staging_skip")
    committed = ctx.final_path("master", "transitions")
    committed.mkdir(parents=True, exist_ok=True)
    wav = committed / "tr_seg_003k_seg_067.wav"
    with wave.open(str(wav), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(48_000)
        handle.writeframes(b"\x00\x00" * 4800)
    assert current_pair_wav_usable(ctx, "seg_003k", "seg_067") == wav
    enter_stage_staging("vo_synthesize")
    try:
        pending = transition_wav_path(ctx, "seg_003k", "seg_067")
        assert pending != wav
        assert not pending.is_file()
        found = current_pair_wav_usable(ctx, "seg_003k", "seg_067")
        assert found is not None
        assert found.resolve() == wav.resolve()
    finally:
        exit_stage_staging()


def _write_usable_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(48_000)
        handle.writeframes(b"\x00\x00" * 4800)


def test_retain_required_pair_dropped_from_transitions_but_in_edl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EDL transition clips must not vanish from transitions.json on rewrite."""
    from interview_mux.transition_vo import (
        persist_transitions_doc,
        retain_required_transition_pairs,
    )
    from run_fixtures import minimal_manifest_segment

    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "gap_vo": {
                    "post_synthesis_qc": {
                        "enabled": False,
                        "speech_qa_enabled": False,
                    }
                }
            }
        },
    )
    ctx = isolated_run_ctx(tmp_path, "tr_retain_edl")
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_036", "seg_038", "seg_041"]},
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                minimal_manifest_segment(
                    "seg_036", start_ms=0, end_ms=1000, text="A", speaker_role="interviewee"
                ),
                minimal_manifest_segment(
                    "seg_038", start_ms=5000, end_ms=6000, text="B", speaker_role="interviewee"
                ),
                minimal_manifest_segment(
                    "seg_041", start_ms=7000, end_ms=8000, text="C", speaker_role="interviewee"
                ),
            ]
        },
        skip_handoff=True,
    )
    text = "Moving from liquid biopsy to tumor cells, what changed?"
    _write_usable_wav(ctx.final_path("master", "transitions", "tr_seg_036_seg_038.wav"))
    edl_doc = {
        "version": 1,
        "ordered_segment_ids": ["seg_036", "seg_038", "seg_041"],
        "timeline_duration_ms": 1000,
        "clips": [
            {
                "type": "transition",
                "after_segment_id": "seg_036",
                "before_segment_id": "seg_038",
                "text": text,
                "source_path": "master/transitions/tr_seg_036_seg_038.wav",
                "duration_ms": 100,
            }
        ],
    }
    (ctx.final_path("master")).mkdir(parents=True, exist_ok=True)
    ctx.final_path("master", "edl.json").write_text(
        json.dumps(edl_doc), encoding="utf-8"
    )
    dropped = {
        "transitions": [
            {
                "after_segment_id": "seg_038",
                "before_segment_id": "seg_041",
                "text": "Other hinge.",
                "type": "bridge",
            }
        ]
    }
    retained, notes = retain_required_transition_pairs(ctx, dropped)
    pairs = {
        (
            str(r.get("after_segment_id")),
            str(r.get("before_segment_id")),
        )
        for r in retained.get("transitions") or []
    }
    assert ("seg_036", "seg_038") in pairs
    assert any("seg_036->seg_038" in n for n in notes)
    written = persist_transitions_doc(ctx, dropped, skip_handoff=True)
    pairs2 = {
        (
            str(r.get("after_segment_id")),
            str(r.get("before_segment_id")),
        )
        for r in written.get("transitions") or []
    }
    assert ("seg_036", "seg_038") in pairs2
    disk = ctx.read_json("master/transitions.json")
    assert any(
        str(r.get("after_segment_id")) == "seg_036"
        and str(r.get("before_segment_id")) == "seg_038"
        for r in disk.get("transitions") or []
    )


def test_pending_audit_path_resolves_committed_transition_wav(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """synthesis_report out_wav under .pending_writes must match committed WAV."""
    from interview_mux.vo_synthesis_audit import (
        audible_script_hash_errors,
        canonicalize_synthesis_out_wav_paths,
        record_synthesis,
        synthesis_entry_for_line,
        synthesis_entry_matches_line,
        _load_entries,
        _persist,
    )
    from interview_mux.transition_vo import ensure_pre_mix_transition_integrity
    from run_fixtures import minimal_manifest_segment

    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "gap_vo": {
                    "post_synthesis_qc": {
                        "enabled": False,
                        "speech_qa_enabled": False,
                    }
                }
            }
        },
    )
    ctx = isolated_run_ctx(tmp_path, "tr_path_canon")
    text = "The same combined readout could also change which patients enter a trial."
    after_id, before_id = "seg_033", "seg_035"
    lid = f"tr_{after_id}_{before_id}"
    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "after_segment_id": after_id,
                    "before_segment_id": before_id,
                    "text": text,
                    "type": "bridge",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                minimal_manifest_segment(
                    after_id, text="before", topic_tags=["t1"], speaker_role="interviewee"
                ),
                minimal_manifest_segment(
                    before_id, text="after", topic_tags=["t2"], speaker_role="interviewee"
                ),
            ]
        },
        skip_handoff=True,
    )
    committed = ctx.final_path("master", "transitions", f"{lid}.wav")
    _write_usable_wav(committed)
    line = {
        "line_id": lid,
        "text": text,
        "targets_segment_id": after_id,
        "placement": "after",
        "after_segment_id": after_id,
        "before_segment_id": before_id,
        "before_excerpt": "before",
        "after_excerpt": "after",
        "source_gap_ms": 1000,
        "strict_grounding": True,
    }
    pending = ctx.run_dir / ".pending_writes" / "edl" / "master" / "transitions" / "synthesized"
    pending.mkdir(parents=True, exist_ok=True)
    staged = pending / f"{lid}.wav"
    staged.write_bytes(committed.read_bytes())
    record_synthesis(ctx, line, backend="chatterbox", out_wav=staged, wav_just_rendered=True)
    entry = synthesis_entry_for_line(ctx, lid)
    assert entry is not None
    rows = _load_entries(ctx)
    for row in rows:
        if str(row.get("line_id")) == lid:
            row["out_wav"] = (
                f".pending_writes/edl/master/transitions/synthesized/{lid}.wav"
            )
    _persist(ctx, rows)
    staged.unlink()
    assert not staged.is_file()
    matches, reason = synthesis_entry_matches_line(ctx, line)
    assert matches, reason
    rewritten = canonicalize_synthesis_out_wav_paths(ctx)
    assert lid in rewritten or str(
        synthesis_entry_for_line(ctx, lid).get("out_wav") or ""
    ).startswith("master/transitions/")
    entry2 = synthesis_entry_for_line(ctx, lid)
    assert not str(entry2.get("out_wav") or "").startswith(".pending_writes/")

    edl_doc = {
        "version": 1,
        "ordered_segment_ids": [after_id, before_id],
        "timeline_duration_ms": 1000,
        "clips": [
            {
                "type": "transition",
                "after_segment_id": after_id,
                "before_segment_id": before_id,
                "text": text,
                "source_path": f".pending_writes/edl/master/transitions/{lid}.wav",
                "script_hash": entry2.get("script_hash"),
                "duration_ms": 100,
            }
        ],
    }
    ctx.final_path("master").mkdir(parents=True, exist_ok=True)
    ctx.final_path("master", "edl.json").write_text(
        json.dumps(edl_doc), encoding="utf-8"
    )
    ensure_pre_mix_transition_integrity(ctx, synthesize=False)
    errs = audible_script_hash_errors(ctx, ctx.read_json("master/edl.json"))
    assert errs == []


def test_transitions_write_cascades_purge_on_text_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rewriting spoken bridge text via write_json must purge the pair WAV."""
    from interview_mux.transition_vo import (
        current_transition_pairs_missing,
        resolve_transition_wav,
    )
    from interview_mux.vo_synthesis_audit import synthesis_entry_for_line

    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "gap_vo": {
                    "post_synthesis_qc": {
                        "enabled": False,
                        "speech_qa_enabled": False,
                    }
                }
            }
        },
    )
    ctx = isolated_run_ctx(tmp_path, "tr_text_cascade")
    text = "Protein buyers rewrote the addressable market."
    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "after_segment_id": "seg_a",
                    "before_segment_id": "seg_b",
                    "text": text,
                    "type": "bridge",
                    "source_gap_ms": 1000,
                }
            ]
        },
        skip_handoff=True,
    )
    out = transition_wav_path(ctx, "seg_a", "seg_b")
    with wave.open(str(out), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(48_000)
        handle.writeframes(b"\x00\x00" * 4800)
    line = {
        "line_id": "tr_seg_a_seg_b",
        "text": text,
        "targets_segment_id": "seg_a",
        "placement": "after",
        "after_segment_id": "seg_a",
        "before_segment_id": "seg_b",
    }
    record_synthesis(ctx, line, backend="mlx_audio", out_wav=out)
    ctx.mark_done("vo_synthesize", force=True)
    assert resolve_transition_wav(ctx, "seg_a", "seg_b") == out

    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "after_segment_id": "seg_a",
                    "before_segment_id": "seg_b",
                    "text": "What made the deal possible?",
                    "type": "bridge",
                    "source_gap_ms": 1000,
                }
            ]
        },
        stage_key="nugget_layup_compose",
        skip_handoff=True,
    )
    assert not out.is_file()
    assert synthesis_entry_for_line(ctx, "tr_seg_a_seg_b") is None
    assert "seg_a->seg_b" in current_transition_pairs_missing(ctx)
    assert not ctx.is_done("vo_synthesize")
