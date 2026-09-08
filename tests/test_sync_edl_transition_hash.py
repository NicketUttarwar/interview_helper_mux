"""EDL script_hash sync covers transition clips as well as vo_pickup."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from interview_mux.spoken_copy_guard import script_hash
from interview_mux.vo_synthesis_audit import sync_edl_vo_script_metadata


def test_sync_edl_restamps_transition_script_hash(tmp_path: Path, monkeypatch) -> None:
    text = "Bridge spoken text."
    expected = script_hash(text)
    wav = tmp_path / "master" / "transitions" / "tr_a_b.wav"
    wav.parent.mkdir(parents=True)
    wav.write_bytes(b"RIFF" + b"\x00" * 64)

    edl = {
        "clips": [
            {
                "type": "transition",
                "after_segment_id": "seg_a",
                "before_segment_id": "seg_b",
                "text": text,
                "script_hash": "stalehash",
                "source_path": "master/transitions/tr_a_b.wav",
                "duration_ms": 0,
            }
        ]
    }

    ctx = MagicMock()
    ctx.run_dir = tmp_path
    ctx.artifact_exists.side_effect = lambda rel: True
    store = {
        "master/edl.json": edl,
        "master/transitions.json": {
            "transitions": [
                {
                    "after_segment_id": "seg_a",
                    "before_segment_id": "seg_b",
                    "text": text,
                }
            ]
        },
        "understanding/gap_report.json": {"interviewer_lines": []},
    }

    def read_json(rel):
        return store[rel]

    def write_live(_ctx, doc, source=None):
        store["master/edl.json"] = doc

    ctx.read_json.side_effect = read_json
    ctx.read_path.side_effect = lambda rel: tmp_path / rel
    monkeypatch.setattr(
        "interview_mux.omit_ledger.reconcile_edl_with_omit_ledger",
        lambda _ctx: {"removed": []},
    )
    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit._vo_pickup_script_lines",
        lambda _ctx: {},
    )
    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit._wav_duration_ms",
        lambda _p: 2500,
    )
    monkeypatch.setattr(
        "interview_mux.air_order.write_live_edl",
        write_live,
    )

    report = sync_edl_vo_script_metadata(ctx)
    assert report["updated"] == 1
    clip = store["master/edl.json"]["clips"][0]
    assert clip["script_hash"] == expected
    assert clip["duration_ms"] == 2500
