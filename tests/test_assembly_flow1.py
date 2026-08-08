from __future__ import annotations

import io
import wave
from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.stages import assembly
from interview_mux.stages.assembly import build_flow1_edl
from run_fixtures import minimal_manifest, minimal_manifest_segment


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


def test_run_edl_applies_nle_to_selection_and_edl(monkeypatch) -> None:
    monkeypatch.setattr(assembly, "check_narrative_qc", lambda *_a, **_k: None)
    monkeypatch.setattr(assembly, "check_edl_qc", lambda *_a, **_k: None)
    monkeypatch.setattr(assembly, "check_edl_narrative_qc", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "interview_mux.synthetic_framing.synthetic_framing_cfg",
        lambda cfg=None: {
            "respect_native_speakers": True,
            "allow_canned_bridge_fallback": True,
            "duration_ratio_min": 0.4,
            "duration_ratio_max": 2.0,
        },
    )

    def _fake_synth_transitions(ctx):
        from interview_mux.transition_vo import transition_wav_path

        if not ctx.artifact_exists("master/transitions.json"):
            return []
        doc = ctx.read_json("master/transitions.json")
        rows = []
        for item in doc.get("transitions") or []:
            if not isinstance(item, dict):
                continue
            after_id = str(item.get("after_segment_id") or "")
            before_id = str(item.get("before_segment_id") or "")
            if not after_id or not before_id:
                continue
            out = transition_wav_path(ctx, after_id, before_id)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(_minimal_wav_bytes(duration_ms=800))
            rows.append(
                {
                    "after_segment_id": after_id,
                    "before_segment_id": before_id,
                    "ok": True,
                    "path": str(out),
                }
            )
        return rows

    monkeypatch.setattr(
        "interview_mux.transition_vo.synthesize_spoken_transitions",
        _fake_synth_transitions,
    )
    ctx = RunContext("run_206", create=True)
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

    assembly.run_edl(ctx)

    selection = ctx.read_json("master/selection.json")
    assert selection["ordered_segment_ids"] == ["seg_c", "seg_a"]
    assert selection.get("nle_applied") is True
    assert any(
        e.get("segment_id") == "seg_b" for e in selection.get("excluded_segment_ids") or []
    )

    edl = ctx.read_json("master/edl.json")
    speech_ids = [c["segment_id"] for c in edl["clips"] if c.get("type") == "speech"]
    assert "seg_b" not in speech_ids
    assert speech_ids == ["seg_c", "seg_a"]
    assert ctx.is_done("edl")


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
