from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.ingest.runner import ingest_audio
from pipeline.orchestrator.preset_a import run_preset_a
from pipeline.transcription.runner import run_stt


@pytest.mark.slow
def test_pipeline_smoke_end_to_end(
    repo_root: Path,
    tmp_assets: Path,
    speech_wav: Path,
    tmp_path: Path,
) -> None:
    """Ingest → STT (tiny) → preset A (--no-llm, --skip-stt) without OpenAI."""
    from mux_store import connect, init_db

    session_id = "run_999"
    db_path = tmp_path / "test.sqlite"
    conn = connect(str(db_path))
    init_db(conn)

    ingest_audio(
        input_path=speech_wav,
        session_id=session_id,
        repo_root=repo_root,
        conn=conn,
        skip_loudnorm=True,
    )
    normalized = tmp_assets / session_id / "ingest" / "normalized.wav"
    assert normalized.is_file()

    run_stt(
        normalized,
        session_id=session_id,
        provider="faster-whisper",
        conn=conn,
        repo_root=repo_root,
        model_size="tiny",
    )

    out = run_preset_a(
        session_id=session_id,
        normalized_wav=normalized,
        conn=conn,
        repo_root=repo_root,
        top_n=2,
        use_llm_rank=False,
        skip_stt=True,
        skip_master_lufs=False,
    )

    polished = Path(out["polished_master_path"])
    assert polished.is_file()
    assert polished.stat().st_size > 1000

    row = conn.execute(
        "SELECT status FROM execution_run WHERE id = ?",
        (out["run_id"],),
    ).fetchone()
    assert row and row[0] == "completed"
    conn.close()
