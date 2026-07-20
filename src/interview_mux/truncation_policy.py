"""Universal truncation detection and escalation for all LLM gateways."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Iterator, Literal

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

# Active volley rebuild boost (0 = baseline caps). Applied by context_volley._char_limit.
_CONTEXT_CAP_BOOST_ROUND: ContextVar[int] = ContextVar("context_cap_boost_round", default=0)
# When True, aggressively raise clip caps so rebuild can clear field_truncated markers.
_CLEAR_FIELD_TRUNCATION: ContextVar[bool] = ContextVar("clear_field_truncation", default=False)


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


@dataclass
class CapBoostRebuildResult:
    """Outcome of rebuild-with-boost escalation before primary/shard calls."""

    volley: list[dict[str, str]]
    framing: Any = None
    flags: list[str] = field(default_factory=list)
    boost_round: int = 0
    cleared: bool = False
    steps: list[str] = field(default_factory=list)


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
        "framer_digest_limits": {"speaker_roles": 24000, "content_context": 24000, "default": 8000},
        # Baseline + progressive rebuild multipliers (round index into this list).
        "context_cap_boost_steps": [1.0, 2.0, 4.0, 8.0, 16.0],
        "raise_escalation_required": True,
        # When field_truncated remains after multiplier boost, raise clip caps to this floor.
        "field_truncation_clear_floor_chars": 8000,
    }
    raw = base.get("truncation_integrity") or {}
    return {**defaults, **raw}


def truncation_integrity_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(truncation_integrity_cfg(cfg).get("enabled", True))


def get_context_cap_boost_round() -> int:
    return int(_CONTEXT_CAP_BOOST_ROUND.get())


def clear_field_truncation_enabled() -> bool:
    return bool(_CLEAR_FIELD_TRUNCATION.get())


def set_context_cap_boost_round(round_idx: int) -> Token:
    return _CONTEXT_CAP_BOOST_ROUND.set(max(0, int(round_idx)))


@contextmanager
def context_cap_boost(
    round_idx: int,
    *,
    clear_field_truncation: bool = False,
) -> Iterator[None]:
    """Temporarily raise context clip caps for a rebuild/retry pass."""
    token = set_context_cap_boost_round(round_idx)
    clear_token = _CLEAR_FIELD_TRUNCATION.set(bool(clear_field_truncation))
    try:
        yield
    finally:
        _CLEAR_FIELD_TRUNCATION.reset(clear_token)
        _CONTEXT_CAP_BOOST_ROUND.reset(token)


def digest_limit_for_stage(stage_key: str, cfg: dict[str, Any] | None = None) -> int:
    ti = truncation_integrity_cfg(cfg)
    limits = ti.get("framer_digest_limits") or {}
    if stage_key in limits:
        base = int(limits[stage_key])
    else:
        ctx_cfg = (cfg or merged_config()).get("analysis", {}).get("context") or {}
        if stage_key == "speaker_roles":
            base = int(ctx_cfg.get("speaker_roles_sample_chars", 24000))
        else:
            base = int(limits.get("default", 8000))
    return apply_context_cap_boost(base, cfg=cfg, field_clip=False)


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
    steps = truncation_integrity_cfg(cfg).get("context_cap_boost_steps") or [1.0, 2.0, 4.0, 8.0, 16.0]
    idx = min(max(int(round_idx), 0), len(steps) - 1)
    return float(steps[idx])


def apply_context_cap_boost(
    base: int,
    *,
    cfg: dict[str, Any] | None = None,
    field_clip: bool = False,
) -> int:
    """Apply active ContextVar boost (and optional field-clear floor) to a char cap."""
    base_i = max(0, int(base))
    mult = context_cap_multiplier(get_context_cap_boost_round(), cfg)
    boosted = int(base_i * mult)
    if field_clip and clear_field_truncation_enabled():
        floor = int(truncation_integrity_cfg(cfg).get("field_truncation_clear_floor_chars", 8000))
        boosted = max(boosted, floor)
    return max(base_i, boosted) if get_context_cap_boost_round() > 0 or clear_field_truncation_enabled() else base_i


def max_cap_boost_round(cfg: dict[str, Any] | None = None) -> int:
    steps = truncation_integrity_cfg(cfg).get("context_cap_boost_steps") or [1.0, 2.0, 4.0, 8.0, 16.0]
    configured = int(truncation_integrity_cfg(cfg).get("max_escalation_rounds_per_call", 4))
    return min(max(len(steps) - 1, 0), max(configured, 0))


def escalation_boost_rounds(cfg: dict[str, Any] | None = None) -> list[int]:
    """Round indices to try when clearing truncation (skip baseline 0; start at 1)."""
    top = max_cap_boost_round(cfg)
    if top < 1:
        return [0]
    return list(range(1, top + 1))


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


def rebuild_volley_clearing_truncation(
    ctx: Any,
    stage_key: str,
    stage_input: dict[str, Any],
    *,
    profile: str = "full",
    task_kind: str = "primary",
    initial_volley: list[dict[str, str]] | None = None,
    initial_framing: Any = None,
    initial_flags: list[str] | None = None,
    cfg: dict[str, Any] | None = None,
) -> CapBoostRebuildResult:
    _ = (ctx, stage_key, stage_input, profile, task_kind, cfg)
    volley = list(initial_volley or [])
    flags = list(initial_flags or [])
    return CapBoostRebuildResult(
        volley=volley,
        framing=initial_framing,
        flags=flags,
        boost_round=get_context_cap_boost_round(),
        cleared=not flags,
        steps=["v2_no_volley_rebuild"],
    )


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
