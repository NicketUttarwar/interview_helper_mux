from __future__ import annotations

import io
import wave
from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.stages import assembly
from interview_mux.stages.assembly import build_flow1_edl, resync_required_synthesize_wavs
from run_fixtures import (
    confirm_test_pickup_speaker,
    isolated_run_ctx,
    minimal_manifest,
    minimal_manifest_segment,
    write_fixture_json,
    write_fixture_vo_wav,
)


def _arm_vo_path(ctx: RunContext, speaker_id: str = "spk_host") -> None:
    confirm_test_pickup_speaker(ctx, speaker_id=speaker_id)
    write_fixture_vo_wav(
        ctx.final_path("understanding", "speaker_samples", f"{speaker_id}.wav"),
        duration_sec=3.2,
    )
    write_fixture_json(
        ctx,
        f"understanding/voice_reference/{speaker_id}.json",
        {
            "speaker_id": speaker_id,
            "approved": True,
            "wav": f"understanding/speaker_samples/{speaker_id}.wav",
        },
    )
    meta: dict = {}
    if ctx.artifact_exists("run_meta.json"):
        try:
            existing = ctx.read_json("run_meta.json")
            if isinstance(existing, dict):
                meta = dict(existing)
        except Exception:
            meta = {}
    meta.setdefault("gap_framing_enabled", True)
    meta.setdefault("gap_vo_delivery", "chatterbox")
    meta.setdefault("voice_reference_approved_at", "2026-01-01T00:00:00Z")
    write_fixture_json(ctx, "run_meta.json", meta)


def _segments() -> dict[str, dict]:
    return {
        "seg_a": {"segment_id": "seg_a", "start_ms": 0, "end_ms": 10_000},
        "seg_b": {"segment_id": "seg_b", "start_ms": 10_000, "end_ms": 25_000},
    }


def test_edl_inserts_vo_before_and_after_with_timeline_offsets(tmp_path: Path) -> None:
    gap_report = {
        "interviewer_lines": [
            {
                "line_id": "line_001",
                "gap_type": "framing",
                "text": "Can you clarify?",
                "targets_segment_id": "seg_b",
                "placement": "before",
                "delivery": "record",
            },
            {
                "line_id": "line_002",
                "gap_type": "followup",
                "text": "Thanks.",
                "targets_segment_id": "seg_a",
                "placement": "after",
                "delivery": "record",
            },
        ]
    }
    vo_files: dict[str, Path] = {}
    for lid in ("line_001", "line_002"):
        p = tmp_path / "vo_pickup" / f"{lid}.wav"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x00")
        vo_files[lid] = p

    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a", "seg_b"]},
        segments_by_id=_segments(),
        gap_report=gap_report,
        transitions={
            "transitions": [
                {
                    "after_segment_id": "seg_a",
                    "before_segment_id": "seg_b",
                    "text": "Moving on.",
                    "type": "bridge",
                }
            ]
        },
        resolve_vo_path=lambda line: vo_files.get(line.get("line_id", "")),
        vo_relpath=lambda p: f"vo_pickup/{p.name}",
        vo_duration_ms=lambda _p: 2_000,
    )

    types = [c["type"] for c in edl["clips"] if c["type"] != "silence"]
    # One spoken host turn per seam: before-VO on seg_b covers the pair;
    # after-VO + transition are not stacked.
    assert types == ["speech", "vo_pickup", "speech"]

    vo_before = next(c for c in edl["clips"] if c.get("line_id") == "line_001")
    assert vo_before["placement"] == "before"
    assert vo_before["targets_segment_id"] == "seg_b"
    assert not any(c.get("line_id") == "line_002" for c in edl["clips"])

    speech_a = edl["clips"][0]
    assert speech_a["timeline_start_ms"] == 0
    assert speech_a["duration_ms"] == 10_000

    assert edl["vo_pickup_clip_count"] == 1
    assert "transition" not in types
    assert len(edl["gap_placements"]) == 1
    assert edl["timeline_duration_ms"] >= 10_000 + 2_000 + 15_000


