"""Local MLX gap-fill for missing downstream-required artifact fields."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any

from interview_mux.downstream_requirements import list_fill_if_missing_gaps
from interview_mux.llm_output_resilience import ResilienceReport
from interview_mux.local_llm_runner import LocalLlmUnavailable, generate_local_chat
from interview_mux.stages.llm_runner import load_system_prompt


def _deterministic_claim_time_fill(artifacts: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Copy topic approx_time_range onto claims missing anchors (no API)."""
    out = copy.deepcopy(artifacts)
    generated: list[dict[str, Any]] = []
    topics = out.get("topics") or []
    default_range = ""
    for topic in topics:
        if isinstance(topic, dict) and topic.get("approx_time_range"):
            default_range = str(topic["approx_time_range"])
            break

    claims = out.get("key_claims") or []
    for i, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        body = str(claim.get("claim") or claim.get("text") or "").strip()
        if not body:
            continue
        has_anchor = bool(
            claim.get("approx_time_range")
            or (claim.get("segment_ids") or claim.get("evidence_segment_ids"))
        )
        if has_anchor:
            continue
        topic_range = default_range
        for topic in topics:
            if not isinstance(topic, dict):
                continue
            tname = str(topic.get("name", "")).lower()
            if tname and tname in body.lower() and topic.get("approx_time_range"):
                topic_range = str(topic["approx_time_range"])
                break
        if not topic_range:
            continue
        claim["approx_time_range"] = topic_range
        claim.setdefault("_provenance", {})
        if isinstance(claim["_provenance"], dict):
            claim["_provenance"].update(
                {
                    "source": "deterministic_gap_fill",
                    "filled_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        generated.append(
            {
                "path": f"key_claims[{i}].approx_time_range",
                "source": "deterministic_gap_fill",
                "value": topic_range,
                "provenance": claim.get("_provenance"),
            }
        )
    out["key_claims"] = claims
    return out, generated


def _build_gap_fill_context(ctx: Any, stage_key: str) -> str:
    parts: list[str] = []
    if ctx.artifact_exists("transcript/full.json"):
        doc = ctx.read_json("transcript/full.json")
        text = str(doc.get("text") or "") if isinstance(doc, dict) else ""
        parts.append(f"transcript_excerpt: {text[:2000]}")
    if ctx.artifact_exists("understanding/speakers.json"):
        parts.append(f"speakers: {json.dumps(ctx.read_json('understanding/speakers.json'), default=str)[:800]}")
    parts.append(f"stage: {stage_key}")
    return "\n".join(parts)


def fill_artifact_gaps(
    ctx: Any,
    stage_key: str,
    artifact_path: str,
    artifacts: dict[str, Any],
    prior_report: ResilienceReport,
) -> tuple[dict[str, Any], ResilienceReport]:
    report = ResilienceReport(
        stage_key=stage_key,
        artifact_path=artifact_path,
        stripped=prior_report.stripped,
        kept_paths=prior_report.kept_paths,
        lint_errors_before=prior_report.lint_errors_before,
    )
    out, det_generated = _deterministic_claim_time_fill(artifacts)
    report.generated.extend(det_generated)

    gaps = list_fill_if_missing_gaps(stage_key, artifact_path, out)
    if not gaps:
        report.summary = f"Gap-fill: {len(det_generated)} deterministic field(s)"
        return out, report

    try:
        system = load_system_prompt("_shared/local-gap-fill.system.txt", include_preamble=False)
        user = (
            f"Fill these JSON paths in the artifact: {gaps[:8]}\n\n"
            f"Current artifact excerpt:\n{json.dumps(out, default=str)[:1500]}\n\n"
            f"{_build_gap_fill_context(ctx, stage_key)}"
        )
        raw, meta = generate_local_chat(system=system, user=user, ctx=ctx, stage_key=stage_key)
        parsed = json.loads(raw) if raw.strip().startswith("{") else {}
        if isinstance(parsed, dict):
            for key, val in parsed.items():
                if key == "key_claims" and isinstance(val, list):
                    out["key_claims"] = val
                elif key in out:
                    out[key] = val
                report.generated.append(
                    {
                        "path": key,
                        "source": "local_gap_fill",
                        "model_id": meta.get("model_id"),
                        "local_llm_raw": raw[:2000],
                        "value": _cap(val),
                        "provenance": {
                            "source": "local_gap_fill",
                            "filled_at": datetime.now(timezone.utc).isoformat(),
                        },
                    }
                )
    except (LocalLlmUnavailable, json.JSONDecodeError, Exception) as exc:
        ctx.log(
            f"Local gap-fill skipped for {stage_key}: {exc}",
            level="warning",
            stage=stage_key,
        )

    report.summary = (
        f"Gap-fill: {len(report.generated)} field(s) "
        f"({len(det_generated)} deterministic, {len(report.generated) - len(det_generated)} local)"
    )
    return out, report


def _cap(val: Any) -> Any:
    text = json.dumps(val, default=str) if not isinstance(val, str) else val
    return text[:500] + "…" if len(text) > 500 else val
