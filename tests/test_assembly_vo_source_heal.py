"""assembly_preview heals vo_pickup clips missing source_path when WAV exists."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from interview_mux.stages import assembly


def test_heal_vo_pickup_clip_source_uses_gap_line(tmp_path, monkeypatch):
    wav = tmp_path / "vo_pickup" / "synthesized" / "vo_layup_seg_008.wav"
    wav.parent.mkdir(parents=True)
    wav.write_bytes(b"RIFF....")

    clip = {
        "type": "vo_pickup",
        "line_id": "vo_layup_seg_008",
        "targets_segment_id": "seg_008",
        "duration_ms": 0,
        # stale / thin EDL fields — no source_path, wrong hash
        "script_hash": "deadbeef",
    }
    gap_line = {
        "line_id": "vo_layup_seg_008",
        "targets_segment_id": "seg_008",
        "text": "Tissue biopsy can mean surgery.",
        "delivery": "synthesize",
        "script_hash": "goodhash",
    }

    ctx = MagicMock()
    ctx.read_json.return_value = {"interviewer_lines": [gap_line]}
    ctx.run_dir = tmp_path
    ctx.final_path.side_effect = lambda *parts: tmp_path.joinpath(*parts)

    resolved = tmp_path / "vo_pickup" / "synthesized" / "vo_layup_seg_008.wav"

    def fake_resolve(_ctx, line):
        assert line.get("text") == gap_line["text"]
        assert line.get("script_hash") == "goodhash"
        return resolved

    monkeypatch.setattr(assembly, "resolve_vo_pickup_path", fake_resolve)
    monkeypatch.setattr(assembly, "_wav_duration_ms", lambda _p: 4320)

    path = assembly.heal_vo_pickup_clip_source(ctx, clip)
    assert path == resolved
    assert clip["source_path"] == "vo_pickup/synthesized/vo_layup_seg_008.wav"
    assert clip["duration_ms"] == 4320


def test_heal_vo_pickup_clip_source_skips_when_present():
    clip = {"type": "vo_pickup", "line_id": "x", "source_path": "vo_pickup/x.wav"}
    ctx = MagicMock()
    assert assembly.heal_vo_pickup_clip_source(ctx, clip) is None
    ctx.read_json.assert_not_called()


def test_gap_line_enrich_prefers_gap_text():
    ctx = MagicMock()
    ctx.read_json.return_value = {
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_008",
                "text": "Authoritative script.",
                "script_hash": "abc",
                "delivery": "synthesize",
            }
        ]
    }
    clip = {"type": "vo_pickup", "line_id": "vo_layup_seg_008", "script_hash": "stale"}
    merged = assembly._gap_line_for_vo_clip(ctx, clip)
    assert merged["text"] == "Authoritative script."
    assert merged["script_hash"] == "abc"
