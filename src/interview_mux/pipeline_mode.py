"""Pipeline posture artifact — Layer 1 native vs synthetic framing authority."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
from interview_mux.run_context import RunContext

PIPELINE_MODE_REL = "understanding/pipeline_mode.json"

PipelineMode = Literal["native_only", "framing_sparse", "framing_full"]
DecidedBy = Literal[
    "operator_g_framing",
    "auto_accept",
    "deterministic_monologue",
    "artifact",
]

_VALID_MODES = frozenset({"native_only", "framing_sparse", "framing_full"})
_SKIP_TOPOLOGY_CLASSES = frozenset({"monologue_heavy", "monologue"})


def load_pipeline_mode(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(PIPELINE_MODE_REL):
        return None
    doc = ctx.read_json(PIPELINE_MODE_REL)
    return doc if isinstance(doc, dict) else None


def persist_pipeline_mode(
    ctx: RunContext,
    mode: PipelineMode,
    *,
    decided_by: DecidedBy,
    reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    if mode not in _VALID_MODES:
        raise ValueError(f"invalid pipeline mode {mode!r}")
    doc: dict[str, Any] = {
        "mode": mode,
        "decided_by": decided_by,
        "reason_codes": list(reason_codes or []),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    ctx.write_json(PIPELINE_MODE_REL, doc, skip_handoff=True)
    return doc


def _topology_class(ctx: RunContext) -> str | None:
    if not ctx.artifact_exists("understanding/source_topology.json"):
        return None
    topo = ctx.read_json("understanding/source_topology.json")
    if isinstance(topo, dict) and topo.get("topology_class"):
        return str(topo["topology_class"])
    return None


def _deterministic_monologue(ctx: RunContext) -> bool:
    topo = _topology_class(ctx)
    if topo in _SKIP_TOPOLOGY_CLASSES:
        return True
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    forced = str((meta or {}).get("gap_fill_mode") or "").lower()
    return forced == "skipped"


def resolve_effective_mode(ctx: RunContext) -> dict[str, Any]:
    """Authoritative Layer-1 posture from artifact, G-Framing gate, and run_meta."""
    stored = load_pipeline_mode(ctx)
    if stored and str(stored.get("mode") or "") in _VALID_MODES:
        return {
            "mode": str(stored["mode"]),
            "decided_by": str(stored.get("decided_by") or "artifact"),
            "reason_codes": list(stored.get("reason_codes") or []),
            "source": "artifact",
        }

    reason_codes: list[str] = []
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled as _gap_framing_enabled
    except Exception:
        def _gap_framing_enabled(_ctx: RunContext) -> bool:
            return True

    if gap_fill_was_skipped(ctx):
        reason_codes.append("gap_fill_skipped")
        return {
            "mode": "native_only",
            "decided_by": "operator_g_framing",
            "reason_codes": reason_codes,
            "source": "gap_fill_skip",
        }

    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    forced = str((meta or {}).get("gap_fill_mode") or "").lower()
    if forced == "skipped":
        reason_codes.append("run_meta_gap_fill_skipped")
        return {
            "mode": "native_only",
            "decided_by": "operator_g_framing",
            "reason_codes": reason_codes,
            "source": "run_meta",
        }

    if not _gap_framing_enabled(ctx):
        reason_codes.append("gap_framing_disabled")
        return {
            "mode": "native_only",
            "decided_by": "operator_g_framing",
            "reason_codes": reason_codes,
            "source": "gap_vo_gates",
        }

    if _deterministic_monologue(ctx):
        reason_codes.append("topology_monologue")
        return {
            "mode": "native_only",
            "decided_by": "deterministic_monologue",
            "reason_codes": reason_codes,
            "source": "topology",
        }

    sparse_hint = False
    if stored and str(stored.get("mode") or "") == "framing_sparse":
        sparse_hint = True
    mode: PipelineMode = "framing_sparse" if sparse_hint else "framing_full"
    return {
        "mode": mode,
        "decided_by": "auto_accept",
        "reason_codes": reason_codes or ["framing_enabled"],
        "source": "default",
    }


def is_native_only(ctx: RunContext) -> bool:
    return str(resolve_effective_mode(ctx).get("mode") or "") == "native_only"


__all__ = [
    "PIPELINE_MODE_REL",
    "PipelineMode",
    "DecidedBy",
    "is_native_only",
    "load_pipeline_mode",
    "persist_pipeline_mode",
    "resolve_effective_mode",
]
