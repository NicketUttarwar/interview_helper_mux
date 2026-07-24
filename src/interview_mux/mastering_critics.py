"""L4 multi-critic panel plumbing: fan-out, evidence packets, arbiter merge.

Spec: docs/cross-cutting/mastering-multi-critic.md
Schemas: mastering_critic_report.schema.json, mastering_cross_critique.schema.json
Artifact: mastering/shape/cross_critique.json

The LLM calls themselves land with the Shape Engine runtime; this module owns the
deterministic half — which critics run, what each one is shown, and how a panel
is merged when the arbiter is unavailable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.mastering_context_compiler import compile_packet, make_item
from interview_mux.mastering_hardening_config import gate_cfg, gate_mode
from interview_mux.run_context import RunContext

CROSS_CRITIQUE_ARTIFACT = "mastering/shape/cross_critique.json"
CRITIC_REPORT_DIR = "mastering/shape/critics"

ALL_CRITICS: tuple[str, ...] = (
    "narrative_editor",
    "engagement_listener",
    "audio_intelligibility",
    "integrity",
    "pacing_repetition",
    "style_fit",
)

# Only integrity may remove a candidate on its own authority.
BLOCKING_CRITICS: frozenset[str] = frozenset({"integrity"})

CRITIC_PROMPTS: dict[str, str] = {
    "narrative_editor": "mastering/critics/narrative-editor.system.txt",
    "engagement_listener": "mastering/critics/engagement-listener.system.txt",
    "audio_intelligibility": "mastering/critics/audio-intelligibility.system.txt",
    "integrity": "mastering/critics/integrity.system.txt",
    "pacing_repetition": "mastering/critics/pacing-repetition.system.txt",
    "style_fit": "mastering/critics/style-fit.system.txt",
}
ARBITER_PROMPT = "mastering/critics/l4-arbiter.system.txt"

# Evidence each critic actually needs; keeps packets small and lanes separate.
_CRITIC_EVIDENCE: dict[str, tuple[str, ...]] = {
    "narrative_editor": ("candidates", "dossier", "rubric"),
    "engagement_listener": ("candidates", "auditions", "rubric"),
    "audio_intelligibility": ("candidates", "auditions"),
    "integrity": ("candidates", "semantic_integrity", "claims"),
    "pacing_repetition": ("candidates", "auditions"),
    "style_fit": ("candidates", "rubric", "dossier"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def enabled_critics(cfg: dict[str, Any] | None = None) -> list[str]:
    conf = gate_cfg("critics", cfg)
    requested = [str(c) for c in (conf.get("enabled_critics") or ALL_CRITICS)]
    return [c for c in ALL_CRITICS if c in requested]


def critic_report_rel(critic_id: str) -> str:
    return f"{CRITIC_REPORT_DIR}/{critic_id}.json"


def build_critic_packets(
    *,
    candidates: list[dict[str, Any]],
    rubric: dict[str, Any] | None = None,
    auditions: dict[str, dict[str, Any]] | None = None,
    semantic_integrity: dict[str, Any] | None = None,
    dossier_refs: list[str] | None = None,
    claim_refs: list[str] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """One evidence packet per critic, carrying only that critic's lane."""
    packets: dict[str, dict[str, Any]] = {}
    for critic_id in enabled_critics(cfg):
        needs = _CRITIC_EVIDENCE.get(critic_id, ("candidates",))
        items: list[dict[str, Any]] = []
        if "candidates" in needs:
            for cand in candidates:
                items.append(
                    make_item(
                        ref=f"mastering/shape/candidates.json#{cand.get('candidate_id')}",
                        kind="artifact",
                        salience=1.0,
                        inline=cand,
                    )
                )
        if "rubric" in needs and rubric:
            items.append(
                make_item(
                    ref="mastering/shape/eval_rubric.json",
                    kind="artifact",
                    salience=0.95,
                    inline=rubric,
                )
            )
        if "auditions" in needs and auditions:
            for cid, manifest in auditions.items():
                items.append(
                    make_item(
                        ref=f"mastering/auditions/{cid}/manifest.json",
                        kind="artifact",
                        salience=0.9,
                        inline=manifest,
                    )
                )
        if "semantic_integrity" in needs and semantic_integrity:
            items.append(
                make_item(
                    ref="mastering/shape/semantic_integrity.json",
                    kind="artifact",
                    salience=1.0,
                    inline=semantic_integrity,
                )
            )
        for ref in (dossier_refs or []) if "dossier" in needs else []:
            items.append(make_item(ref=ref, kind="artifact", salience=0.5))
        for ref in (claim_refs or []) if "claims" in needs else []:
            items.append(make_item(ref=ref, kind="artifact", salience=0.8))

        packets[critic_id] = compile_packet(
            consumer_id=f"critic_{critic_id}",
            consumer_kind="critic",
            items=items,
            cfg=cfg,
        )
    return packets


