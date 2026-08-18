"""Local MLX STT + diarization (replaces AWS Transcribe on Apple Silicon)."""

from __future__ import annotations

from interview_mux.hardware_detect import is_apple_silicon
from interview_mux.operator_trace import logged_step
from interview_mux.operator_subprocess import touch_job_message
from interview_mux.run_context import RunContext
from interview_mux.local_runtime import LocalRuntimeUnavailable
from interview_mux.stt_runner import speech_available, transcribe_audio
from interview_mux.transcript_normalize import normalize_local_stt


def run_transcribe(ctx: RunContext) -> None:
    if not is_apple_silicon():
        raise RuntimeError(
            "Local MLX transcription requires Apple Silicon. "
            "Run on arm64 macOS after ./scripts/bootstrap_venv.sh"
        )
    if not speech_available():
        raise RuntimeError(
            "Local speech venv missing. Re-run ./scripts/bootstrap_venv.sh "
            "(step 4/5 local_speech)."
        )

    ctx.artifact_exists_required(
        "ingest/normalized.wav",
        stage="transcribe",
        label="Normalized audio from ingest",
    )
    normalized = ctx.read_path("ingest", "normalized.wav")

    ctx.log(
        "Transcribe: local MLX STT + diarization",
        level="action",
        stage="transcribe",
        detail={"journey_kind": "execute", "provider": "local_speech"},
    )
    touch_job_message(ctx, "Transcribe: running local MLX STT…")

    try:
        with logged_step("transcribe/local_stt", ctx=ctx, stage="transcribe"):
            raw = transcribe_audio(ctx, normalized)
        with logged_step("transcribe/normalize_transcript", ctx=ctx, stage="transcribe"):
            full, speakers = normalize_local_stt(raw)
            ctx.write_json("transcript/full.json", full)
            ctx.write_json("transcript/speakers.json", speakers)
    except LocalRuntimeUnavailable as exc:
        ctx.log(f"Local STT failed: {exc}", level="error", stage="transcribe")
        raise RuntimeError(str(exc)) from exc

    ctx.log(
        f"Transcription complete — {len(full.get('words') or [])} words, "
        f"{len(speakers.get('speakers') or [])} speaker(s).",
        level="success",
        stage="transcribe",
    )
    ctx.mark_done("transcribe")
    try:
        from interview_mux.homunculus.issues import is_homunculus_meta
        from interview_mux.homunculus.source_card import build_source_card, refresh_source_profile

        n_speakers = len((speakers.get("speakers") if isinstance(speakers, dict) else None) or [])
        refresh_source_profile(ctx, stage="transcribe", speaker_count=n_speakers or None)
        if is_homunculus_meta(ctx):
            build_source_card(ctx)
    except Exception:
        pass
