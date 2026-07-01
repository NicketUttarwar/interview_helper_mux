"""Universal truncation detection and escalation for all LLM gateways."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from interview_mux.config import merged_config
from interview_mux.model_registry import TIER_ORDER, next_tier

TRUNCATION_MARKERS: tuple[str, ...] = (
    "…[stage data truncated]",
    "…[digest truncated]",
    "…[truncated]",
    "…[volley_middle_truncated]",
)

MARKER_FLAG_MAP: dict[str, str] = {
    "…[stage data truncated]": "max_stage_data_chars",
    "…[digest truncated]": "framer_digest_truncated",
    "…[truncated]": "field_truncated",
    "…[volley_middle_truncated]": "volley_middle_truncated",
}


class TruncationEscalationRequired(Exception):
    """Input volley is truncated; caller should rebuild with higher caps or decompose."""

    def __init__(self, *, flags: list[str], steps: list[str], stage_key: str) -> None:
        self.flags = flags
        self.steps = steps
        self.stage_key = stage_key
        super().__init__(f"Truncation escalation required ({stage_key}): {', '.join(flags)}")


@dataclass
class TruncationScan:
    truncated: bool
    flags: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)


@dataclass
class TruncationEscalationMeta:
    rounds: int = 0
    steps: list[str] = field(default_factory=list)
    final_flags: list[str] = field(default_factory=list)
    provider: str = "openai"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rounds": self.rounds,
            "steps": self.steps,
            "final_flags": self.final_flags,
            "provider": self.provider,
        }


def truncation_integrity_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    base = (cfg or merged_config()).get("analysis") or {}
    defaults = {
        "enabled": True,
        "enforce_at_gateways": True,
        "never_accept_truncated_output": True,
        "never_inject_framer_when_truncated": True,
        "local_on_truncation": "escalate_openai",
        "openai_tier_ladder": list(TIER_ORDER),
        "decompose_at_flagship_if_still_truncated": True,
        "max_escalation_rounds_per_call": 4,
        "framer_digest_limits": {"speaker_roles": 24000, "default": 8000},
        "context_cap_boost_steps": [1.0, 2.0, 4.0],
    }
    raw = base.get("truncation_integrity") or {}
    return {**defaults, **raw}


def truncation_integrity_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(truncation_integrity_cfg(cfg).get("enabled", True))


def digest_limit_for_stage(stage_key: str, cfg: dict[str, Any] | None = None) -> int:
    ti = truncation_integrity_cfg(cfg)
    limits = ti.get("framer_digest_limits") or {}
    if stage_key in limits:
        return int(limits[stage_key])
    ctx_cfg = (cfg or merged_config()).get("analysis", {}).get("context") or {}
    if stage_key == "speaker_roles":
        return int(ctx_cfg.get("speaker_roles_sample_chars", 24000))
    return int(limits.get("default", 8000))


def build_framer_digest(
    stage_input: dict[str, Any],
    stage_key: str,
    *,
    cfg: dict[str, Any] | None = None,
) -> tuple[str, bool]:
    import json

    full = json.dumps(stage_input, ensure_ascii=False)
    limit = digest_limit_for_stage(stage_key, cfg)
    if len(full) <= limit:
        return full, False
    return full[:limit] + "\n…[digest truncated]", True


def scan_text(text: str, *, location: str = "text") -> TruncationScan:
    flags: list[str] = []
    locations: list[str] = []
    for marker, flag in MARKER_FLAG_MAP.items():
        if marker in text:
            if flag not in flags:
                flags.append(flag)
            locations.append(location)
    return TruncationScan(truncated=bool(flags), flags=flags, locations=locations)


def scan_llm_input(
    *,
    messages: list[dict[str, str]] | None = None,
    user_content: str | None = None,
    system: str | None = None,
) -> TruncationScan:
    merged_flags: list[str] = []
    merged_locs: list[str] = []
    parts: list[tuple[str, str]] = []
    if system:
        parts.append(("system", system))
    if user_content:
        parts.append(("user_content", user_content))
    if messages:
        for i, m in enumerate(messages):
            parts.append((f"messages[{i}]", str(m.get("content", ""))))
    for loc, text in parts:
        sub = scan_text(text, location=loc)
        for f in sub.flags:
            if f not in merged_flags:
                merged_flags.append(f)
        merged_locs.extend(sub.locations)
    return TruncationScan(truncated=bool(merged_flags), flags=merged_flags, locations=merged_locs)


def scan_messages(messages: list[dict[str, str]]) -> TruncationScan:
    return scan_llm_input(messages=messages)


def context_cap_multiplier(round_idx: int, cfg: dict[str, Any] | None = None) -> float:
    steps = truncation_integrity_cfg(cfg).get("context_cap_boost_steps") or [1.0, 2.0, 4.0]
    idx = min(max(round_idx, 0), len(steps) - 1)
    return float(steps[idx])


def next_openai_tier(current: str) -> str:
    return next_tier(current)


def tier_ladder_index(tier: str, cfg: dict[str, Any] | None = None) -> int:
    ladder = truncation_integrity_cfg(cfg).get("openai_tier_ladder") or list(TIER_ORDER)
    try:
        return ladder.index(tier)
    except ValueError:
        return 0


def tier_at_ladder_step(step: int, cfg: dict[str, Any] | None = None) -> str:
    ladder = truncation_integrity_cfg(cfg).get("openai_tier_ladder") or list(TIER_ORDER)
    idx = min(max(step, 0), len(ladder) - 1)
    return str(ladder[idx])


def validate_framer_turns(
    turns: list[dict[str, str]],
    stage_input: dict[str, Any],
    *,
    stage_key: str,
) -> tuple[list[dict[str, str]], list[str]]:
    """Reject misleading uncertainty turns when transcript evidence exists."""
    rejected: list[str] = []
    speakers = stage_input.get("speakers")
    samples = stage_input.get("transcript_samples") or stage_input.get("transcript_excerpt")
    if not samples or not speakers:
        return turns, rejected
    uncertainty_phrases = (
        "unclear",
        "not explicitly labeled",
        "cannot determine",
        "ambiguous",
    )
    kept: list[dict[str, str]] = []
    for turn in turns:
        content = str(turn.get("content", "")).lower()
        if any(p in content for p in uncertainty_phrases):
            rejected.append(content[:80])
            continue
        kept.append(turn)
    return kept, rejected


def should_skip_framer_injection(
    framing: Any,
    *,
    stage_key: str,
    prior_one_liners: list[Any],
    cfg: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    ti = truncation_integrity_cfg(cfg)
    if getattr(framing, "digest_truncated", False) and ti.get("never_inject_framer_when_truncated", True):
        return True, "digest_truncated"
    from interview_mux.local_llm_config import force_escalate_stage

    if force_escalate_stage(stage_key) and stage_key == "speaker_roles" and not prior_one_liners:
        return True, "empty_priors_p0"
    if not getattr(framing, "volley_turns", None):
        return True, "empty_turns"
    return False, ""


def attach_truncation_meta(envelope: dict[str, Any], meta: TruncationEscalationMeta) -> None:
    llm_meta = envelope.setdefault("_llm_meta", {})
    llm_meta["truncation_escalation"] = meta.to_dict()


def log_truncation_event(
    ctx: Any,
    *,
    stage_key: str,
    event: str,
    scan: TruncationScan,
    step: str | None = None,
) -> None:
    if ctx is None:
        return
    ctx.log(
        f"Truncation {event} ({stage_key}): {', '.join(scan.flags[:3]) or 'none'}",
        level="warning" if scan.truncated else "info",
        stage=stage_key,
        action_id=f"truncation.{event}",
        detail={"flags": scan.flags, "step": step, "locations": scan.locations[:6]},
        origin="pipeline",
    )


ProviderKind = Literal["openai", "local_mlx"]
