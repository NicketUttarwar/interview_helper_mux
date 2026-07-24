"""Route the 38 mastering research fields for one source.

Spec: docs/cross-cutting/mastering-quality-hardening.md (Workstream 1)
Schema: mastering_research_routing.schema.json
Artifact: mastering/research/routing.json
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from interview_mux.mastering_hardening_config import routing_cfg
from interview_mux.run_context import RunContext

Disposition = Literal["required", "thin", "skip", "deepen", "revisit_after_preview"]

ROUTING_ARTIFACT = "mastering/research/routing.json"

# Field dependency on an operator flow or asset. When the dependency is absent the
# field is skipped rather than guessed at — never invent evidence for a skipped flow.
FIELD_DEPENDENCIES: dict[str, str] = {
    "gap_framing_coverage": "gap_framing",
    "gap_vo_synthesis": "gap_framing",
    "framing_question_quality": "gap_framing",
    "voice_reference_quality": "voice_reference",
    "preclean_outcome": "preclean",
    "nle_operator_edits": "nle",
    "sfx_asset_catalog": "sfx_assets",
    "soundscape_plan": "sfx_assets",
    "mmaudio_asset_qa": "sfx_assets",
    "sound_design_palettes": "sfx_assets",
}

# Fields that cannot be judged before audio exists.
POST_PREVIEW_FIELDS: frozenset[str] = frozenset(
    {"master_verify_readiness", "mix_tier_fit", "intelligibility_ceiling"}
)

# Fields other fields cite; degrade to `thin` instead of `skip`.
FOUNDATIONAL_FIELDS: frozenset[str] = frozenset(
    {
        "source_hygiene",
        "transcript_quality",
        "speaker_roles",
        "source_topology",
        "speaker_volleys",
        "pickup_voice",
        "thesis_and_value",
        "segment_inventory",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def route_fields(
    *,
    fields: list[dict[str, Any]],
    signature: dict[str, Any] | None = None,
    available_flows: set[str] | frozenset[str] | None = None,
    deepen_hints: set[str] | frozenset[str] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Decide a disposition for every research field.

    `fields` are `{field_id, wave}` rows from the research catalog. `available_flows`
    names the operator flows and asset families that actually ran for this source.
    """
    routing = routing_cfg(cfg)
    default_disposition = str(routing.get("default_disposition") or "required")
    max_deep = int(routing.get("max_deep_fields") or 12)
    flows = set(available_flows or ())
    hints = set(deepen_hints or ())
    sig = dict(signature or {})
    skipped_flows = {str(f) for f in (sig.get("skipped_flows") or [])}

    routed: list[dict[str, Any]] = []
    deep_count = 0
    for row in fields:
        field_id = str(row.get("field_id") or "")
        if not field_id:
            continue
        wave = int(row.get("wave") or 1)
        dependency = FIELD_DEPENDENCIES.get(field_id)
        signals: list[str] = []

        if dependency and dependency in skipped_flows:
            disposition: Disposition = "skip"
            reason = f"operator skipped {dependency}"
            signals.append(f"skipped_flow:{dependency}")
        elif dependency and dependency not in flows:
            disposition = "skip"
            reason = f"{dependency} inputs absent for this source"
            signals.append(f"missing_dependency:{dependency}")
        elif field_id in POST_PREVIEW_FIELDS:
            disposition = "revisit_after_preview"
            reason = "cannot be judged before rendered audio exists"
            signals.append("needs_audio")
        elif field_id in hints and deep_count < max_deep:
            disposition = "deepen"
            reason = "signature flags this field as decisive here"
            signals.append("deepen_hint")
            deep_count += 1
        else:
            disposition = default_disposition  # type: ignore[assignment]
            reason = "default disposition for this source"

        if disposition == "skip" and field_id in FOUNDATIONAL_FIELDS:
            disposition = "thin"
            reason = f"{reason}; foundational field kept thin because others cite it"

        routed.append(
            {
                "field_id": field_id,
                "wave": wave,
                "disposition": disposition,
                "reason": reason,
                "signals": signals,
                "model_tier": _tier_for(disposition),
            }
        )

    return {
        "version": 1,
        "mode": str(routing.get("mode") or "advisory"),
        "source_signature": sig,
        "fields": routed,
        "wave_budgets": _wave_budgets(routed),
        "generated_at": _now(),
    }


def _tier_for(disposition: str) -> str:
    if disposition == "deepen":
        return "flagship"
    if disposition == "thin":
        return "economy"
    return "standard"


def _wave_budgets(routed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cap each wave by how many fields it actually needs to run."""
    per_wave: dict[int, int] = {}
    for row in routed:
        if row["disposition"] in {"skip", "revisit_after_preview"}:
            continue
        per_wave[int(row["wave"])] = per_wave.get(int(row["wave"]), 0) + 1
    return [{"wave": w, "max_fields": n} for w, n in sorted(per_wave.items())]


def active_field_ids(routing: dict[str, Any]) -> list[str]:
    """Fields that should run now (excludes skip / revisit_after_preview)."""
    out: list[str] = []
    for row in routing.get("fields") or []:
        if not isinstance(row, dict):
            continue
        if row.get("disposition") in {"skip", "revisit_after_preview"}:
            continue
        out.append(str(row.get("field_id")))
    return out


def disposition_for(routing: dict[str, Any], field_id: str) -> str | None:
    for row in routing.get("fields") or []:
        if isinstance(row, dict) and row.get("field_id") == field_id:
            return str(row.get("disposition"))
    return None


def write_routing(ctx: RunContext, routing: dict[str, Any]) -> None:
    ctx.write_json(ROUTING_ARTIFACT, routing)


def load_routing(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(ROUTING_ARTIFACT):
        return None
    doc = ctx.read_json(ROUTING_ARTIFACT)
    return doc if isinstance(doc, dict) else None
