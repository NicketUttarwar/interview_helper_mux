"""Segment-adjacent context clips + speaker ref metadata for S2S."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.gap_framing import gap_vo_cfg
from interview_mux.local_model_selection import load_speech_selection
from interview_mux.local_runtime import LocalRuntimeUnavailable, run_runtime_json
from interview_mux.run_context import RunContext


def local_speech_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    return (cfg or merged_config()).get("local_speech") or {}


def s2s_enabled(cfg: dict[str, Any] | None = None) -> bool:
    block = local_speech_cfg(cfg)
    return bool(block.get("enabled", True))


def resolve_s2s_model_id(cfg: dict[str, Any] | None = None) -> str:
    block = local_speech_cfg(cfg)
    override = str(block.get("s2s_model_id") or "").strip()
    if override:
        return override
    sel = load_speech_selection() or {}
    return str(sel.get("s2s_model_id") or "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit")


def write_speaker_ref_sidecar(ctx: RunContext, speaker_id: str, *, ref_text: str) -> str:
    """Persist ref_text sidecar next to speaker sample WAV."""
    rel = f"understanding/speaker_samples/{speaker_id}.json"
    payload = {
        "speaker_id": speaker_id,
        "ref_text": ref_text.strip(),
        "wav": f"understanding/speaker_samples/{speaker_id}.wav",
    }
    ctx.write_json(rel, payload)
    return rel


def load_speaker_ref(ctx: RunContext, speaker_id: str) -> dict[str, Any] | None:
    rel = f"understanding/speaker_samples/{speaker_id}.json"
    if not ctx.artifact_exists(rel):
        return None
    data = ctx.read_json(rel)
    return data if isinstance(data, dict) else None


def resolve_reference_audio(ctx: RunContext, line: dict[str, Any]) -> Path:
    from interview_mux.source_topology import ensure_speaker_sample_clips, pickup_eligible_speaker_id

    speaker_id = str(line.get("voice_speaker_id") or pickup_eligible_speaker_id(ctx) or "").strip()
    if not speaker_id:
        raise FileNotFoundError("No pickup-eligible speaker for S2S reference")
    clips = ensure_speaker_sample_clips(ctx)
    rel = clips.get(speaker_id) or f"understanding/speaker_samples/{speaker_id}.wav"
    path = ctx.read_path(*rel.split("/"))
    if not path.is_file():
        raise FileNotFoundError(f"Missing speaker reference: {rel}")
    return path


def context_clip_for_line(ctx: RunContext, line: dict[str, Any]) -> Path | None:
    """Extract 2–8 s adjacent speech clip for prosody conditioning."""
    block = local_speech_cfg()
    if not block.get("context_clip_enabled", True):
        return None
    seg_id = str(line.get("targets_segment_id") or "")
    if not seg_id or not ctx.artifact_exists("segments/segments.json"):
        return None
    segments = ctx.read_json("segments/segments.json")
    seg = next(
        (s for s in (segments.get("segments") or []) if str(s.get("segment_id")) == seg_id),
        None,
    )
    if not isinstance(seg, dict):
        return None
    placement = str(line.get("placement") or "before").lower()
    if placement == "after":
        anchor_ms = int(seg.get("end_ms") or 0)
    else:
        anchor_ms = int(seg.get("start_ms") or 0)
    min_ms = int(block.get("context_clip_min_ms", 2000))
    max_ms = int(block.get("context_clip_max_ms", 8000))
    start_ms = max(0, anchor_ms - max_ms // 2)
    end_ms = start_ms + max_ms
    if end_ms - start_ms < min_ms:
        return None
    audio = ctx.read_path("ingest", "normalized.wav")
    if not audio.is_file():
        return None
    out = ctx.path("vo_pickup", "_s2s_context", f"{line.get('line_id', seg_id)}.wav")
    out.parent.mkdir(parents=True, exist_ok=True)
    from interview_mux.source_topology import extract_clip

    extract_clip(audio, out, start_ms, end_ms)
    return out if out.is_file() else None


def synthesize_line(
    ctx: RunContext,
    line: dict[str, Any],
    *,
    mode: str = "synthesize",
    tone: str | None = None,
    source_audio: Path | None = None,
    dest_dir: Path | None = None,
) -> Path:
    """Generate VO WAV via Chatterbox (gap default) or mlx-audio S2S subprocess."""
    if mode == "convert":
        # Never TTS into matched/ — DSP preserves the operator take.
        from interview_mux.timbre_match import match_vo_take

        if source_audio is None or not Path(source_audio).is_file():
            raise FileNotFoundError("source_audio required for DSP timbre match (convert)")
        return match_vo_take(ctx, line, Path(source_audio))

    chatterbox_fallback = False
    if mode == "synthesize":
        from interview_mux.chatterbox_runner import should_use_chatterbox

        if should_use_chatterbox(ctx):
            from interview_mux import chatterbox_runner

            try:
                out = chatterbox_runner.synthesize_line(ctx, line, dest_dir=dest_dir)
                from interview_mux.vo_synthesis_audit import qc_failed

                entries = ctx.read_json("vo_pickup/synthesis_report.json") if ctx.artifact_exists("vo_pickup/synthesis_report.json") else {}
                last = (entries.get("entries") or [])[-1] if isinstance(entries, dict) and entries.get("entries") else {}
                if isinstance(last, dict) and qc_failed(last):
                    ctx.log(
                        f"Chatterbox QC fail → mlx-audio retry for {line.get('line_id')}",
                        level="warning",
                        stage="vo_synthesize",
                    )
                    chatterbox_fallback = True
                else:
                    return out
            except Exception as exc:
                block = gap_vo_cfg()
                if block.get("fail_open", False) and str(block.get("fallback_backend", "mlx_audio")) == "mlx_audio":
                    ctx.log(
                        f"Chatterbox fail-open → mlx-audio: {exc}",
                        level="warning",
                        stage="vo_synthesize",
                    )
                    chatterbox_fallback = True
                elif mode == "synthesize":
                    from interview_mux.synthesis_fallback import maybe_fallback_after_synthesis_failure

                    maybe_fallback_after_synthesis_failure(ctx, line, exc, stage="vo_synthesize")
                else:
                    raise

    if not s2s_enabled():
        if mode == "synthesize":
            from interview_mux.synthesis_fallback import maybe_fallback_after_synthesis_failure

            maybe_fallback_after_synthesis_failure(
                ctx,
                line,
                LocalRuntimeUnavailable("local_speech S2S disabled in config"),
                stage="vo_synthesize",
            )
        raise LocalRuntimeUnavailable("local_speech S2S disabled in config")

    line_id = str(line.get("line_id") or line.get("targets_segment_id") or "line")
    ref = resolve_reference_audio(ctx, line)
    context = context_clip_for_line(ctx, line)
    pickup = dest_dir or ctx.path("vo_pickup")
    subdir = {
        "synthesize": "synthesized",
        "convert": "matched",
        "tone": "synthesized",
    }.get(mode, "synthesized")
    out_dir = pickup / subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_wav = out_dir / f"{line_id}.wav"

    payload: dict[str, Any] = {
        "mode": mode,
        "model_id": resolve_s2s_model_id(),
        "text": str(line.get("text") or ""),
        "ref_audio": str(ref),
        "out_wav": str(out_wav),
        "tone": tone or line.get("suggested_tone"),
    }
    if context and context.is_file():
        payload["context_audio"] = str(context)
    if source_audio and source_audio.is_file():
        payload["source_audio"] = str(source_audio)

    block = local_speech_cfg()
    timeout = int(block.get("s2s_timeout_sec", 600))
    result = run_runtime_json(
        "speech",
        "tools/s2s_generate.py",
        payload,
        timeout_sec=timeout,
        ctx=ctx,
        stage="vo_synthesize",
    )
    if not result.get("ok"):
        err = LocalRuntimeUnavailable(str(result.get("error") or "S2S failed"))
        if mode == "synthesize":
            from interview_mux.synthesis_fallback import maybe_fallback_after_synthesis_failure

            maybe_fallback_after_synthesis_failure(ctx, line, err, stage="vo_synthesize")
        raise err
    if not out_wav.is_file():
        err = LocalRuntimeUnavailable(f"S2S missing output: {out_wav}")
        if mode == "synthesize":
            from interview_mux.synthesis_fallback import maybe_fallback_after_synthesis_failure

            maybe_fallback_after_synthesis_failure(ctx, line, err, stage="vo_synthesize")
        raise err
    _append_qa_sidecar(ctx, line_id, mode=mode, out_wav=out_wav, payload=payload)
    if mode == "synthesize":
        from interview_mux.vo_synthesis_audit import record_synthesis

        record_synthesis(
            ctx,
            line,
            backend="mlx_audio",
            out_wav=out_wav,
            ref_audio=str(ref),
            fallback_from="chatterbox" if chatterbox_fallback else None,
            fallback_reason="chatterbox_fail_open_or_qc" if chatterbox_fallback else None,
            model_id=str(payload.get("model_id") or ""),
        )
        promote_synthesized_vo(ctx, line_id=line_id, src=out_wav)
    return out_wav


def promote_synthesized_vo(ctx: RunContext, *, line_id: str, src: Path) -> Path | None:
    """Copy synthesized WAV to vo_pickup/{line_id}.wav for G1/EDL resolution."""
    if not src.is_file() or not line_id:
        return None
    dest = ctx.path("vo_pickup") / f"{line_id}.wav"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.resolve() != src.resolve():
            dest.write_bytes(src.read_bytes())
        return dest
    except OSError:
        return None


def _append_qa_sidecar(
    ctx: RunContext,
    line_id: str,
    *,
    mode: str,
    out_wav: Path,
    payload: dict[str, Any],
) -> None:
    rel = "vo_pickup/s2s_qa.json"
    rows: list[dict[str, Any]] = []
    if ctx.artifact_exists(rel):
        existing = ctx.read_json(rel)
        if isinstance(existing, list):
            rows = list(existing)
        elif isinstance(existing, dict):
            rows = list(existing.get("entries") or [])
    rows.append(
        {
            "line_id": line_id,
            "mode": mode,
            "path": out_wav.relative_to(ctx.run_dir).as_posix()
            if out_wav.is_relative_to(ctx.run_dir)
            else str(out_wav),
            "model_id": payload.get("model_id"),
            "tone": payload.get("tone"),
            "ref_audio": payload.get("ref_audio"),
            "context_audio": payload.get("context_audio"),
        }
    )
    ctx.write_json(rel, {"entries": rows})
