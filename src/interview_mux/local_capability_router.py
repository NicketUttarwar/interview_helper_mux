"""Fail-fast local capability router for quality-allowlisted LLM stages.

Plans and runs LX-01/03/04/05 (manifest-gated). Zero retries per cap.
Preserves OpenAI escalate / force_openai / arbiter paths.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from interview_mux.config import merged_config
from interview_mux.local_capability_manifest import (
    enabled_caps_from_manifest,
    load_capability_manifest,
)
from interview_mux.local_llm_config import (
    LOCAL_COMPRESSOR_PROMPT,
    LOCAL_ESCALATE_ADVISORY_PROMPT,
    LOCAL_SHARD_PREP_PROMPT,
    capability_router_enabled,
    local_llm_enabled,
    max_local_steps,
    planner_fanout_k,
    stage_on_quality_allowlist,
)
from interview_mux.local_llm_runner import LocalLlmUnavailable, generate_local_chat, mlx_available
from interview_mux.local_volley_framer import LocalFramingResult, prepare_volley_for_llm
from interview_mux.run_context import RunContext
from interview_mux.stages.llm_runner import _extract_json, load_system_prompt


@dataclass
class RouterTelemetry:
    plan: list[str] = field(default_factory=list)
    caps_run: list[str] = field(default_factory=list)
    abort_reason: str | None = None
    planner_used: bool = False
    planner_fanout: int = 0
    advisory: dict[str, Any] | None = None
    shard_packets: list[dict[str, Any]] | None = None
    compressed_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": list(self.plan),
            "caps_run": list(self.caps_run),
            "abort_reason": self.abort_reason,
            "planner": {"used": self.planner_used, "fanout": self.planner_fanout},
            "advisory": self.advisory,
            "shard_packet_count": len(self.shard_packets or []),
            "had_compressed_digest": bool(self.compressed_digest),
        }


@dataclass
class RouterOutcome:
    volley: list[dict[str, str]]
    framing: LocalFramingResult | None
    telemetry: RouterTelemetry


_CALL_COUNTER: list[str] = []


def reset_local_call_counter() -> None:
    _CALL_COUNTER.clear()


def local_call_count() -> int:
    return len(_CALL_COUNTER)


def _record_cap(cap: str) -> None:
    _CALL_COUNTER.append(cap)


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    try:
        data = _extract_json(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _load_extra_digests(ctx: RunContext, paths: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for rel in paths:
        rel = str(rel).strip()
        if not rel:
            continue
        try:
            if ctx.artifact_exists(rel):
                out[rel] = ctx.read_json(rel) if rel.endswith(".json") else ctx.read_path(rel).read_text(encoding="utf-8")[:2000]
        except Exception:
            continue
    return out


def _predicted_fanout(stage_input: dict[str, Any]) -> int:
    for key in ("shard_plan", "predicted_shards", "decompose_shards"):
        val = stage_input.get(key)
        if isinstance(val, list) and val:
            return len(val)
    evidence = stage_input.get("evidence_shards")
    if isinstance(evidence, list):
        return len(evidence)
    segments = stage_input.get("segments")
    if isinstance(segments, list) and len(segments) >= 12:
        return max(3, min(6, len(segments) // 8))
    return 0


def _default_plan(enabled: frozenset[str], *, want_compress: bool, fanout: int, k: int) -> list[str]:
    steps: list[str] = []
    if want_compress and "LX-03" in enabled:
        steps.append("LX-03")
    if "LX-04" in enabled:
        steps.append("LX-04")
    if fanout >= k and "LX-05" in enabled:
        steps.append("LX-05")
    steps.append("LX-01")
    return steps


def _run_economy_planner(
    ctx: RunContext,
    stage_key: str,
    *,
    fanout: int,
    enabled: frozenset[str],
    cfg: dict[str, Any],
) -> list[str] | None:
    """One economy OpenAI planner call. Returns step caps or None on failure."""
    from interview_mux.stages.llm_runner import run_prompt_envelope

    user = json.dumps(
        {
            "stage_key": stage_key,
            "fanout": fanout,
            "enabled_caps": sorted(enabled),
            "instruction": "Schedule local caps then escalate_primary. abort_on_any_hard_fail true.",
        },
        indent=2,
    )
    try:
        envelope = run_prompt_envelope(
            f"{stage_key}__local_planner",
            "_shared/local-capability-planner.system.txt",
            user_content=user,
            ctx=ctx,
            include_preamble=False,
            task_kind="arbiter",
            explicit_tier="economy",
            record_stage_key=stage_key,
        )
    except Exception:
        return None
    artifacts = envelope.get("artifacts") if isinstance(envelope, dict) else None
    parsed = artifacts if isinstance(artifacts, dict) else envelope if isinstance(envelope, dict) else None
    if not parsed:
        return None
    steps_raw = parsed.get("steps") or []
    caps: list[str] = []
    for item in steps_raw:
        if not isinstance(item, dict):
            continue
        cap = str(item.get("cap") or "").strip()
        if cap in ("LX-03", "LX-04", "LX-05", "LX-01"):
            if cap == "LX-01" or cap in enabled:
                caps.append(cap)
    if not caps:
        return None
    if "LX-01" not in caps:
        caps.append("LX-01")
    _ = cfg
    return caps


def _run_lx03(
    ctx: RunContext,
    stage_key: str,
    stage_input: dict[str, Any],
    *,
    digest: str,
    extra: dict[str, Any],
    cfg: dict[str, Any],
    budget: int,
) -> tuple[str | None, str | None]:
    """Returns (compressed_digest, abort_reason)."""
    _record_cap("LX-03")
    try:
        system = load_system_prompt(LOCAL_COMPRESSOR_PROMPT, include_preamble=False)
        user = json.dumps(
            {
                "stage_key": stage_key,
                "stage_input_digest": digest,
                "extra_digest_paths": {k: (v if isinstance(v, str) else json.dumps(v)[:1500]) for k, v in extra.items()},
            },
            indent=2,
            ensure_ascii=False,
        )
        raw, _meta = generate_local_chat(
            system=system,
            user=user,
            ctx=ctx,
            stage_key=stage_key,
            task_kind="local_digest_compress",
            max_tokens_override=budget,
            cfg=cfg,
        )
    except LocalLlmUnavailable as exc:
        return None, f"lx03_unavailable:{exc}"
    except Exception as exc:
        return None, f"lx03_error:{type(exc).__name__}"
    parsed = _parse_json_object(raw)
    if not parsed:
        return None, "lx03_parse_fail"
    compressed = str(parsed.get("compressed_digest") or "").strip()
    if not compressed:
        return None, "lx03_empty_digest"
    try:
        conf = float(parsed.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    if conf < 0.5:
        return None, "lx03_low_confidence"
    return compressed, None


def _run_lx04(
    ctx: RunContext,
    stage_key: str,
    *,
    severity: str,
    truncation_flags: list[str],
    cfg: dict[str, Any],
    budget: int,
) -> dict[str, Any] | None:
    """Advisory only — never mutates escalate matrix."""
    _record_cap("LX-04")
    try:
        system = load_system_prompt(LOCAL_ESCALATE_ADVISORY_PROMPT, include_preamble=False)
        user = json.dumps(
            {
                "stage_key": stage_key,
                "severity": severity,
                "truncation_flags": truncation_flags,
            },
            indent=2,
        )
        raw, _meta = generate_local_chat(
            system=system,
            user=user,
            ctx=ctx,
            stage_key=stage_key,
            task_kind="local_escalate_advisory",
            max_tokens_override=budget,
            cfg=cfg,
        )
    except Exception:
        return None
    parsed = _parse_json_object(raw)
    return parsed


def _run_lx05(
    ctx: RunContext,
    stage_key: str,
    stage_input: dict[str, Any],
    *,
    cfg: dict[str, Any],
    budget: int,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    _record_cap("LX-05")
    try:
        system = load_system_prompt(LOCAL_SHARD_PREP_PROMPT, include_preamble=False)
        slim = {
            "stage_key": stage_key,
            "segment_ids": [
                str(s.get("segment_id") or s.get("id") or "")
                for s in (stage_input.get("segments") or [])[:40]
                if isinstance(s, dict)
            ],
            "notes": str(stage_input.get("task_line") or stage_key)[:400],
        }
        raw, _meta = generate_local_chat(
            system=system,
            user=json.dumps(slim, indent=2),
            ctx=ctx,
            stage_key=stage_key,
            task_kind="local_shard_prep",
            max_tokens_override=budget,
            cfg=cfg,
        )
    except LocalLlmUnavailable as exc:
        return None, f"lx05_unavailable:{exc}"
    except Exception as exc:
        return None, f"lx05_error:{type(exc).__name__}"
    parsed = _parse_json_object(raw)
    if not parsed:
        return None, "lx05_parse_fail"
    packets = parsed.get("packets")
    if not isinstance(packets, list) or not packets:
        return None, "lx05_empty_packets"
    return [p for p in packets if isinstance(p, dict)], None


def prepare_volley_via_router(
    ctx: RunContext,
    stage_key: str,
    stage_input: dict[str, Any],
    *,
    profile: str = "full",
    task_kind: str = "primary",
    cfg: dict[str, Any] | None = None,
    extra_digest_paths: list[str] | None = None,
    predicted_fanout: int | None = None,
) -> RouterOutcome:
    """
    Quality-allowlist router. Non-allowlist / disabled → thin pass through to prepare_volley_for_llm.
    """
    resolved_cfg = cfg or merged_config()
    tele = RouterTelemetry()

    if not local_llm_enabled(resolved_cfg) or not capability_router_enabled(resolved_cfg):
        volley, framing = prepare_volley_for_llm(
            ctx, stage_key, stage_input, profile=profile, task_kind=task_kind, cfg=resolved_cfg
        )
        return RouterOutcome(volley=volley, framing=framing, telemetry=tele)

    if not stage_on_quality_allowlist(stage_key, resolved_cfg):
        # Housekeeping / non-quality: zero router local spend beyond today's framer only if already framed —
        # plan: zero extra caps; still allow LX-01 via prepare when should_frame.
        volley, framing = prepare_volley_for_llm(
            ctx, stage_key, stage_input, profile=profile, task_kind=task_kind, cfg=resolved_cfg
        )
        tele.abort_reason = "not_on_quality_allowlist"
        return RouterOutcome(volley=volley, framing=framing, telemetry=tele)

    if task_kind != "primary":
        volley, framing = prepare_volley_for_llm(
            ctx, stage_key, stage_input, profile=profile, task_kind=task_kind, cfg=resolved_cfg
        )
        return RouterOutcome(volley=volley, framing=framing, telemetry=tele)

    manifest = load_capability_manifest()
    enabled = enabled_caps_from_manifest(manifest)
    budgets = (manifest or {}).get("budgets") or {}
    fanout = predicted_fanout if predicted_fanout is not None else _predicted_fanout(stage_input)
    k = planner_fanout_k(resolved_cfg)

    from interview_mux.model_registry import stage_severity
    from interview_mux.truncation_policy import build_framer_digest

    severity = stage_severity(stage_key)
    digest, digest_truncated = build_framer_digest(stage_input, stage_key, cfg=resolved_cfg)
    want_compress = bool(digest_truncated or len(digest) > 3500)
    extra = _load_extra_digests(ctx, list(extra_digest_paths or stage_input.get("_extra_digest_paths") or []))

    plan = _default_plan(enabled, want_compress=want_compress, fanout=fanout, k=k)

    # Optional one-shot economy planner when fanout high and LX-05 enabled
    if fanout >= k and "LX-05" in enabled and mlx_available():
        planned = _run_economy_planner(ctx, stage_key, fanout=fanout, enabled=enabled, cfg=resolved_cfg)
        tele.planner_used = True
        tele.planner_fanout = fanout
        if planned:
            plan = planned
        # planner failure → keep default plan (no second planner call)

    # Cap steps
    plan = plan[: max_local_steps(resolved_cfg)]
    tele.plan = list(plan)

    working_input = dict(stage_input)
    if extra:
        working_input["_router_extra_digests"] = {k: "present" for k in extra}

    for cap in plan:
        if tele.abort_reason:
            break
        if cap == "LX-03":
            if "LX-03" not in enabled:
                continue
            compressed, abort = _run_lx03(
                ctx,
                stage_key,
                working_input,
                digest=digest,
                extra=extra,
                cfg=resolved_cfg,
                budget=int(budgets.get("lx03_max_tokens") or 512),
            )
            tele.caps_run.append("LX-03")
            if abort:
                tele.abort_reason = abort
                ctx.log(
                    f"Local capability branch aborted ({abort}); escalating OpenAI for {stage_key}",
                    level="warning",
                    stage=stage_key,
                    detail={"local_branch_aborted": abort},
                )
                break
            tele.compressed_digest = compressed
            working_input = dict(working_input)
            working_input["_local_compressed_digest"] = compressed
            digest = compressed or digest
        elif cap == "LX-04":
            if "LX-04" not in enabled:
                continue
            from interview_mux.context_volley import truncation_flags_for_volley

            # advisory before framer — use empty volley flags from digest path
            advice = _run_lx04(
                ctx,
                stage_key,
                severity=severity,
                truncation_flags=["framer_digest_truncated"] if digest_truncated else [],
                cfg=resolved_cfg,
                budget=int(budgets.get("lx04_max_tokens") or 256),
            )
            tele.caps_run.append("LX-04")
            tele.advisory = advice
            # never abort on advisory; never change escalate
        elif cap == "LX-05":
            if "LX-05" not in enabled:
                continue
            packets, abort = _run_lx05(
                ctx,
                stage_key,
                working_input,
                cfg=resolved_cfg,
                budget=int(budgets.get("lx05_max_tokens") or 768),
            )
            tele.caps_run.append("LX-05")
            if abort:
                tele.abort_reason = abort
                ctx.log(
                    f"Local capability branch aborted ({abort}); escalating OpenAI for {stage_key}",
                    level="warning",
                    stage=stage_key,
                    detail={"local_branch_aborted": abort},
                )
                break
            tele.shard_packets = packets
            working_input = dict(working_input)
            working_input["_local_shard_packets"] = packets
        elif cap == "LX-01":
            tele.caps_run.append("LX-01")
            _record_cap("LX-01")
            volley, framing = prepare_volley_for_llm(
                ctx,
                stage_key,
                working_input,
                profile=profile,
                task_kind=task_kind,
                cfg=resolved_cfg,
            )
            if framing and framing.fallback == "local_framing_failed":
                tele.abort_reason = "lx01_framing_failed"
            if framing is not None:
                meta = framing.to_attempt_meta()
                meta["router"] = tele.to_dict()
                # stash on framing via reason extension for routing meta
                framing.reason = framing.reason or ""
                if tele.abort_reason and "local_branch_aborted" not in framing.reason:
                    framing.escalate = True
                    framing.reason = f"local_branch_aborted:{tele.abort_reason}"
            return RouterOutcome(volley=volley, framing=framing, telemetry=tele)

    # Aborted before LX-01 or plan without LX-01 — still build OpenAI volley, escalate
    volley, framing = prepare_volley_for_llm(
        ctx,
        stage_key,
        working_input,
        profile=profile,
        task_kind=task_kind,
        cfg=resolved_cfg,
    )
    if framing is None:
        framing = LocalFramingResult(escalate=True, reason=tele.abort_reason or "router_fallback")
    else:
        framing.escalate = True
        if tele.abort_reason:
            framing.reason = f"local_branch_aborted:{tele.abort_reason}"
    return RouterOutcome(volley=volley, framing=framing, telemetry=tele)


def attach_router_meta(envelope: dict[str, Any], outcome: RouterOutcome) -> None:
    routing = envelope.setdefault("_routing_meta", {})
    local_meta = routing.get("local_llm") or {}
    if outcome.framing:
        local_meta = {**outcome.framing.to_attempt_meta(), **local_meta}
    local_meta["router"] = outcome.telemetry.to_dict()
    routing["local_llm"] = local_meta
