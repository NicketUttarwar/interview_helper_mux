from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.common import assets_root
from pipeline.dsp.room_polish import apply_room_polish
from pipeline.mux.assembler import assemble_highlight_reel, write_edl
from pipeline.mux.mastering import master_lufs
from pipeline.scoring.rank import rank_segments_for_session
from pipeline.segmentation.segmenter import persist_segments, segment_transcript
from pipeline.snippet_store.manifest import build_snippet_manifest, write_snippet_manifest
from pipeline.transcription.load import load_latest_transcript
from pipeline.transcription.runner import run_stt


def run_preset_a(
    *,
    session_id: str,
    normalized_wav: Path,
    conn: Any,
    repo_root: Path,
    top_n: int = 8,
    stt_provider: str = "faster-whisper",
    use_llm_rank: bool = True,
    crossfade_ms: int = 300,
    skip_stt: bool = False,
    stt_model_size: str = "base",
    skip_master_lufs: bool = False,
    skip_dsp: bool = False,
) -> dict[str, Any]:
    """Preset A: STT → segment → rank top-N → crossfade mux → LUFS → mandatory DSP polish."""
    from mux_store import create_run, register_asset, touch_run

    run_id = create_run(
        conn,
        status="running",
        orchestration_slug="preset_a_highlight",
        config={
            "session_id": session_id,
            "top_n": top_n,
            "stt_provider": stt_provider,
            "skip_stt": skip_stt,
            "skip_master_lufs": skip_master_lufs,
            "skip_dsp": skip_dsp,
        },
    )

    if skip_stt:
        doc = load_latest_transcript(session_id, repo_root=repo_root)
    else:
        doc = run_stt(
            normalized_wav,
            session_id=session_id,
            provider=stt_provider,
            conn=conn,
            repo_root=repo_root,
            model_size=stt_model_size,
        )

    segs = segment_transcript(doc)
    persist_segments(conn, session_id, segs)
    ordered = rank_segments_for_session(conn, session_id, use_llm=use_llm_rank, top_n=top_n)
    manifest = build_snippet_manifest(session_id, segs, ordered_ids=ordered, transcript_revision_id=doc.revision_id)
    manifest_path = write_snippet_manifest(manifest)

    reel = assemble_highlight_reel(
        normalized_wav,
        segs,
        ordered,
        session_id=session_id,
        crossfade_ms=crossfade_ms,
    )
    master_path = assets_root(repo_root) / session_id / "master" / "highlight_master.wav"
    master_lufs(reel, master_path, apply_lufs=not skip_master_lufs)

    register_asset(
        conn,
        storage_uri=str(master_path),
        kind="audio_master",
        run_id=run_id,
        interview_id=session_id,
        mime_type="audio/wav",
        meta={"preset": "A", "top_n": top_n},
    )

    polished_path = assets_root(repo_root) / session_id / "processed" / "room_polish_master.wav"
    if skip_dsp:
        final_path = master_path
    else:
        apply_room_polish(master_path, polished_path, conn=conn)
        register_asset(
            conn,
            storage_uri=str(polished_path),
            kind="audio_master_polished",
            run_id=run_id,
            interview_id=session_id,
            mime_type="audio/wav",
            meta={"preset": "A", "dsp": "room_polish"},
        )
        final_path = polished_path

    write_edl(conn, run_id, session_id, ordered, segs)
    touch_run(conn, run_id, status="completed")

    return {
        "run_id": run_id,
        "session_id": session_id,
        "transcript_revision_id": doc.revision_id,
        "ordered_segment_ids": ordered,
        "manifest_path": str(manifest_path),
        "highlight_reel": str(reel),
        "master_path": str(master_path),
        "polished_master_path": str(final_path),
        "skip_stt": skip_stt,
        "skip_dsp": skip_dsp,
    }
