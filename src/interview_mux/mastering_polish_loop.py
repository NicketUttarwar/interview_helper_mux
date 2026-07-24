"""Closed-loop realization polish: audio-grounded audit → bounded remux → re-verify.

Spec: docs/cross-cutting/mastering-audition-loop.md
Schema: mastering_polish_audit.schema.json
Artifact: mastering/polish_audit.json

Remux is deliberately bounded: it may adjust what exists, never restructure. A
structural change means the Shape Engine was wrong, and that needs a new plan.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.mastering_hardening_config import gate_cfg, gate_mode
from interview_mux.run_context import RunContext

POLISH_ARTIFACT = "mastering/polish_audit.json"

AUDIO_DIMENSIONS: tuple[str, ...] = (
    "speech_masking",
    "transition_jolt",
    "dead_air",
    "sfx_repetition",
    "listener_fatigue",
    "cold_open_payoff",
    "plan_adherence",
)

ALLOWED_REMUX_ACTIONS: frozenset[str] = frozenset(
    {
        "adjust_level",
        "adjust_duck",
        "remove_cue",
        "replace_cue",
        "adjust_fade",
        "trim_silence",
        "extend_silence",
        "adjust_crossfade",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def max_remux_rounds(cfg: dict[str, Any] | None = None) -> int:
    return max(0, int(gate_cfg("polish", cfg).get("max_remux_rounds") or 0))


def audio_grounding_required(cfg: dict[str, Any] | None = None) -> bool:
    return bool(gate_cfg("polish", cfg).get("audio_grounded", True))


def audit_input_audio(ctx: RunContext) -> Path | None:
    """The most finished render available: mix draft first, then assembly preview."""
    for rel in ("master/mix.wav", "master/assembly_preview.wav", "master/preview.wav"):
        if ctx.artifact_exists(rel):
            path = ctx.read_path(*rel.split("/"))
            if path.is_file():
                return path
    return None


def build_audit_request(
    ctx: RunContext,
    *,
    plan: dict[str, Any] | None = None,
    rubric_ref: str | None = None,
    round_index: int = 0,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble what the flagship audit needs, including measured audio features."""
    from interview_mux.mastering_auditions import measure_features

    audio = audit_input_audio(ctx)
    features = measure_features(audio) if audio else {}
    return {
        "audited_audio_ref": str(audio.relative_to(ctx.run_dir)) if audio else None,
        "audio_grounded": bool(audio) and audio_grounding_required(cfg),
        "audio_features": features,
        "rubric_ref": rubric_ref,
        "remux_round": round_index,
        "max_remux_rounds": max_remux_rounds(cfg),
        "plan": plan,
    }


def normalize_audit(
    audit: dict[str, Any],
    request: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stamp loop state onto an audit response and drop out-of-scope directives."""
    rounds = max_remux_rounds(cfg)
    round_index = int(request.get("remux_round") or 0)
    directives = [
        d
        for d in (audit.get("remux_directives") or [])
        if isinstance(d, dict) and str(d.get("action")) in ALLOWED_REMUX_ACTIONS
    ]
    rejected = [
        str(d.get("action"))
        for d in (audit.get("remux_directives") or [])
        if isinstance(d, dict) and str(d.get("action")) not in ALLOWED_REMUX_ACTIONS
    ]

    out = {
        **audit,
        "version": 1,
        "audio_grounded": bool(request.get("audio_grounded")),
        "audited_audio_ref": request.get("audited_audio_ref"),
        "audio_features": request.get("audio_features") or {},
        "rubric_ref": request.get("rubric_ref"),
        "remux_directives": directives,
        "remux_round": round_index,
        "max_remux_rounds": rounds,
        "remux_exhausted": round_index >= rounds,
        "generated_at": audit.get("generated_at") or _now(),
    }
    if rejected:
        out["issues"] = [
            *(out.get("issues") or []),
            f"structural remux actions rejected (out of scope): {', '.join(sorted(set(rejected)))}",
        ]
    if out["remux_exhausted"] and out.get("verdict") in {"fail", "remux_suggested"}:
        out["residual_issues"] = list(out.get("issues") or [])
    return out


def should_remux(audit: dict[str, Any], *, cfg: dict[str, Any] | None = None) -> bool:
    if not audit.get("remux_directives"):
        return False
    if int(audit.get("remux_round") or 0) >= max_remux_rounds(cfg):
        return False
    return audit.get("verdict") in {"fail", "remux_suggested", "soft_pass"}


def blocks_finalize(audit: dict[str, Any], *, cfg: dict[str, Any] | None = None) -> bool:
    """Only an authoritative gate may hold back master_finalize."""
    if gate_mode("polish", cfg) != "authoritative":
        return False
    return audit.get("verdict") == "fail" and bool(audit.get("remux_exhausted"))


def write_audit(ctx: RunContext, audit: dict[str, Any]) -> None:
    ctx.write_json(POLISH_ARTIFACT, audit)
