from __future__ import annotations

from pathlib import Path

from interview_mux.diarization_suspicion import (
    absorbable_micro_runs,
    detect_speaker_flips,
    forced_diarization_fuse_verdicts,
    run_diarization_verify,
)
from interview_mux.gap_vo_prior_context import CLAUSE_CONTINUE_MAX_GAP_MS, is_filled_pause_only_text
from interview_mux.interview_spine.windows import build_windows
from interview_mux.prompt_validation import validate_diarization_repairs
from interview_mux.run_context import RunContext
from interview_mux.segment_fuse import apply_connector_fuses
from interview_mux.segment_id_remap import apply_full_segment_id_remap
from run_fixtures import patch_executions_root


def _w(text: str, start: int, *, spk: str, dur: int = 180) -> dict:
    return {"text": text, "start_ms": start, "end_ms": start + dur, "speaker_id": spk}


def _seg_row(sid: str, start: int, end: int, text: str, spk: str = "spk_1") -> dict:
    return {
        "segment_id": sid,
        "start_ms": start,
        "end_ms": end,
        "text": text,
        "speaker_id": spk,
        "type": "interviewee_answer" if spk == "spk_1" else "interviewer_reaction",
        "speaker_role": "interviewee" if spk == "spk_1" else "interviewer",
        "topic_tags": [],
    }


def _fill(spk: str, start: int, end: int, *, stem: str = "w", step: int = 220) -> list[dict]:
    words: list[dict] = []
    t = start
    i = 0
    while t + 180 <= end:
        words.append(_w(f"{stem}{i}", t, spk=spk, dur=180))
        t += step
        i += 1
    return words


def test_detect_flip_at_novel_1080() -> None:
    t = 1_785_000
    words = [
        _w("a", t, spk="spk_1"),
        _w("very", t + 200, spk="spk_1"),
        _w("novel", t + 400, spk="spk_1"),
        _w("1080", t + 400 + 180 + 1120, spk="spk_0"),
        _w("gene", t + 400 + 180 + 1120 + 200, spk="spk_0"),
    ]
    flips = detect_speaker_flips(words)
    assert len(flips) == 1
    assert flips[0]["from_speaker_id"] == "spk_1"
    assert flips[0]["to_speaker_id"] == "spk_0"
    assert flips[0]["gap_ms"] == 1120
    assert flips[0]["hanging_setup"] is True
    assert flips[0]["gap_ms"] <= CLAUSE_CONTINUE_MAX_GAP_MS


def test_hanging_flips_sort_first() -> None:
    words = [
        *_fill("spk_0", 0, 2000, stem="h"),
        _w("hello", 2500, spk="spk_1"),
        *_fill("spk_1", 10_000, 12_000, stem="a"),
        _w("a", 12_200, spk="spk_1"),
        _w("very", 12_400, spk="spk_1"),
        _w("novel", 12_600, spk="spk_1"),
        _w("1080", 12_600 + 180 + 800, spk="spk_0"),
    ]
    flips = detect_speaker_flips(words)
    assert flips
    assert flips[0]["hanging_setup"] is True
    assert flips[0]["next_text"] == "1080"


