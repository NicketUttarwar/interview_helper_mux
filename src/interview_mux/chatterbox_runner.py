"""Chatterbox zero-shot voice clone synthesis for gap framing VO."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.gap_framing import gap_vo_cfg
from interview_mux.gap_vo_gates import resolve_gap_vo_delivery
from interview_mux.local_runtime import LocalRuntimeUnavailable, run_runtime_json
from interview_mux.run_context import RunContext
from interview_mux.voice_reference import voice_reference_cfg


def chatterbox_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    block = (cfg or merged_config()).get("local_chatterbox") or {}
    defaults = {
        "enabled": True,
        "model_id": "ResembleAI/chatterbox",
        "timeout_sec": 600,
        "fail_open": bool(gap_vo_cfg().get("fail_open", False)),
    }
    if isinstance(block, dict):
        merged = {**defaults, **block}
        if "fail_open" not in block:
            merged["fail_open"] = defaults["fail_open"]
        return merged
    return defaults


def chatterbox_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(chatterbox_cfg(cfg).get("enabled", True))


def should_use_chatterbox(ctx: RunContext) -> bool:
    vo = gap_vo_cfg()
    backend = str(vo.get("synthesis_backend", "chatterbox")).lower()
    if backend != "chatterbox":
        return False
    if resolve_gap_vo_delivery(ctx) != "chatterbox":
        return False
    return chatterbox_enabled()


def resolve_reference_audio(ctx: RunContext, line: dict[str, Any]) -> Path:
    from interview_mux.s2s_runner import resolve_reference_audio as mlx_ref

    return mlx_ref(ctx, line)


def _iter_voice_ref_candidates(ctx: RunContext, line: dict[str, Any]) -> list[tuple[str, Path]]:
    """Ordered voice-ref paths: approved sample, then alternate candidate clips."""
    from interview_mux.source_topology import pickup_eligible_speaker_id

    speaker_id = str(line.get("voice_speaker_id") or pickup_eligible_speaker_id(ctx) or "").strip()
    ordered: list[tuple[str, Path]] = []
    seen: set[str] = set()

    def _add(ref_id: str, path: Path) -> None:
        key = str(path.resolve()) if path.is_file() else ""
        if not key or key in seen:
            return
        seen.add(key)
        ordered.append((ref_id, path))

    try:
        primary = resolve_reference_audio(ctx, line)
        _add("speaker_sample", primary)
    except FileNotFoundError:
        pass

    max_n = int(voice_reference_cfg().get("max_reference_candidates", 5))
    if speaker_id:
        cand_rel = f"understanding/voice_reference/{speaker_id}_candidates.json"
        if ctx.artifact_exists(cand_rel):
            doc = ctx.read_json(cand_rel)
            for i, seg in enumerate((doc.get("segments") or []) if isinstance(doc, dict) else []):
                if not isinstance(seg, dict):
                    continue
                clip_rel = str(seg.get("clip_path") or "").strip()
                if not clip_rel:
                    continue
                path = ctx.read_path(*clip_rel.split("/"))
                _add(f"candidate_{i:02d}", path)
                if len(ordered) >= max_n:
                    break
        # Also try discrete clip files even if candidates json lacks clip_path.
        clips_dir = ctx.path("understanding", "voice_reference", "clips", speaker_id)
        if clips_dir.is_dir():
            for path in sorted(clips_dir.glob("candidate_*.wav")):
                _add(path.stem, path)
                if len(ordered) >= max_n:
                    break
    return ordered[:max_n] if ordered else ordered


def _synthesize_once(
    ctx: RunContext,
    line: dict[str, Any],
    *,
    ref: Path,
    out_wav: Path,
    voice_ref_id: str,
    attempt: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model_id": chatterbox_cfg().get("model_id"),
        "text": str(line.get("text") or ""),
        "ref_audio": str(ref),
        "out_wav": str(out_wav),
    }
    speaker_id = line.get("voice_speaker_id")
    if speaker_id and ctx.artifact_exists(f"understanding/speaker_samples/{speaker_id}.json"):
        ref_doc = ctx.read_json(f"understanding/speaker_samples/{speaker_id}.json")
        if isinstance(ref_doc, dict) and ref_doc.get("ref_text"):
            payload["ref_text"] = ref_doc["ref_text"]

    timeout = int(chatterbox_cfg().get("timeout_sec", 600))
    result = run_runtime_json(
        "chatterbox",
        "tools/chatterbox_generate.py",
        payload,
        timeout_sec=timeout,
        ctx=ctx,
        stage="vo_synthesize",
    )
    if not result.get("ok"):
        raise LocalRuntimeUnavailable(str(result.get("error") or "Chatterbox failed"))
    if not out_wav.is_file():
        raise LocalRuntimeUnavailable(f"Chatterbox missing output: {out_wav}")
    # Normalize float32 Chatterbox output before speech QA / promote.
    from interview_mux.s2s_runner import _ensure_pcm_s16le_wav

    normalized = _ensure_pcm_s16le_wav(out_wav, out_wav)
    if normalized is None or not out_wav.is_file():
        raise LocalRuntimeUnavailable(f"Chatterbox output normalize failed: {out_wav}")
    from interview_mux.vo_synthesis_audit import record_synthesis

    return record_synthesis(
        ctx,
        line,
        backend="chatterbox",
        out_wav=out_wav,
        ref_audio=str(ref),
        model_id=str(chatterbox_cfg().get("model_id") or ""),
        voice_ref_id=voice_ref_id,
        attempt=attempt,
    )


def synthesize_line(
    ctx: RunContext,
    line: dict[str, Any],
    *,
    dest_dir: Path | None = None,
) -> Path:
    if not chatterbox_enabled():
        raise LocalRuntimeUnavailable("local_chatterbox disabled in config")

    line_id = str(line.get("line_id") or line.get("targets_segment_id") or "line")
    pickup = dest_dir or ctx.path("vo_pickup")
    out_dir = pickup / "synthesized"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_wav = out_dir / f"{line_id}.wav"

    candidates = _iter_voice_ref_candidates(ctx, line)
    if not candidates:
        raise FileNotFoundError("No pickup-eligible voice reference for Chatterbox")

    last_entry: dict[str, Any] | None = None
    last_exc: Exception | None = None
    for attempt, (ref_id, ref) in enumerate(candidates, start=1):
        try:
            entry = _synthesize_once(
                ctx,
                line,
                ref=ref,
                out_wav=out_wav,
                voice_ref_id=ref_id,
                attempt=attempt,
            )
            last_entry = entry
            if entry.get("qc_pass") is False:
                ctx.log(
                    f"Chatterbox QC fail for {line_id} ref={ref_id} "
                    f"({entry.get('qc_notes')}); trying next voice-ref",
                    level="warning",
                    stage="vo_synthesize",
                )
                continue
            from interview_mux.s2s_runner import promote_synthesized_vo

            promote_synthesized_vo(ctx, line_id=line_id, src=out_wav)
            return out_wav
        except Exception as exc:
            last_exc = exc
            ctx.log(
                f"Chatterbox attempt {attempt} ref={ref_id} failed: {exc}",
                level="warning",
                stage="vo_synthesize",
            )
            continue

    # All refs exhausted — hard-stop (or let s2s fail-open to mlx when configured).
    if last_entry and last_entry.get("qc_pass") is False:
        notes = last_entry.get("qc_notes") or "speech_qa_failed"
        raise LocalRuntimeUnavailable(
            f"Chatterbox QC failed all voice-ref candidates for {line_id}: {notes}"
        )
    if last_exc:
        raise LocalRuntimeUnavailable(str(last_exc)) from last_exc
    raise LocalRuntimeUnavailable(f"Chatterbox failed all voice-ref candidates for {line_id}")