def test_edl_never_emits_a_sentence_twice_for_different_targets(tmp_path: Path) -> None:
    vo_files: dict[str, Path] = {}
    for lid in ("line_a", "line_b"):
        path = tmp_path / f"{lid}.wav"
        path.write_bytes(b"\x00")
        vo_files[lid] = path
    gap_report = {
        "interviewer_lines": [
            {
                "line_id": "line_a",
                "text": "What changed after the deal?",
                "targets_segment_id": "seg_a",
                "placement": "before",
                "delivery": "record",
            },
            {
                "line_id": "line_b",
                "text": "What changed after the deal?",
                "targets_segment_id": "seg_b",
                "placement": "before",
                "delivery": "record",
            },
        ]
    }

    with pytest.raises(ValueError, match="duplicate spoken sentence"):
        build_flow1_edl(
            selection={"ordered_segment_ids": ["seg_a", "seg_b"]},
            segments_by_id=_segments(),
            gap_report=gap_report,
            resolve_vo_path=lambda line: vo_files.get(line.get("line_id", "")),
            vo_duration_ms=lambda _path: 2_000,
        )


def test_run_edl_applies_nle_to_selection_and_edl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S5: NLE must already be on disk selection; EDL refuses dual-copy apply."""
    monkeypatch.setattr(assembly, "check_narrative_qc", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "interview_mux.edl_narrative_remutate.narrative_audit_blocks_edl",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "interview_mux.nugget_layup.assert_layup_fresh_vs_selection",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.nugget_layup.assert_gap_report_layup_authority",
        lambda *_a, **_k: None,
    )
    ctx = isolated_run_ctx(tmp_path, "run_206")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_a", start_ms=0, end_ms=10_000),
            minimal_manifest_segment("seg_b", start_ms=10_000, end_ms=20_000),
            minimal_manifest_segment("seg_c", start_ms=20_000, end_ms=30_000),
        ),
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_a", "seg_b", "seg_c"], "excluded_segment_ids": []},
    )
    ctx.write_json(
        "segments/nle_edits.json",
        {
            "sequence_order": ["seg_c", "seg_a"],
            "segment_overrides": {"seg_b": {"excluded": True}},
        },
    )

    with pytest.raises(SystemExit, match="NLE operator edits not committed"):
        assembly.run_edl(ctx)


def test_edl_skips_non_record_delivery() -> None:
    gap_report = {
        "interviewer_lines": [
            {
                "line_id": "line_x",
                "gap_type": "framing",
                "text": "TBD",
                "targets_segment_id": "seg_a",
                "placement": "before",
                "delivery": "synthesize",
            },
        ]
    }
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a"]},
        segments_by_id=_segments(),
        gap_report=gap_report,
    )
    assert edl["vo_pickup_clip_count"] == 0
    assert len(edl["clips"]) == 1


def test_opening_orientation_precedes_music_without_native_hook(
    tmp_path: Path,
) -> None:
    wav = tmp_path / "vo_preface.wav"
    wav.write_bytes(b"\x00")
    gap_report = {
        "interviewer_lines": [
            {
                "line_id": "vo_preface_episode_orientation",
                "gap_type": "missing_setup",
                "line_category": "episode_preface",
                "episode_orientation": True,
                "opening_sequence": "intro_music_body",
                "text": "This conversation is about the company and the stakes.",
                "targets_segment_id": "seg_a",
                "placement": "before",
                "delivery": "synthesize",
            }
        ]
    }
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a"]},
        segments_by_id=_segments(),
        gap_report=gap_report,
        resolve_vo_path=lambda _line: wav,
        vo_duration_ms=lambda _path: 2_000,
    )
    assert [
        (clip["type"], clip.get("air_kind"))
        for clip in edl["clips"]
    ][:3] == [
        ("vo_pickup", None),
        ("silence", "opening_music"),
        ("speech", None),
    ]


def test_native_open_omit_places_music_before_body() -> None:
    gap_report = {
        "opening_orientation": {
            "required": False,
            "omitted": True,
            "omit_reason": "native_open_self_orients",
            "sequence": "music_body",
            "target_segment_id": "seg_a",
        },
        "interviewer_lines": [],
    }
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a"]},
        segments_by_id=_segments(),
        gap_report=gap_report,
    )
    assert [
        (clip["type"], clip.get("air_kind"))
        for clip in edl["clips"]
    ][:2] == [
        ("silence", "opening_music"),
        ("speech", None),
    ]
    assert not any(clip.get("type") == "vo_pickup" for clip in edl["clips"])


def test_missing_orientation_wav_is_warned_not_silent_clip() -> None:
    gap_report = {
        "interviewer_lines": [
            {
                "line_id": "vo_preface_episode_orientation",
                "gap_type": "missing_setup",
                "line_category": "episode_preface",
                "episode_orientation": True,
                "opening_sequence": "intro_music_body",
                "text": "This conversation is about the company and the stakes.",
                "targets_segment_id": "seg_a",
                "placement": "before",
                "delivery": "synthesize",
            }
        ]
    }
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a"]},
        segments_by_id=_segments(),
        gap_report=gap_report,
        resolve_vo_path=lambda _line: None,
    )
    assert not any(
        c.get("line_id") == "vo_preface_episode_orientation" for c in edl["clips"]
    )
    assert "vo_preface_episode_orientation" in edl["warnings"]["missing_vo_files"]


def test_opening_music_marker_present_when_vo_duration_is_zero(tmp_path: Path) -> None:
    wav = tmp_path / "vo_preface.wav"
    wav.write_bytes(b"\x00")
    gap_report = {
        "interviewer_lines": [
            {
                "line_id": "vo_preface_episode_orientation",
                "gap_type": "missing_setup",
                "line_category": "episode_preface",
                "episode_orientation": True,
                "opening_sequence": "intro_music_body",
                "text": "This conversation is about the company and the stakes.",
                "targets_segment_id": "seg_a",
                "placement": "before",
                "delivery": "synthesize",
            }
        ]
    }
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a"]},
        segments_by_id=_segments(),
        gap_report=gap_report,
        resolve_vo_path=lambda _line: wav,
        vo_duration_ms=lambda _path: 0,
    )
    assert (
        sum(1 for c in edl["clips"] if c.get("air_kind") == "opening_music") == 1
    )
    assert any(
        c.get("type") == "vo_pickup"
        and c.get("line_id") == "vo_preface_episode_orientation"
        for c in edl["clips"]
    )


def test_cold_open_with_many_before_vo_keeps_orientation_early(
    tmp_path: Path,
) -> None:
    """Hook before-VO must not push orientation past max_non_silence_index=3."""
    from interview_mux.opening_orientation import validate_opening_orientation

    wav = tmp_path / "vo.wav"
    wav.write_bytes(b"\x00")
    gap_report = {
        "interviewer_lines": [
            {
                "line_id": "vo_preface_episode_orientation",
                "gap_type": "missing_setup",
                "line_category": "episode_preface",
                "episode_orientation": True,
                "opening_sequence": "native_hook_music_intro_body",
                "orientation_missions": [
                    "guest_identity",
                    "conversation_topic",
                    "listener_stakes",
                ],
                "text": "This conversation is about the company and the stakes.",
                "targets_segment_id": "seg_a",
                "placement": "after",
                "delivery": "synthesize",
            },
            *[
                {
                    "line_id": f"vo_hook_{i}",
                    "origin": "nugget_layup",
                    "text": f"Hook setup line number {i} with enough words here.",
                    "targets_segment_id": "seg_a",
                    "placement": "before",
                    "delivery": "synthesize",
                }
                for i in range(4)
            ],
        ]
    }
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a", "seg_b"]},
        segments_by_id=_segments(),
        gap_report=gap_report,
        resolve_vo_path=lambda _line: wav,
        vo_duration_ms=lambda _path: 2_000,
    )
    errors = validate_opening_orientation(gap_report=gap_report, edl=edl)
    assert not any("too_late" in e for e in errors), errors
    non_silence = [c for c in edl["clips"] if c.get("type") != "silence"]
    orient_idx = next(
        i
        for i, c in enumerate(non_silence)
        if c.get("line_id") == "vo_preface_episode_orientation"
    )
    assert orient_idx <= 3
    assert non_silence[0]["type"] == "speech"


def test_cold_open_orientation_not_stacked_with_next_layup(tmp_path: Path) -> None:
    wav = tmp_path / "vo.wav"
    wav.write_bytes(b"\x00")
    gap_report = {
        "interviewer_lines": [
            {
                "line_id": "vo_preface_episode_orientation",
                "gap_type": "missing_setup",
                "line_category": "episode_preface",
                "episode_orientation": True,
                "opening_sequence": "native_hook_music_intro_body",
                "text": "This conversation is about the company and the stakes.",
                "targets_segment_id": "seg_a",
                "placement": "after",
                "delivery": "synthesize",
            },
            {
                "line_id": "vo_layup_seg_b",
                "origin": "nugget_layup",
                "text": "Next he explains the employee test and why it mattered.",
                "targets_segment_id": "seg_b",
                "placement": "before",
                "delivery": "synthesize",
            },
        ]
    }
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a", "seg_b"]},
        segments_by_id=_segments(),
        gap_report=gap_report,
        resolve_vo_path=lambda _line: wav,
        vo_duration_ms=lambda _path: 2_000,
    )
    line_ids = [c.get("line_id") for c in edl["clips"] if c.get("line_id")]
    assert "vo_preface_episode_orientation" in line_ids
    # nugget_layup is an EDL survivor after orientation (hosted floor / exec_13183).
    assert "vo_layup_seg_b" in line_ids
    assert line_ids.index("vo_preface_episode_orientation") < line_ids.index(
        "vo_layup_seg_b"
    )


def test_native_hook_precedes_music_and_orientation(tmp_path: Path) -> None:
    wav = tmp_path / "vo_preface.wav"
    wav.write_bytes(b"\x00")
    gap_report = {
        "interviewer_lines": [
            {
                "line_id": "vo_preface_episode_orientation",
                "gap_type": "missing_setup",
                "line_category": "episode_preface",
                "episode_orientation": True,
                "opening_sequence": "native_hook_music_intro_body",
                "text": "This conversation is about the company and the stakes.",
                "targets_segment_id": "seg_a",
                "placement": "after",
                "delivery": "synthesize",
            }
        ]
    }
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a", "seg_b"]},
        segments_by_id=_segments(),
        gap_report=gap_report,
        resolve_vo_path=lambda _line: wav,
        vo_duration_ms=lambda _path: 2_000,
    )
    assert [
        (clip["type"], clip.get("air_kind"))
        for clip in edl["clips"]
    ][:4] == [
        ("speech", None),
        ("silence", "opening_music"),
        ("vo_pickup", None),
        ("silence", "after_vo"),
    ]
    assert edl["clips"][-1]["type"] == "speech"


def _minimal_wav_bytes(*, duration_ms: int = 100) -> bytes:
    buf = io.BytesIO()
    rate = 48000
    frames = max(1, int(rate * duration_ms / 1000))
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


def test_run_preview_renders_speech_and_vo(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run_001"
    (run_dir / "ingest").mkdir(parents=True, exist_ok=True)
    (run_dir / "vo_pickup").mkdir(parents=True, exist_ok=True)
    (run_dir / "master").mkdir(parents=True, exist_ok=True)
    (run_dir / "ingest" / "normalized.wav").write_bytes(b"\x00")
    (run_dir / "vo_pickup" / "line_001.wav").write_bytes(b"\x00")

    edl = {
        "clips": [
            {"type": "speech", "source_start_ms": 0, "source_end_ms": 1000},
            {
                "type": "vo_pickup",
                "line_id": "line_001",
                "source_path": "vo_pickup/line_001.wav",
            },
        ]
    }

    class FakeCtx:
        def __init__(self) -> None:
            self.run_dir = run_dir
            self.logs: list[tuple[str, str, str]] = []
            self.done: list[str] = []

        def read_json(self, rel: str) -> dict:
            assert rel == "master/edl.json"
            return edl

        def path(self, *parts: str) -> Path:
            return self.run_dir.joinpath(*parts)

        def read_path(self, *parts: str) -> Path:
            return self.path(*parts)

        def log(self, message: str, *, level: str, stage: str, detail: str | None = None, **kwargs) -> None:
            self.logs.append((level, stage, message if detail is None else f"{message}::{detail}"))

        def mark_done(self, stage: str) -> None:
            self.done.append(stage)

    ffmpeg_calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs):
        ffmpeg_calls.append(cmd)
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(_minimal_wav_bytes())
        from subprocess import CompletedProcess

        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("interview_mux.operator_subprocess.subprocess.run", fake_run)

    ctx = FakeCtx()
    preview = assembly.run_preview(ctx)

    assert preview == run_dir / "master" / "assembly_preview.wav"
    assert preview.is_file()
    assert ctx.done == ["assembly_preview"]
    assert any(stage == "assembly_preview" and level == "success" for level, stage, _ in ctx.logs)
    assert len(ffmpeg_calls) == 2


def test_run_preview_missing_vo_raises(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run_002"
    (run_dir / "ingest").mkdir(parents=True, exist_ok=True)
    (run_dir / "master").mkdir(parents=True, exist_ok=True)
    (run_dir / "ingest" / "normalized.wav").write_bytes(b"\x00")

    edl = {
        "clips": [
            {"type": "speech", "source_start_ms": 0, "source_end_ms": 1000},
            {
                "type": "vo_pickup",
                "line_id": "line_missing",
                "source_path": "vo_pickup/line_missing.wav",
            },
        ]
    }

    class FakeCtx:
        def __init__(self) -> None:
            self.run_dir = run_dir
            self.logs: list[tuple[str, str | None]] = []

        def read_json(self, rel: str) -> dict:
            return edl

        def path(self, *parts: str) -> Path:
            return self.run_dir.joinpath(*parts)

        def read_path(self, *parts: str) -> Path:
            return self.path(*parts)

        def log(
            self,
            message: str,
            *,
            level: str = "info",
            stage: str | None = None,
            detail: str | dict | None = None,
            **kwargs,
        ) -> None:
            self.logs.append((message, stage))

    monkeypatch.setattr(
        "interview_mux.operator_subprocess.subprocess.run",
        lambda cmd, **kwargs: __import__("subprocess").CompletedProcess(cmd, 0, "", ""),
    )

    with pytest.raises(FileNotFoundError, match="line_missing"):
        assembly.run_preview(FakeCtx())


def test_resync_required_synthesize_wavs_calls_synth_when_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_resync_vo")
    _arm_vo_path(ctx)
    line = {
        "line_id": "vo_preface_episode_orientation",
        "episode_orientation": True,
        "line_category": "episode_preface",
        "text": "This conversation is about the company and the stakes.",
        "targets_segment_id": "seg_a",
        "placement": "before",
        "delivery": "synthesize",
    }
    called: list[str] = []

    def _fake_synth(_ctx, row, *, mode="synthesize"):
        called.append(str(row.get("line_id")))
        out = _ctx.path("vo_pickup", "synthesized", "vo_preface_episode_orientation.wav")
        out.parent.mkdir(parents=True, exist_ok=True)
        rate = 48_000
        with wave.open(str(out), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(b"\x00\x00" * int(rate * 0.3))
        from interview_mux.vo_synthesis_audit import record_synthesis

        record_synthesis(_ctx, row, backend="mlx_audio", out_wav=out)
        return out

    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _fake_synth)
    monkeypatch.setattr(
        "interview_mux.stages.assembly.resolve_vo_pickup_path",
        lambda _ctx, _line: (
            _ctx.path("vo_pickup", "synthesized", "vo_preface_episode_orientation.wav")
            if called
            else None
        ),
    )
    notes = resync_required_synthesize_wavs(ctx, {"interviewer_lines": [line]})
    assert called == ["vo_preface_episode_orientation"]
    assert notes == ["vo_preface_episode_orientation"]


def test_resync_accepts_audit_match_when_resolve_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Post-synth speech-QA resolve miss must not raise when audit already matches."""
    ctx = isolated_run_ctx(tmp_path, "run_resync_match_no_resolve")
    _arm_vo_path(ctx)
    line = {
        "line_id": "vo_layup_seg_019",
        "text": "Cancer data arrive in separate silos across modalities.",
        "targets_segment_id": "seg_019",
        "placement": "before",
        "delivery": "synthesize",
        "required": True,
    }

    def _fake_synth(_ctx, row, *, mode="synthesize"):
        out = _ctx.path("vo_pickup", "synthesized", "vo_layup_seg_019.wav")
        out.parent.mkdir(parents=True, exist_ok=True)
        rate = 48_000
        with wave.open(str(out), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(b"\x00\x00" * int(rate * 0.3))
        from interview_mux.vo_synthesis_audit import record_synthesis

        record_synthesis(
            _ctx, row, backend="chatterbox", out_wav=out, wav_just_rendered=True
        )
        return out

    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _fake_synth)
    monkeypatch.setattr(
        "interview_mux.stages.assembly.resolve_vo_pickup_path",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.gap_framing_enabled",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.resolve_gap_vo_delivery",
        lambda _ctx: "chatterbox",
    )
    notes = resync_required_synthesize_wavs(ctx, {"interviewer_lines": [line]})
    assert notes == ["vo_layup_seg_019"]


