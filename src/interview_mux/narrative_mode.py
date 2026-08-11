"""Narrative mode prefer/forbid, consistency QC, and hybrid acceptance.

Canon: docs/cross-cutting/narrative-mode-and-montage.md
Data: docs/cross-cutting/narrative-mode-prefer-forbid.json
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

NARRATIVE_MODES: tuple[str, ...] = (
    "conversational_host",
    "guide_summary",
    "documentary_bridge",
    "hook_montage",
    "sparse_source",
    "hybrid_bespoke",
)

GRAMMAR_MOVES: tuple[str, ...] = (
    "vo_then_clip",
    "clip_then_react_vo",
    "summary_replace_setup",
    "cold_open_then_body",
    "act_preface_blocks",
    "interleaved_bridges",
    "information_package_then_block",
)

_DOCS = Path(__file__).resolve().parents[2] / "docs" / "cross-cutting"
_PREFER_FORBID = _DOCS / "narrative-mode-prefer-forbid.json"
_PRIORS = _DOCS / "narrative-mode-priors.json"


@lru_cache(maxsize=1)
def load_prefer_forbid() -> dict[str, Any]:
    return json.loads(_PREFER_FORBID.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_priors() -> dict[str, Any]:
    return json.loads(_PRIORS.read_text(encoding="utf-8"))


def matrix_for_mode(mode: str, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    doc = load_prefer_forbid()
    modes = doc.get("modes") or {}
    base = dict(modes.get(mode) or modes.get("sparse_source") or {})
    if mode == "hybrid_bespoke" and isinstance(plan, dict):
        override = plan.get("hybrid_prefer_forbid")
        if isinstance(override, dict):
            base = {**base, **override}
    return base


def sonic_density_for_mode(mode: str, plan: dict[str, Any] | None = None) -> str:
    return str(matrix_for_mode(mode, plan).get("sonic_density") or "minimal")


def default_pov_for_mode(mode: str, plan: dict[str, Any] | None = None) -> str:
    return str(matrix_for_mode(mode, plan).get("default_pov") or "host_second_person")


def prefer_forbid_volley_block(mode: str, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Inject into missing_framing / gap compose volleys."""
    m = matrix_for_mode(mode, plan)
    return {
        "narrative_mode": mode,
        "prefer_line_categories": list(m.get("prefer_line_categories") or []),
        "forbid_line_categories": list(m.get("forbid_line_categories") or []),
        "prefer_grammar_moves": list(m.get("prefer_grammar_moves") or []),
        "forbid_grammar_moves": list(m.get("forbid_grammar_moves") or []),
        "default_pov": default_pov_for_mode(mode, plan),
        "sonic_density": sonic_density_for_mode(mode, plan),
    }


def mode_consistency_report(
    *,
    mode: str,
    interviewer_lines: list[dict[str, Any]],
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Advisory-only histogram vs prefer/forbid. Never blocking."""
    m = matrix_for_mode(mode, plan)
    forbid = set(m.get("forbid_line_categories") or [])
    prefer = set(m.get("prefer_line_categories") or [])
    counts: dict[str, int] = {}
    violations: list[dict[str, str]] = []
    for line in interviewer_lines:
        if not isinstance(line, dict):
            continue
        cat = str(line.get("line_category") or "")
        if not cat:
            continue
        counts[cat] = counts.get(cat, 0) + 1
        # System-owned layups / episode orientation are not mode-matrix choices.
        origin = str(line.get("origin") or "")
        gap_type = str(line.get("gap_type") or "")
        if origin == "nugget_layup" or gap_type == "nugget_layup":
            continue
        if bool(line.get("episode_orientation")):
            continue
        if cat in forbid:
            violations.append(
                {
                    "line_id": str(line.get("line_id") or ""),
                    "line_category": cat,
                    "reason": "forbidden_for_mode",
                }
            )
    preferred_used = sum(counts.get(c, 0) for c in prefer)
    total = sum(counts.values())
    return {
        "advisory": True,
        "blocking": False,
        "mode": mode,
        "category_counts": counts,
        "preferred_used": preferred_used,
        "total_lines": total,
        "violations": violations,
        "ok": len(violations) == 0,
    }


def hybrid_acceptance(plan: dict[str, Any]) -> tuple[bool, str]:
    if plan.get("narrative_mode") != "hybrid_bespoke":
        return True, "not_hybrid"
    label = plan.get("hybrid_label")
    refs = plan.get("evidence_refs") or plan.get("hybrid_evidence_refs") or []
    anti = plan.get("anti_patterns") or plan.get("hybrid_anti_patterns") or []
    if not label:
        return False, "missing_hybrid_label"
    if not isinstance(refs, list) or len(refs) < 2:
        return False, "hybrid_needs_two_evidence_refs"
    if not isinstance(anti, list) or not anti:
        return False, "hybrid_needs_anti_patterns"
    matrix = plan.get("hybrid_prefer_forbid")
    if not isinstance(matrix, dict):
        return False, "hybrid_needs_in_plan_matrix"
    return True, "ok"


def demote_hybrid(plan: dict[str, Any]) -> dict[str, Any]:
    out = dict(plan)
    out["narrative_mode"] = "guide_summary"
    out["hybrid_demoted"] = True
    out["hybrid_demote_reason"] = hybrid_acceptance(plan)[1]
    reasons = list(out.get("degradation_reasons") or [])
    reasons.append("hybrid_acceptance_failed")
    out["degradation_reasons"] = reasons
    if out.get("plan_status") == "complete":
        out["plan_status"] = "degraded"
    return out


def nearest_mode_from_priors(hints: dict[str, str]) -> str:
    """Pick highest-weight mode from style hints; default conversational_host."""
    scores: dict[str, float] = {m: 0.0 for m in NARRATIVE_MODES if m != "hybrid_bespoke"}
    for row in load_priors().get("priors") or []:
        if not isinstance(row, dict):
            continue
        src = str(row.get("hint_source") or "")
        val = str(row.get("hint_value") or "")
        mode = str(row.get("mode") or "")
        if hints.get(src) == val and mode in scores:
            scores[mode] += float(row.get("weight") or 0)
    if not scores or max(scores.values()) <= 0:
        return "conversational_host"
    return max(scores.items(), key=lambda kv: kv[1])[0]