def validate_critic_report(report: dict[str, Any]) -> list[str]:
    """Contract checks the schema cannot express."""
    errors: list[str] = []
    critic_id = str(report.get("critic_id") or "")
    if critic_id not in ALL_CRITICS:
        errors.append(f"unknown critic_id: {critic_id!r}")
    for review in report.get("candidate_reviews") or []:
        cid = review.get("candidate_id")
        if review.get("blocking") and critic_id not in BLOCKING_CRITICS:
            errors.append(f"{critic_id} set blocking on {cid} but only integrity may block")
        if review.get("blocking") and not (review.get("evidence_refs") or []):
            errors.append(f"{critic_id} blocked {cid} without evidence_refs")
        if not review.get("scores"):
            errors.append(f"{critic_id} returned no scores for {cid}")
    return errors


def merge_panel(
    reports: list[dict[str, Any]],
    *,
    candidate_ids: list[str],
    rubric: dict[str, Any] | None = None,
    arbiter_rationale: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministic panel merge — the fallback when the flagship arbiter is unavailable.

    Weighting follows the per-run rubric so a critic agreeing on a low-weight
    criterion cannot outvote a single critic on a decisive one.
    """
    weights = _rubric_weights(rubric)
    kills = _integrity_kills(reports)

    survivors: list[dict[str, Any]] = []
    for cid in candidate_ids:
        if cid in kills:
            continue
        dimension_scores = _dimension_scores(reports, cid)
        survivors.append(
            {
                "candidate_id": cid,
                "rank": 0,
                "dimension_scores": dimension_scores,
                "aggregate_score": _weighted(dimension_scores, weights),
                "strengths": _collect(reports, cid, "strengths"),
                "weaknesses": _collect(reports, cid, "issues"),
                "evidence_refs": _collect(reports, cid, "evidence_refs"),
            }
        )

    survivors.sort(key=lambda s: -(s["aggregate_score"] or 0.0))
    for i, survivor in enumerate(survivors, start=1):
        survivor["rank"] = i

    return {
        "version": 1,
        "mode": gate_mode("critics", cfg),
        "rubric_ref": "mastering/shape/eval_rubric.json" if rubric else None,
        "critic_reports": reports,
        "critics_run": [str(r.get("critic_id")) for r in reports],
        "ranked_survivors": survivors,
        "killed": [
            {"candidate_id": cid, "reason": reason, "killed_by": "integrity", "hard_fail": True}
            for cid, reason in kills.items()
        ],
        "deepen_directives": _deepen_directives(reports, candidate_ids, cfg=cfg),
        "disagreements": _disagreements(reports, candidate_ids),
        "arbiter_rationale": arbiter_rationale
        or "Deterministic panel merge (no flagship arbiter in this run).",
        "generated_at": _now(),
    }


def _rubric_weights(rubric: dict[str, Any] | None) -> dict[str, float]:
    weights: dict[str, float] = {}
    for criterion in (rubric or {}).get("criteria") or []:
        if isinstance(criterion, dict) and criterion.get("criterion_id"):
            try:
                weights[str(criterion["criterion_id"])] = float(criterion.get("weight") or 0.0)
            except (TypeError, ValueError):
                continue
    return weights


def _reviews(reports: list[dict[str, Any]], candidate_id: str):
    for report in reports:
        for review in report.get("candidate_reviews") or []:
            if str(review.get("candidate_id")) == candidate_id:
                yield report, review


def _integrity_kills(reports: list[dict[str, Any]]) -> dict[str, str]:
    kills: dict[str, str] = {}
    for report in reports:
        if str(report.get("critic_id")) not in BLOCKING_CRITICS:
            continue
        for review in report.get("candidate_reviews") or []:
            if review.get("blocking") or review.get("verdict") == "kill":
                issues = review.get("issues") or ["integrity violation"]
                kills[str(review.get("candidate_id"))] = "; ".join(str(i) for i in issues)
    return kills


def _dimension_scores(reports: list[dict[str, Any]], candidate_id: str) -> dict[str, float]:
    """Average each dimension across the critics that scored it."""
    totals: dict[str, list[float]] = {}
    for _, review in _reviews(reports, candidate_id):
        for dim, value in (review.get("scores") or {}).items():
            try:
                totals.setdefault(str(dim), []).append(float(value))
            except (TypeError, ValueError):
                continue
    return {dim: round(sum(vals) / len(vals), 4) for dim, vals in totals.items() if vals}


def _weighted(scores: dict[str, float], weights: dict[str, float]) -> float | None:
    if not scores:
        return None
    if not weights:
        return round(sum(scores.values()) / len(scores), 4)
    total_weight = sum(weights.get(dim, 0.0) for dim in scores)
    if total_weight <= 0:
        return round(sum(scores.values()) / len(scores), 4)
    weighted = sum(value * weights.get(dim, 0.0) for dim, value in scores.items())
    return round(weighted / total_weight, 4)


def _collect(reports: list[dict[str, Any]], candidate_id: str, key: str) -> list[str]:
    out: list[str] = []
    for _, review in _reviews(reports, candidate_id):
        out.extend(str(v) for v in (review.get(key) or []))
    return list(dict.fromkeys(out))


def _disagreements(
    reports: list[dict[str, Any]], candidate_ids: list[str]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cid in candidate_ids:
        verdicts = {str(r.get("verdict")) for _, r in _reviews(reports, cid)}
        if "promote" in verdicts and ("demote" in verdicts or "kill" in verdicts):
            confidences = [float(r.get("confidence") or 0.0) for _, r in _reviews(reports, cid)]
            low = all(c < 0.6 for c in confidences) if confidences else False
            out.append(
                {
                    "candidate_id": cid,
                    "detail": f"panel split: {', '.join(sorted(verdicts))}",
                    "resolution": "deepen" if low else "kept_both",
                }
            )
    return out


def _deepen_directives(
    reports: list[dict[str, Any]], candidate_ids: list[str], *, cfg: dict[str, Any] | None
) -> list[dict[str, Any]]:
    conf = gate_cfg("critics", cfg)
    budget = int(conf.get("max_deepen_rounds") or 1)
    directives: list[dict[str, Any]] = []
    for row in _disagreements(reports, candidate_ids):
        if len(directives) >= budget:
            break
        if row["resolution"] != "deepen":
            continue
        directives.append(
            {
                "candidate_id": row["candidate_id"],
                "directive": f"Panel split with low confidence — {row['detail']}; resolve with a deeper pass",
                "target_level": "L3",
            }
        )
    return directives


def write_cross_critique(ctx: RunContext, doc: dict[str, Any]) -> None:
    ctx.write_json(CROSS_CRITIQUE_ARTIFACT, doc)


def write_critic_report(ctx: RunContext, report: dict[str, Any]) -> None:
    ctx.write_json(critic_report_rel(str(report["critic_id"])), report)


def survivors_for_pareto(cross_critique: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"candidate_id": s.get("candidate_id"), "dimension_scores": s.get("dimension_scores") or {}}
        for s in (cross_critique.get("ranked_survivors") or [])
    ]