def test_resync_under_edl_staging_promotes_owner_vo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EDL-nested resync must stage/promote under vo_synthesize (exec_11630)."""
    from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

    ctx = isolated_run_ctx(tmp_path, "run_resync_nested_edl")
    _arm_vo_path(ctx)
    line = {
        "line_id": "vo_layup_seg_020",
        "text": "Why does counting cells leave clinicians uncertain?",
        "targets_segment_id": "seg_020",
        "placement": "before",
        "delivery": "synthesize",
        "required": True,
    }
    stages: list[str | None] = []

    def _fake_synth(_ctx, row, *, mode="synthesize"):
        from interview_mux.write_staging import active_stage_id

        stages.append(active_stage_id())
        out = _ctx.path("vo_pickup", "synthesized", "vo_layup_seg_020.wav")
        out.parent.mkdir(parents=True, exist_ok=True)
        rate = 48_000
        with wave.open(str(out), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(b"\x00\x00" * int(rate * 0.25))
        from interview_mux.vo_synthesis_audit import record_synthesis

        record_synthesis(
            _ctx, row, backend="chatterbox", out_wav=out, wav_just_rendered=True
        )
        return out

    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _fake_synth)
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.gap_framing_enabled",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.resolve_gap_vo_delivery",
        lambda _ctx: "chatterbox",
    )
    enter_stage_staging("edl")
    try:
        notes = resync_required_synthesize_wavs(ctx, {"interviewer_lines": [line]})
    finally:
        exit_stage_staging()
    assert notes == ["vo_layup_seg_020"]
    assert stages == ["vo_synthesize"]
    assert (ctx.run_dir / "vo_pickup" / "synthesized" / "vo_layup_seg_020.wav").is_file()


def test_build_flow1_edl_active_layup_drops_transition(tmp_path: Path) -> None:
    wav = tmp_path / "vo.wav"
    wav.write_bytes(b"\x00")
    gap_report = {
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_b",
                "origin": "nugget_layup",
                "text": "Next he explains why a live cell is the starting point.",
                "targets_segment_id": "seg_b",
                "placement": "before",
                "delivery": "synthesize",
            }
        ]
    }
    transitions = {
        "transitions": [
            {
                "after_segment_id": "seg_a",
                "before_segment_id": "seg_b",
                "text": "That capture model is the setup — next, what a live cell actually lets you do.",
                "type": "spoken_bridge",
            }
        ]
    }
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a", "seg_b"]},
        segments_by_id=_segments(),
        gap_report=gap_report,
        transitions=transitions,
        resolve_vo_path=lambda _line: wav,
        vo_duration_ms=lambda _path: 2_000,
        resolve_transition_path=lambda _a, _b: wav,
    )
    synth = [
        c
        for c in edl["clips"]
        if c.get("type") in {"vo_pickup", "transition"}
    ]
    assert len(synth) == 1
    assert synth[0].get("type") == "vo_pickup"
    assert synth[0].get("line_id") == "vo_layup_seg_b"


def test_build_flow1_edl_skipped_layup_keeps_only_transition(tmp_path: Path) -> None:
    wav = tmp_path / "vo.wav"
    wav.write_bytes(b"\x00")
    gap_report = {
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_b",
                "origin": "nugget_layup",
                "skipped_optional": True,
                "text": "The native describes the claimed data?",
                "targets_segment_id": "seg_b",
                "placement": "before",
                "delivery": "synthesize",
            }
        ]
    }
    transitions = {
        "transitions": [
            {
                "after_segment_id": "seg_a",
                "before_segment_id": "seg_b",
                "text": "That capture model is the setup — next, what a live cell actually lets you do.",
                "type": "spoken_bridge",
            }
        ]
    }
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_a", "seg_b"]},
        segments_by_id=_segments(),
        gap_report=gap_report,
        transitions=transitions,
        resolve_vo_path=lambda _line: wav,
        vo_duration_ms=lambda _path: 2_000,
        resolve_transition_path=lambda _a, _b: wav,
    )
    synth = [
        c
        for c in edl["clips"]
        if c.get("type") in {"vo_pickup", "transition"}
    ]
    assert len(synth) == 1
    assert synth[0].get("type") == "transition"
