"""Chatterbox zero-shot voice clone synthesis for gap framing VO."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.gap_framing import gap_vo_cfg
from interview_mux.gap_vo_gates import resolve_gap_vo_delivery
from interview_mux.local_runtime import LocalRuntimeUnavailable, run_runtime_json
from interview_mux.run_context import RunContext


def chatterbox_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    block = (cfg or merged_config()).get("local_chatterbox") or {}
    defaults = {
        "enabled": True,
        "model_id": "ResembleAI/chatterbox",
        "timeout_sec": 600,
        "fail_open": False,
    }
    if isinstance(block, dict):
        return {**defaults, **block}
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


def synthesize_line(
    ctx: RunContext,
    line: dict[str, Any],
    *,
    dest_dir: Path | None = None,
) -> Path:
    if not chatterbox_enabled():
        raise LocalRuntimeUnavailable("local_chatterbox disabled in config")

    line_id = str(line.get("line_id") or line.get("targets_segment_id") or "line")
    ref = resolve_reference_audio(ctx, line)
    pickup = dest_dir or ctx.path("vo_pickup")
    out_dir = pickup / "synthesized"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_wav = out_dir / f"{line_id}.wav"

    payload: dict[str, Any] = {
        "model_id": chatterbox_cfg().get("model_id"),
        "text": str(line.get("text") or ""),
        "ref_audio": str(ref),
        "out_wav": str(out_wav),
    }
    ref_doc = ctx.read_json(f"understanding/speaker_samples/{line.get('voice_speaker_id')}.json") if line.get("voice_speaker_id") and ctx.artifact_exists(f"understanding/speaker_samples/{line.get('voice_speaker_id')}.json") else {}
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
    from interview_mux.vo_synthesis_audit import record_synthesis

    record_synthesis(
        ctx,
        line,
        backend="chatterbox",
        out_wav=out_wav,
        ref_audio=str(ref),
        model_id=str(chatterbox_cfg().get("model_id") or ""),
    )
    from interview_mux.s2s_runner import promote_synthesized_vo

    promote_synthesized_vo(ctx, line_id=line_id, src=out_wav)
    return out_wav
