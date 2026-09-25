"""interview_spine_build S1–S4: repairs-only diarization; no unpaid transcript land."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_ownership import write_permitted
from interview_mux.diarization_suspicion import REPAIRS_REL, run_diarization_verify
from interview_mux.prompt_validation import validate_diarization_repairs
from interview_mux.run_context import RunContext
from interview_mux.stage_contract import load_contract
from run_fixtures import patch_executions_root


def _w(text: str, start: int, *, spk: str, dur: int = 180) -> dict:
    return {"text": text, "start_ms": start, "end_ms": start + dur, "speaker_id": spk}


def test_s1_s2_yes_does_not_write_transcript_under_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("isb_s1_repairs", create=True)
    t = 1_785_000
    words = [
        _w("a", t, spk="spk_1"),
        _w("very", t + 200, spk="spk_1"),
        _w("novel", t + 400, spk="spk_1"),
        _w("1080", t + 400 + 180 + 1120, spk="spk_0"),
        _w("gene", t + 400 + 180 + 1120 + 200, spk="spk_0"),
    ]
    ctx.write_json("transcript/full.json", {"words": words})
    ctx.write_json(
        "transcript/speakers.json",
        {"speakers": [{"id": "spk_0", "role": "unknown", "word_count": 1}]},
        skip_handoff=True,
    )
    (ctx.run_dir / "ingest").mkdir(exist_ok=True)
    (ctx.run_dir / "ingest" / "normalized.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    monkeypatch.setattr(
        "interview_mux.diarization_suspicion.extract_clip",
        lambda *a, **k: None,
    )

    ok_tx, reason_tx = write_permitted(ctx, "transcript/full.json", "interview_spine_build")
    assert ok_tx is False, reason_tx
    ok_rep, reason_rep = write_permitted(ctx, REPAIRS_REL, "interview_spine_build")
    assert ok_rep is True, reason_rep

    before_spk = [w["speaker_id"] for w in ctx.read_json("transcript/full.json")["words"]]
    doc = run_diarization_verify(ctx, stage="interview_spine_build", verify_pair=lambda a, b: "YES")
    assert not validate_diarization_repairs(doc)
    assert doc["pairs"][0]["action"] == "relabel"
    assert [w["speaker_id"] for w in ctx.read_json("transcript/full.json")["words"]] == before_spk
    speakers = ctx.read_json("transcript/speakers.json")
    assert speakers["speakers"][0]["id"] == "spk_0"
    assert ctx.artifact_exists(REPAIRS_REL)


def test_s3_verify_stays_hosted_in_spine_stage() -> None:
    """Safest S3: no dedicated stage split — verify remains a host step in ISB."""
    from interview_mux.stages import interview_spine_stage as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "run_diarization_verify" in src
    assert "repairs-only" in src


def test_s4_contract_lists_repairs_and_read_only_transcript() -> None:
    contract = load_contract("interview_spine_build")
    assert contract is not None
    outs = {out.path for out in contract.outputs}
    assert "understanding/interview_spine.json" in outs
    assert "transcript/diarization_repairs.json" in outs
    hard = {inp.path for inp in contract.inputs if inp.hard}
    assert "transcript/full.json" in hard
    trans = next(inp for inp in contract.inputs if inp.path == "transcript/full.json")
    assert trans.producer == "transcribe"
