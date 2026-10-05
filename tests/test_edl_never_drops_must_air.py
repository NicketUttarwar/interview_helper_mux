"""No EDL write leaves a must-air keep without a clip (ISSUES 179).

exec_025: the never-touch clamp deleted every speech clip under 400 ms, even
one it never clamped (seg_021, 280 ms after an overlap trim), labelled it
"dropped_unplayable_never_touch" and asked the selection to drop it; removal
authority refused (must-air), the EDL and selection disagreed, and the EDL
stage refused itself to the invoke cap.
"""

from __future__ import annotations

from pathlib import Path

import interview_mux.removal_authority as removal_authority
from interview_mux.air_order import restore_protected_speech_clips
from interview_mux.media_ip_cta import clamp_edl_speech_away_from_never_touch
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment


def _speech(sid: str, s: int, e: int) -> dict:
    return {"segment_id": sid, "type": "speech", "source_start_ms": s, "source_end_ms": e, "duration_ms": e - s}


def test_clamp_keeps_a_protected_short_clip_it_did_not_clamp(tmp_path: Path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_nt_untouched")
    monkeypatch.setattr(removal_authority, "protected_segment_ids", lambda *a, **k: {"seg_b"})
    edl = {"clips": [_speech("seg_a", 0, 10_000), _speech("seg_b", 20_000, 20_280)]}
    out, rows = clamp_edl_speech_away_from_never_touch(ctx, edl, intervals=[(50_000, 60_000, "cta")])
    assert [c["segment_id"] for c in out["clips"]] == ["seg_a", "seg_b"]
    assert not rows


def test_clamp_labels_an_unprotected_short_drop_honestly(tmp_path: Path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_nt_short")
    monkeypatch.setattr(removal_authority, "protected_segment_ids", lambda *a, **k: set())
    edl = {"clips": [_speech("seg_a", 0, 10_000), _speech("seg_b", 20_000, 20_280)]}
    out, rows = clamp_edl_speech_away_from_never_touch(ctx, edl, intervals=[(50_000, 60_000, "cta")])
    assert [c["segment_id"] for c in out["clips"]] == ["seg_a"]
    assert rows and rows[-1]["notes"] == ["dropped_unplayable_short"]


def test_clamp_keeps_a_protected_clip_it_shortened(tmp_path: Path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_nt_protected")
    monkeypatch.setattr(removal_authority, "protected_segment_ids", lambda *a, **k: {"seg_b"})
    edl = {"clips": [_speech("seg_a", 0, 10_000), _speech("seg_b", 20_000, 21_000)]}
    out, _rows = clamp_edl_speech_away_from_never_touch(ctx, edl, intervals=[(20_200, 30_000, "cta")])
    clip = next(c for c in out["clips"] if c["segment_id"] == "seg_b")
    assert clip["source_end_ms"] <= 20_200


def test_clamp_still_drops_an_unprotected_clip_it_shortened(tmp_path: Path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_nt_unprotected")
    monkeypatch.setattr(removal_authority, "protected_segment_ids", lambda *a, **k: set())
    edl = {"clips": [_speech("seg_a", 0, 10_000), _speech("seg_b", 20_000, 21_000)]}
    out, _rows = clamp_edl_speech_away_from_never_touch(ctx, edl, intervals=[(20_200, 30_000, "cta")])
    assert [c["segment_id"] for c in out["clips"]] == ["seg_a"]


def test_writer_reseats_a_must_air_keep_the_edl_lost(tmp_path: Path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_reseat")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_026", start_ms=1_933_820, end_ms=2_093_819),
            minimal_manifest_segment("seg_025", start_ms=1_899_160, end_ms=1_933_460),
            minimal_manifest_segment("seg_021", start_ms=1_668_620, end_ms=1_716_080),
            minimal_manifest_segment("seg_028", start_ms=2_122_380, end_ms=2_200_000),
        ),
    )
    (ctx.run_dir / "master").mkdir(exist_ok=True)
    import json

    (ctx.run_dir / "master" / "selection.json").write_text(
        json.dumps({"ordered_segment_ids": ["seg_026", "seg_025", "seg_021", "seg_028"]})
    )
    monkeypatch.setattr(removal_authority, "protected_segment_ids", lambda *a, **k: {"seg_021"})
    edl = {
        "clips": [
            _speech("seg_026", 1_933_820, 2_093_819),
            _speech("seg_025", 1_899_160, 1_933_460),
            {"type": "transition", "duration_ms": 3000},
            _speech("seg_028", 2_122_380, 2_200_000),
        ],
        "ordered_segment_ids": ["seg_026", "seg_025", "seg_028"],
        "omitted_unplayable_segment_ids": ["seg_021"],
    }
    restored = restore_protected_speech_clips(ctx, edl)
    assert restored == ["seg_021"]
    speech = [c for c in edl["clips"] if c.get("type") == "speech"]
    assert [c["segment_id"] for c in speech] == ["seg_026", "seg_025", "seg_021", "seg_028"]
    clip = speech[2]
    assert (clip["source_start_ms"], clip["source_end_ms"]) == (1_668_620, 1_716_080)
    assert edl["ordered_segment_ids"] == ["seg_026", "seg_025", "seg_021", "seg_028"]
    assert edl["omitted_unplayable_segment_ids"] == []
    starts = [c["timeline_start_ms"] for c in edl["clips"]]
    assert starts == sorted(starts)


def test_writer_reseats_a_must_air_clip_seated_on_foreign_tape(tmp_path: Path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_reseat_foreign")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_026", start_ms=1_933_820, end_ms=2_093_819),
            minimal_manifest_segment("seg_021", start_ms=1_668_620, end_ms=1_716_080),
        ),
    )
    (ctx.run_dir / "master").mkdir(exist_ok=True)
    import json

    (ctx.run_dir / "master" / "selection.json").write_text(
        json.dumps({"ordered_segment_ids": ["seg_026", "seg_021"]})
    )
    monkeypatch.setattr(removal_authority, "protected_segment_ids", lambda *a, **k: {"seg_021"})
    edl = {"clips": [_speech("seg_026", 1_933_820, 2_093_819), _speech("seg_021", 1_933_540, 1_933_820)]}
    assert restore_protected_speech_clips(ctx, edl) == ["seg_021"]
    clip = edl["clips"][1]
    assert (clip["source_start_ms"], clip["source_end_ms"]) == (1_668_620, 1_716_080)


def test_writer_leaves_an_unprotected_drop_alone(tmp_path: Path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_reseat_free")
    (ctx.run_dir / "master").mkdir(exist_ok=True)
    import json

    (ctx.run_dir / "master" / "selection.json").write_text(
        json.dumps({"ordered_segment_ids": ["seg_a", "seg_b"]})
    )
    monkeypatch.setattr(removal_authority, "protected_segment_ids", lambda *a, **k: set())
    edl = {"clips": [_speech("seg_a", 0, 10_000)]}
    assert restore_protected_speech_clips(ctx, edl) == []
    assert len(edl["clips"]) == 1
