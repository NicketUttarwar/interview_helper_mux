from __future__ import annotations

from pathlib import Path

from interview_mux.stages import assembly_flow1
from interview_mux.stages.assembly_flow1 import build_flow1_edl


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

    types = [c["type"] for c in edl["clips"]]
    assert types == [
        "speech",
        "vo_pickup",
        "transition",
        "vo_pickup",
        "speech",
    ]

    vo_before = next(c for c in edl["clips"] if c.get("line_id") == "line_001")
    assert vo_before["placement"] == "before"
    assert vo_before["targets_segment_id"] == "seg_b"
    assert vo_before["timeline_start_ms"] == 12_000  # after seg_a, after-VO, transition anchor

    speech_a = edl["clips"][0]
    assert speech_a["timeline_start_ms"] == 0
    assert speech_a["duration_ms"] == 10_000

    assert edl["vo_pickup_clip_count"] == 2
    assert edl["timeline_duration_ms"] == 10_000 + 2_000 + 0 + 2_000 + 15_000
    assert len(edl["gap_placements"]) == 2


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


def test_run_preview_renders_speech_and_vo(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run_001"
    (run_dir / "ingest").mkdir(parents=True, exist_ok=True)
    (run_dir / "vo_pickup").mkdir(parents=True, exist_ok=True)
    (run_dir / "flow_1_master").mkdir(parents=True, exist_ok=True)
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
            {
                "type": "vo_pickup",
                "line_id": "line_missing",
                "source_path": "vo_pickup/line_missing.wav",
            },
            {"type": "transition", "text": "bridge"},
        ]
    }

    class FakeCtx:
        def __init__(self) -> None:
            self.run_dir = run_dir
            self.logs: list[tuple[str, str, str]] = []
            self.done: list[str] = []

        def read_json(self, rel: str) -> dict:
            assert rel == "flow_1_master/edl.json"
            return edl

        def path(self, *parts: str) -> Path:
            return self.run_dir.joinpath(*parts)

        def log(self, message: str, *, level: str, stage: str, detail: str | None = None) -> None:
            self.logs.append((level, stage, message if detail is None else f"{message}::{detail}"))

        def mark_done(self, stage: str) -> None:
            self.done.append(stage)

    ffmpeg_calls: list[list[str]] = []

    def fake_run(cmd: list[str], check: bool, capture_output: bool, text: bool = False):
        ffmpeg_calls.append(cmd)
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x00")
        return None

    monkeypatch.setattr(assembly_flow1.subprocess, "run", fake_run)

    ctx = FakeCtx()
    preview = assembly_flow1.run_preview(ctx)

    assert preview == run_dir / "flow_1_master" / "assembly_preview.wav"
    assert preview.is_file()
    assert ctx.done == ["assembly_preview"]
    assert any(stage == "assembly_preview" and level == "success" for level, stage, _ in ctx.logs)
    assert any(stage == "assembly_preview" and level == "warning" for level, stage, _ in ctx.logs)
    assert len(ffmpeg_calls) == 3
