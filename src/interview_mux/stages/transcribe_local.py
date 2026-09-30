"""Local STT + diarization (replaces AWS Transcribe).

Backend is chosen by tools/stt_transcribe.py: mlx-audio on Apple Silicon,
faster-whisper (CTranslate2, CUDA or CPU) elsewhere. Both satisfy the same
words contract, so this stage does not care which one ran.
"""

from __future__ import annotations

from interview_mux.operator_trace import logged_step
from interview_mux.operator_subprocess import touch_job_message
from interview_mux.run_context import RunContext
from interview_mux.local_runtime import LocalRuntimeUnavailable
from interview_mux.stt_runner import speech_available, transcribe_audio
from interview_mux.transcript_normalize import normalize_local_stt


def run_transcribe(ctx: RunContext) -> None:
    # Gate on the runtime actually being installed, not on the hardware. This
    # used to refuse anything but Apple Silicon, which blocked the stage on a
    # host where the faster-whisper backend was present and working.
    # speech_available() resolves the configured local_speech venv, and
    # tools/stt_transcribe.py picks mlx-audio or faster-whisper inside it.
    if not speech_available():
        raise RuntimeError(
            "Local speech runtime missing. Run ./scripts/bootstrap_venv.sh on "
            "Apple Silicon, or ./scripts/bootstrap_venv_windows.sh on a "
            "Windows/Linux CUDA host."
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

    # Same normalized audio, same model, same diarization mode: same words.
    # A rerun of a source file already transcribed on this machine restores the
    # transcript from the stage cache instead of running STT again (ISSUES 93).
    from interview_mux import stage_cache
    from interview_mux.stt_runner import local_speech_cfg, resolve_diarization_mode, resolve_stt_model_id

    cache_rels = ["transcript/full.json", "transcript/speakers.json"]
    key = stage_cache.cache_key(
        "transcribe",
        stage_cache.file_digest(normalized),
        resolve_stt_model_id(),
        resolve_diarization_mode(),
        stage_cache.config_digest(local_speech_cfg()),
    )
    try:
        if stage_cache.restore(ctx, "transcribe", key, cache_rels):
            full = ctx.read_json("transcript/full.json")
            speakers = ctx.read_json("transcript/speakers.json")
        else:
            with logged_step("transcribe/local_stt", ctx=ctx, stage="transcribe"):
                raw = transcribe_audio(ctx, normalized)
            with logged_step("transcribe/normalize_transcript", ctx=ctx, stage="transcribe"):
                full, speakers = normalize_local_stt(raw)
                ctx.write_json("transcript/full.json", full)
                ctx.write_json("transcript/speakers.json", speakers)
            stage_cache.store(
                ctx,
                "transcribe",
                key,
                {"transcript/full.json": full, "transcript/speakers.json": speakers},
            )
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
        try:
            meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
            recipe = (meta or {}).get("source_profile_recipe") or {}
            retries = int(recipe.get("diarization_retry") or 1)
            ctx.log(
                f"source_profile recipe diarization_retry={retries}",
                level="info",
                stage="transcribe",
                detail={"recipe": recipe},
            )
        except Exception:
            pass
        if is_homunculus_meta(ctx):
            build_source_card(ctx)
    except Exception:
        pass