def test_verify_yes_relabels_later_run(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("relabel_yes", create=True)
    t = 1_785_000
    words = [
        _w("a", t, spk="spk_1"),
        _w("very", t + 200, spk="spk_1"),
        _w("novel", t + 400, spk="spk_1"),
        _w("1080", t + 400 + 180 + 1120, spk="spk_0"),
        _w("gene", t + 400 + 180 + 1120 + 200, spk="spk_0"),
        _w("panel", t + 400 + 180 + 1120 + 400, spk="spk_0"),
        _w("Host", 2_000_000, spk="spk_0"),
    ]
    ctx.write_json("transcript/full.json", {"words": words})
    ctx.write_json(
        "transcript/speaker_flows.json",
        {"version": 1, "flows": [{"speaker_id": "spk_0", "start_ms": 0}]},
        skip_handoff=True,
    )
    (ctx.run_dir / "ingest").mkdir(exist_ok=True)
    (ctx.run_dir / "ingest" / "normalized.wav").write_bytes(b"RIFF" + b"\x00" * 40)

    def yes_fn(a, b):  # noqa: ARG001
        return "YES"

    monkeypatch.setattr(
        "interview_mux.diarization_suspicion.extract_clip",
        lambda *a, **k: None,
    )
    doc = run_diarization_verify(ctx, verify_pair=yes_fn)
    assert not validate_diarization_repairs(doc)
    later = [w for w in ctx.read_json("transcript/full.json")["words"] if w["start_ms"] < 1_900_000]
    assert {w["speaker_id"] for w in later[3:6]} == {"spk_1"}
    host = [w for w in ctx.read_json("transcript/full.json")["words"] if w["text"] == "Host"]
    assert host and host[0]["speaker_id"] == "spk_0"
    assert doc["pairs"][0]["action"] == "relabel"
    flows = ctx.read_json("transcript/speaker_flows.json")
    assert any(f.get("speaker_id") == "spk_1" for f in (flows.get("flows") or []))


def test_verify_no_and_miss_keep_labels(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("relabel_no", create=True)
    t = 1000
    words = [
        _w("a", t, spk="spk_1"),
        _w("very", t + 200, spk="spk_1"),
        _w("novel", t + 400, spk="spk_1"),
        _w("1080", t + 400 + 180 + 1120, spk="spk_0"),
    ]
    ctx.write_json("transcript/full.json", {"words": list(words)})
    (ctx.run_dir / "ingest").mkdir(exist_ok=True)
    (ctx.run_dir / "ingest" / "normalized.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    monkeypatch.setattr("interview_mux.diarization_suspicion.extract_clip", lambda *a, **k: None)

    run_diarization_verify(ctx, verify_pair=lambda a, b: "NO")
    assert ctx.read_json("transcript/full.json")["words"][-1]["speaker_id"] == "spk_0"
    assert ctx.read_json("transcript/diarization_repairs.json")["pairs"][0]["action"] == "keep"

    ctx2 = RunContext("relabel_miss", create=True)
    ctx2.write_json("transcript/full.json", {"words": list(words)})
    (ctx2.run_dir / "ingest").mkdir(exist_ok=True)
    (ctx2.run_dir / "ingest" / "normalized.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    run_diarization_verify(ctx2, verify_pair=lambda a, b: None)
    assert ctx2.read_json("transcript/full.json")["words"][-1]["speaker_id"] == "spk_0"
    assert ctx2.read_json("transcript/diarization_repairs.json")["pairs"][0]["verdict"] == "skipped"


def test_sortformer_unavailable_logs_and_stamps_repairs(tmp_path: Path, monkeypatch) -> None:
    from interview_mux.local_runtime import LocalRuntimeUnavailable

    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("sortformer_missing", create=True)
    t = 1_785_000
    words = [
        _w("a", t, spk="spk_1"),
        _w("very", t + 200, spk="spk_1"),
        _w("novel", t + 400, spk="spk_1"),
        _w("1080", t + 400 + 180 + 1120, spk="spk_0"),
        _w("gene", t + 400 + 180 + 1120 + 200, spk="spk_0"),
        _w("panel", t + 400 + 180 + 1120 + 400, spk="spk_0"),
    ]
    ctx.write_json("transcript/full.json", {"words": words})
    (ctx.run_dir / "ingest").mkdir(exist_ok=True)
    (ctx.run_dir / "ingest" / "normalized.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    monkeypatch.setattr(
        "interview_mux.diarization_suspicion.extract_clip",
        lambda *a, **k: None,
    )

    def boom(_a, _b):
        raise LocalRuntimeUnavailable("speech runtime missing")

    doc = run_diarization_verify(ctx, verify_pair=boom)
    assert doc.get("verify_unavailable") is True
    assert "speech runtime missing" in str(doc.get("verify_unavailable_reason") or "")
    assert not validate_diarization_repairs(doc)


def test_um_in_monologue_is_absorbable() -> None:
    assert is_filled_pause_only_text("um")
    words = [
        *_fill("spk_1", 0, 20_000, stem="a"),
        _w("um", 20_100, spk="spk_0", dur=200),
        *_fill("spk_1", 20_400, 40_400, stem="b"),
    ]
    micros = absorbable_micro_runs(words)
    assert len(micros) == 1
    assert micros[0]["speaker_id"] == "spk_0"
    assert micros[0]["dominant_share"] >= 0.98


def test_verify_no_absorbs_nested_um(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("absorb_um", create=True)
    words = [
        *_fill("spk_1", 0, 20_000, stem="a"),
        _w("um", 20_100, spk="spk_0", dur=200),
        *_fill("spk_1", 20_400, 40_400, stem="b"),
    ]
    ctx.write_json("transcript/full.json", {"words": words})
    (ctx.run_dir / "ingest").mkdir(exist_ok=True)
    (ctx.run_dir / "ingest" / "normalized.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    monkeypatch.setattr("interview_mux.diarization_suspicion.extract_clip", lambda *a, **k: None)
    doc = run_diarization_verify(ctx, verify_pair=lambda a, b: "NO")
    assert not validate_diarization_repairs(doc)
    um = [w for w in ctx.read_json("transcript/full.json")["words"] if w["text"] == "um"]
    assert um and um[0]["speaker_id"] == "spk_0"
    assert any(p.get("action") == "absorb_micro" for p in doc["pairs"])
    windows = build_windows(words, pace_class="calm", cfg={"window_sec_calm": 60, "hop_sec": 0})
    assert len(windows) == 1
    assert "um" in windows[0]["text_span"]


def test_real_content_other_speaker_not_absorbed() -> None:
    words = [
        *_fill("spk_1", 0, 20_000, stem="a"),
        _w("this", 20_100, spk="spk_0", dur=800),
        _w("is", 21_000, spk="spk_0", dur=800),
        _w("real", 22_000, spk="spk_0", dur=800),
        _w("talk", 23_000, spk="spk_0", dur=800),
        *_fill("spk_1", 24_000, 44_000, stem="b"),
    ]
    assert absorbable_micro_runs(words) == []


def test_host_question_after_complete_close_not_absorbed() -> None:
    words = [
        *_fill("spk_1", 0, 8_000, stem="a"),
        _w("done.", 8_200, spk="spk_1"),
        _w("What", 9_000, spk="spk_0"),
        _w("happened", 9_250, spk="spk_0"),
        _w("after", 9_500, spk="spk_0"),
        _w("that?", 9_750, spk="spk_0"),
    ]
    assert absorbable_micro_runs(words) == []
    windows = build_windows(words, pace_class="calm", cfg={"window_sec_calm": 60, "hop_sec": 0})
    assert len(windows) >= 2
    assert any("What" in (w.get("text_span") or "") for w in windows)


def test_same_speaker_complete_thoughts_stay_split() -> None:
    words = [
        _w("That", 0, spk="spk_1"),
        _w("was", 200, spk="spk_1"),
        _w("it.", 400, spk="spk_1"),
        _w("Next", 1600, spk="spk_1"),
        _w("chapter", 1800, spk="spk_1"),
        _w("starts.", 2000, spk="spk_1"),
    ]
    assert absorbable_micro_runs(words) == []
    windows = build_windows(words, pace_class="dense", cfg={"window_sec_dense": 20, "hop_sec": 0})
    assert len(windows) >= 2


def test_yes_fuse_and_remap(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("fuse_yes", create=True)
    t = 1_785_000
    words = [
        _w("a", t, spk="spk_1"),
        _w("very", t + 200, spk="spk_1"),
        _w("novel", t + 400, spk="spk_1"),
        _w("1080", t + 400 + 180 + 1120, spk="spk_1"),
    ]
    ctx.write_json("transcript/full.json", {"words": words}, skip_handoff=True)
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                _seg_row("seg_016", t, t + 580, "a very novel"),
                _seg_row("seg_017", t + 400 + 180 + 1120, t + 400 + 180 + 1120 + 180, "1080"),
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "transcript/diarization_repairs.json",
        {
            "version": 1,
            "applied": True,
            "candidate_count": 1,
            "pairs": [
                {
                    "from_speaker_id": "spk_1",
                    "to_speaker_id": "spk_0",
                    "verdict": "yes_same",
                    "action": "relabel",
                    "hanging_setup": True,
                    "seam_end_ms": t + 580,
                    "next_start_ms": t + 400 + 180 + 1120,
                    "start_ms": t + 580,
                    "end_ms": t + 400 + 180 + 1120,
                }
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [{"line_id": "vo_seg_017", "targets_segment_id": "seg_017", "gap_type": "clarification", "text": "x", "placement": "before", "delivery": "synthesize"}]},
        skip_handoff=True,
    )
    verdicts = forced_diarization_fuse_verdicts(ctx)
    assert verdicts and verdicts[0]["forced_by"] == "diarization_yes_same"
    result = apply_connector_fuses(ctx, verdicts, pass_id="diar_test")
    assert result["applied"] == 1
    segs = ctx.read_json("segments/manifest.json")["segments"]
    ids = {s["segment_id"] for s in segs}
    assert "seg_016" in ids
    assert "seg_017" not in ids
    gap = ctx.read_json("understanding/gap_report.json")
    assert gap["interviewer_lines"][0]["targets_segment_id"] == "seg_016"


def test_micro_keeper_fuse(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("fuse_micro", create=True)
    ctx.write_json("transcript/full.json", {"words": []}, skip_handoff=True)
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                _seg_row("seg_a", 0, 20_000, "guest"),
                _seg_row("seg_um", 20_100, 20_300, "um", spk="spk_0"),
                _seg_row("seg_b", 20_400, 40_400, "more"),
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "transcript/diarization_repairs.json",
        {
            "version": 1,
            "applied": True,
            "candidate_count": 1,
            "pairs": [
                {
                    "from_speaker_id": "spk_1",
                    "to_speaker_id": "spk_0",
                    "verdict": "no_different",
                    "action": "absorb_micro",
                    "seam_end_ms": 20_000,
                    "next_start_ms": 20_100,
                    "start_ms": 20_000,
                    "end_ms": 20_100,
                    "island_start_ms": 20_100,
                    "island_end_ms": 20_300,
                }
            ],
        },
        skip_handoff=True,
    )
    verdicts = forced_diarization_fuse_verdicts(ctx)
    result = apply_connector_fuses(ctx, verdicts, pass_id="micro_test")
    assert result["applied"] >= 1
    ids = {s["segment_id"] for s in ctx.read_json("segments/manifest.json")["segments"]}
    assert "seg_um" not in ids
    assert len(ids) == 1


def test_remap_rewrites_gap_report(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("remap_gap", create=True)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [{"line_id": "x", "targets_segment_id": "seg_017", "gap_type": "clarification", "text": "x", "placement": "before", "delivery": "synthesize"}]},
        skip_handoff=True,
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_016", "seg_017"]},
        skip_handoff=True,
    )
    updated = apply_full_segment_id_remap(
        ctx, {"seg_017": "seg_016"}, skip_handoff=True, rebind_vo=False
    )
    assert "understanding/gap_report.json" in updated
    assert ctx.read_json("understanding/gap_report.json")["interviewer_lines"][0]["targets_segment_id"] == "seg_016"
    assert ctx.read_json("master/selection.json")["ordered_segment_ids"] == ["seg_016"]


def test_sortformer_pair_smoke_optional() -> None:
    """GPU smoke: skip when the production speech venv cannot import mlx_audio.vad."""
    import json
    import subprocess
    import sys
    from pathlib import Path as P

    import pytest

    speech_py = P("ASSETS/local_speech/venv/bin/python")
    py = speech_py if speech_py.is_file() else P(sys.executable)
    proc = subprocess.run(
        [str(py), "-c", "from mlx_audio.vad import load; print('ok')"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.skip(proc.stderr[-200:] if proc.stderr else "mlx_audio.vad unavailable")
    probe = P("tools/s2s_interrogate.py")
    if not probe.is_file():
        pytest.skip("s2s_interrogate missing")
    verify = subprocess.run(
        [str(py), str(probe), "--verify"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert verify.returncode == 0
    payload = json.loads(verify.stdout.strip().splitlines()[-1])
    assert payload.get("ok") is True
    assert payload.get("vad_ok") is True
