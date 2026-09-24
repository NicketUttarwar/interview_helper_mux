from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.analysis_memory import load_analysis_state, update_completion_from_analysis
from interview_mux.llm_specialists import (
    load_comprehension_risks,
    maybe_run_pre_stage_specialists,
)
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.stage_enrichment import compact_manifest_for_volley, compact_value_features_summary
from interview_mux.source_topology import attach_adaptation_to_payload, pickup_eligible_speaker_id
from interview_mux.production_profile import prompt_variant
from interview_mux.artifact_completeness import make_stage_persist
from interview_mux.stages.analysis_stage import run_analysis_llm_stage, sync_gaps_to_state
from interview_mux.stage_completion import heal_or_raise, heal_or_refuse_mark


def _compact_segments_payload(
    c: RunContext,
    *,
    segment_ids: list[str] | None = None,
) -> dict[str, Any]:
    from interview_mux.transcript_shards import segment_text_max_chars

    manifest = c.read_json("segments/manifest.json") if c.artifact_exists("segments/manifest.json") else {}
    if not isinstance(manifest, dict):
        manifest = {}
    if segment_ids is not None:
        want = {str(x) for x in segment_ids}
        rows = [
            s
            for s in (manifest.get("segments") or [])
            if isinstance(s, dict) and str(s.get("segment_id") or "") in want
        ]
        manifest = {**manifest, "segments": rows}
    return compact_manifest_for_volley(manifest, text_max=segment_text_max_chars())


def _gap_segment_ids(ctx: RunContext) -> list[str]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return []
    man = ctx.read_json("segments/manifest.json")
    if not isinstance(man, dict):
        return []
    return [
        str(s.get("segment_id"))
        for s in (man.get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    ]


def _gap_pass_batch_size(cfg: dict[str, Any] | None = None) -> int:
    from interview_mux.transcript_shards import analysis_context_cfg

    ctx_cfg = analysis_context_cfg(cfg)
    # Prefer explicit gap batch size; fall back to classification shard size.
    raw = ctx_cfg.get("proactive_decompose_gap_segments")
    if raw is None:
        raw = ctx_cfg.get("max_segments_in_gap_pass") or ctx_cfg.get("per_segment_shard_max") or 40
    return max(1, int(raw))


_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}


def _gap_eval_severity_rank(row: dict[str, Any] | None) -> int:
    if not isinstance(row, dict):
        return 0
    return int(_SEVERITY_RANK.get(str(row.get("severity") or "").strip().lower(), 0))


def _merge_gap_evaluations(parts: list[dict[str, Any]], required_ids: list[str]) -> dict[str, Any]:
    """Merge shard envelopes by segment_id — prefer scored rows; severity breaks ties.

    Last-write-wins used to let a sparse later shard overwrite a good earlier score
    (ASSETS-informed). Scored keep-eligible rows beat thinner rows. When both are
    scored, prefer the higher severity; equal severity → newer wins.
    """
    by_id: dict[str, dict[str, Any]] = {}
    for part in parts:
        if not isinstance(part, dict):
            continue
        for row in part.get("evaluations") or []:
            if not isinstance(row, dict) or not row.get("segment_id"):
                continue
            sid = str(row["segment_id"])
            existing = by_id.get(sid)
            if existing is None:
                by_id[sid] = row
                continue
            existing_scored = _gap_eval_row_is_keep_scored(existing)
            incoming_scored = _gap_eval_row_is_keep_scored(row)
            if existing_scored and not incoming_scored:
                continue
            if existing_scored and incoming_scored:
                if _gap_eval_severity_rank(row) < _gap_eval_severity_rank(existing):
                    continue
            by_id[sid] = row
    ordered = [by_id[sid] for sid in required_ids if sid in by_id]
    for sid, row in by_id.items():
        if sid not in {str(r.get("segment_id")) for r in ordered}:
            ordered.append(row)
    return {"evaluations": ordered}


def _gap_eval_row_is_keep_scored(row: dict[str, Any]) -> bool:
    """True when a row has severity+gap_type and is not an unscored fill/seal placeholder."""
    if not isinstance(row, dict):
        return False
    producer = str((row.get("_meta") or {}).get("producer") or "")
    if producer == "gap_fill_skip":
        return True
    if _gap_eval_is_unscored_fill(row):
        return False
    return bool(row.get("severity") and row.get("gap_type"))


def _full_keep_eligible_seal_fields(sid: str) -> dict[str, Any]:
    """Full keep-eligible field set for CAP seals / fabricate (OpenAI envelope parity)."""
    return {
        "segment_id": sid,
        "self_explanatory": True,
        "gap_type": "ok_with_light_bridge",
        "secondary_gap_type": None,
        "severity": "low",
        "listener_confusion": "",
        "recommended_framing": "none",
        "candidate_for_summary": False,
        "supports_ranking_exclude": False,
        "duplicate_claim_cluster": "",
    }


def _ensure_keep_eligible_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Fill missing keep-eligible fields without clobbering LLM-scored values."""
    out = dict(row)
    if out.get("gap_type") in (None, ""):
        out["gap_type"] = "ok_with_light_bridge"
    if "secondary_gap_type" not in out:
        out["secondary_gap_type"] = None
    if out.get("severity") in (None, ""):
        out["severity"] = "low"
    if out.get("listener_confusion") is None:
        out["listener_confusion"] = ""
    elif not isinstance(out.get("listener_confusion"), str):
        out["listener_confusion"] = str(out.get("listener_confusion") or "")
    if out.get("recommended_framing") in (None, ""):
        out["recommended_framing"] = "none"
    if "candidate_for_summary" not in out or out.get("candidate_for_summary") is None:
        out["candidate_for_summary"] = False
    if "supports_ranking_exclude" not in out or out.get("supports_ranking_exclude") is None:
        out["supports_ranking_exclude"] = False
    if out.get("duplicate_claim_cluster") is None:
        out["duplicate_claim_cluster"] = ""
    return out


_BLOCKING_RERUN_STAGES = frozenset(
    {
        "speaker_roles",
        "boundary_detection",
        "boundary_topic_resplit",
        "transcript_review_build",
        "segment_classification",
    }
)


def _blocking_rerun_stage_from_needs(needs: Any) -> str | None:
    """Return upstream stage to pin when LLM asks for a blocking rerun_stage need."""
    if not isinstance(needs, list):
        return None
    for need in needs:
        if not isinstance(need, dict):
            continue
        if need.get("blocking") is False:
            continue
        ntype = str(need.get("type") or need.get("kind") or "").strip()
        if ntype and ntype not in {"rerun_stage", "needs_input"}:
            continue
        stage = str(
            need.get("stage")
            or need.get("rerun_stage")
            or (need.get("suggested_action") or {}).get("stage")
            or ""
        ).strip()
        if stage in _BLOCKING_RERUN_STAGES:
            return stage
    return None


def _proxy_risk_candidates(ctx: RunContext) -> list[tuple[str, str, float]]:
    """Ranked proxy risk candidates: (segment_id, source, priority).

    Used when specialists are thin/empty so sealed_vs_risk / wrong-keep revisit
    still protect chapter opens, talking-point anchors, and topic boundaries.
    """
    ranked: list[tuple[str, str, float]] = []

    def _push(sid: str, source: str, priority: float) -> None:
        s = str(sid or "").strip()
        if s:
            ranked.append((s, source, float(priority)))

    try:
        if ctx.artifact_exists("understanding/episode_structure.json"):
            doc = ctx.read_json("understanding/episode_structure.json")
            if isinstance(doc, dict):
                for i, ch in enumerate(doc.get("chapters") or []):
                    if not isinstance(ch, dict):
                        continue
                    # Chapter opens matter most for framing VO.
                    pri = 1.0 - min(0.4, 0.02 * i)
                    for key in (
                        "first_segment_id",
                        "start_segment_id",
                        "opening_segment_id",
                        "segment_id",
                    ):
                        _push(str(ch.get(key) or ""), "proxy_chapter", pri)
                    segs = [str(s) for s in (ch.get("segment_ids") or []) if s]
                    if segs:
                        _push(segs[0], "proxy_chapter", pri)
    except Exception:
        pass
    try:
        if ctx.artifact_exists("understanding/talking_points.json"):
            doc = ctx.read_json("understanding/talking_points.json")
            rows: list[Any] = []
            if isinstance(doc, dict):
                rows = list(doc.get("talking_points") or doc.get("points") or [])
            elif isinstance(doc, list):
                rows = doc
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sid = str(
                    row.get("segment_id")
                    or row.get("anchor_segment_id")
                    or row.get("before_target")
                    or ""
                ).strip()
                if not sid:
                    continue
                imp = row.get("importance")
                try:
                    score = float(imp) if imp is not None else 0.5
                except (TypeError, ValueError):
                    score = 0.5
                _push(sid, "proxy_talking_point", 0.7 + 0.3 * max(0.0, min(1.0, score)))
    except Exception:
        pass
    try:
        if ctx.artifact_exists("understanding/content_brief.json"):
            doc = ctx.read_json("understanding/content_brief.json")
            topics = doc.get("topics") if isinstance(doc, dict) else None
            if isinstance(topics, list):
                for i, topic in enumerate(topics):
                    if not isinstance(topic, dict):
                        continue
                    segs = topic.get("segment_ids") or []
                    if isinstance(segs, list) and segs:
                        _push(str(segs[0]), "proxy_brief_topic", 0.55 - min(0.2, 0.02 * i))
    except Exception:
        pass
    try:
        if ctx.artifact_exists("segments/boundaries.json"):
            doc = ctx.read_json("segments/boundaries.json")
            bounds = doc.get("boundaries") if isinstance(doc, dict) else None
            if isinstance(bounds, list):
                for b in bounds:
                    if not isinstance(b, dict):
                        continue
                    kind = str(b.get("kind") or b.get("boundary_type") or "").lower()
                    if kind and "chapter" not in kind and kind not in {
                        "topic",
                        "major",
                        "act",
                    }:
                        continue
                    _push(
                        str(b.get("segment_id") or b.get("after_segment_id") or ""),
                        "proxy_boundary",
                        0.5,
                    )
    except Exception:
        pass
    ranked.sort(key=lambda t: (-t[2], t[0]))
    return ranked


def resolve_framing_risk_segment_ids(
    ctx: RunContext,
    *,
    required_ids: list[str] | None = None,
    proxy_cap: int = 16,
) -> dict[str, Any]:
    """Complete framing-risk authority for sealed_vs_risk / wrong-keep revisit.

    - Always prefer specialist comprehension_risks when present.
    - Union with structural proxies (never risk-blind when specialists fail-open).
    - Intersect with live required gap segment ids (no orphan chase).
    - Preserve provenance for coverage_report / forensics.
    """
    live = set(required_ids if required_ids is not None else _gap_segment_ids(ctx))
    sources: dict[str, str] = {}
    specialist_ids: list[str] = []
    try:
        from interview_mux.llm_specialists import load_comprehension_risks

        risks = load_comprehension_risks(ctx, "missing_framing")
    except Exception:
        risks = []
    for row in risks or []:
        if not isinstance(row, dict):
            continue
        found: list[str] = []
        for key in ("segment_id", "seg_id", "target_segment_id", "before_target"):
            sid = str(row.get(key) or "").strip()
            if sid:
                found.append(sid)
        for sid in row.get("segment_ids") or []:
            s = str(sid or "").strip()
            if s:
                found.append(s)
        for sid in found:
            if live and sid not in live:
                continue
            if sid not in sources:
                sources[sid] = "specialist"
                specialist_ids.append(sid)

    proxy_ids: list[str] = []
    for sid, source, _pri in _proxy_risk_candidates(ctx):
        if live and sid not in live:
            continue
        if sid in sources:
            continue
        if len(proxy_ids) >= max(0, int(proxy_cap)):
            break
        sources[sid] = source
        proxy_ids.append(sid)

    ordered = specialist_ids + proxy_ids
    return {
        "ids": set(ordered),
        "ordered_ids": ordered,
        "sources": sources,
        "specialist_count": len(specialist_ids),
        "proxy_count": len(proxy_ids),
        "mode": (
            "specialist+proxy"
            if specialist_ids and proxy_ids
            else ("specialist" if specialist_ids else ("proxy" if proxy_ids else "empty"))
        ),
    }


def _comprehension_risk_segment_ids(ctx: RunContext) -> set[str]:
    return set(resolve_framing_risk_segment_ids(ctx).get("ids") or set())


def _sealed_vs_risk_ids(ctx: RunContext, doc: dict[str, Any]) -> list[str]:
    """Sealed-as-low ids that contradict framing-risk authority (specialist ∪ proxy).

    When a segment has both a coverage seal and a real scored row, prefer the
    scored row — duplicate seal leftovers must not thrash sealed_vs_risk
    (exec_13181 seg_067/068/070).
    """
    risk_ids = set(resolve_framing_risk_segment_ids(ctx).get("ids") or set())
    if not risk_ids:
        return []
    by_sid: dict[str, list[dict[str, Any]]] = {}
    for row in doc.get("evaluations") or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("segment_id") or "")
        if not sid or sid not in risk_ids:
            continue
        by_sid.setdefault(sid, []).append(row)
    hit: list[str] = []
    for sid, rows in by_sid.items():
        has_scored = any(
            not _gap_eval_is_coverage_seal(row)
            and not _gap_eval_is_unscored_fill(row)
            and str(row.get("severity") or "").strip()
            for row in rows
        )
        if has_scored:
            continue
        if any(
            _gap_eval_is_coverage_seal(row)
            and str(row.get("severity") or "low").lower() == "low"
            for row in rows
        ):
            hit.append(sid)
    return hit


def _wrong_keep_revisit_ids(
    ctx: RunContext, rows: list[Any], required_ids: list[str]
) -> list[str]:
    """Wrong-but-scored keep rows: low severity on *specialist* risk ids.

    Proxy structural anchors (chapters / talking points) must not force revisit of
    honest low ``ok_with_light_bridge`` scores — that blew leftover sets and made
    coverage passes look proactive-empty. Proxies still feed sealed_vs_risk.
    """
    risk = resolve_framing_risk_segment_ids(ctx, required_ids=required_ids)
    specialist_ids = {
        sid
        for sid, src in (risk.get("sources") or {}).items()
        if str(src) == "specialist"
    }
    if not specialist_ids:
        return []
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("segment_id"):
            by_id[str(row["segment_id"])] = row
    out: list[str] = []
    for sid in required_ids:
        if sid not in specialist_ids:
            continue
        row = by_id.get(sid)
        if row is None:
            continue
        meta = row.get("_meta") if isinstance(row.get("_meta"), dict) else {}
        if meta.get("risk_revisit_done") or meta.get("producer") == "gap_fill_skip":
            continue
        if _gap_eval_is_unscored_fill(row) or _gap_eval_is_coverage_seal(row):
            continue
        if str(row.get("severity") or "").lower() == "low":
            out.append(sid)
    return out



def _stamp_risk_revisit_done(merged: dict[str, Any], ids: list[str]) -> dict[str, Any]:
    want = {str(s) for s in ids if s}
    if not want:
        return merged
    rows: list[dict[str, Any]] = []
    for row in merged.get("evaluations") or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("segment_id") or "")
        if sid not in want:
            rows.append(row)
            continue
        out = dict(row)
        meta = dict(out.get("_meta") or {})
        meta["risk_revisit_done"] = True
        out["_meta"] = meta
        rows.append(out)
    out_doc = dict(merged)
    out_doc["evaluations"] = rows
    return out_doc


MISSING_FRAMING_COVERAGE_CAP = 2
MISSING_FRAMING_COVERAGE_REPORT_REL = (
    "understanding/stage_runs/missing_framing/coverage_report.json"
)
# ASSETS 13159–13170: sealed 20–45% after CAP=2. Above this ratio we force one
# bounded rescue micro-volley before accepting seals as terminal.
_DEFAULT_SEALED_RATIO_MAX = 0.15
_DEFAULT_SEALED_RATIO_RESCUE_MAX_IDS = 32


def _gap_eval_filled_by(row: dict[str, Any]) -> str:
    return str((row.get("_meta") or {}).get("filled_by") or "")


def _gap_eval_is_coverage_seal(row: dict[str, Any]) -> bool:
    """True when row is a post-CAP coverage_exhausted_accept seal."""
    meta = row.get("_meta") if isinstance(row, dict) else None
    if not isinstance(meta, dict):
        return False
    if str(meta.get("filled_by") or "") == "coverage_exhausted_accept":
        return True
    return str(meta.get("reason") or "") == "coverage_cap_seal"


def _missing_framing_gap_fill_cfg() -> dict[str, Any]:
    from interview_mux.config import merged_config

    root = merged_config()
    analysis = root.get("analysis") if isinstance(root.get("analysis"), dict) else {}
    raw = analysis.get("gap_fill") if isinstance(analysis.get("gap_fill"), dict) else {}
    return dict(raw)


def _sealed_ratio_max() -> float:
    raw = _missing_framing_gap_fill_cfg().get("sealed_ratio_max")
    if raw is None:
        return _DEFAULT_SEALED_RATIO_MAX
    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return _DEFAULT_SEALED_RATIO_MAX


def _sealed_ratio_hard_max() -> float:
    """After one rescue, ratios above this are operator-STOP (not auto-accepted)."""
    raw = _missing_framing_gap_fill_cfg().get("sealed_ratio_hard_max")
    try:
        val = float(raw) if raw is not None else 0.35
    except (TypeError, ValueError):
        val = 0.35
    return max(0.0, min(1.0, val))


def _sealed_ratio_rescue_max_ids() -> int:
    raw = _missing_framing_gap_fill_cfg().get("sealed_ratio_rescue_max_ids")
    if raw is None:
        return _DEFAULT_SEALED_RATIO_RESCUE_MAX_IDS
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return _DEFAULT_SEALED_RATIO_RESCUE_MAX_IDS


def _shard_envelope_has_evaluations(arts: Any) -> bool:
    """True when a shard envelope carries at least one segment evaluation row."""
    if not isinstance(arts, dict):
        return False
    evals = arts.get("evaluations")
    if not isinstance(evals, list):
        return False
    return any(
        isinstance(row, dict) and str(row.get("segment_id") or "").strip() for row in evals
    )


def _coverage_stats_from_doc(
    doc: dict[str, Any],
    required_ids: list[str],
) -> dict[str, Any]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in doc.get("evaluations") or []:
        if isinstance(row, dict) and row.get("segment_id"):
            by_id[str(row["segment_id"])] = row
    sealed_ids: list[str] = []
    batch_fill_ids: list[str] = []
    scored_ids: list[str] = []
    missing_ids: list[str] = []
    for sid in required_ids:
        row = by_id.get(sid)
        if row is None:
            missing_ids.append(sid)
            continue
        producer = str((row.get("_meta") or {}).get("producer") or "")
        if producer == "gap_fill_skip":
            scored_ids.append(sid)
            continue
        if _gap_eval_is_unscored_fill(row):
            batch_fill_ids.append(sid)
            continue
        if _gap_eval_is_coverage_seal(row):
            sealed_ids.append(sid)
            continue
        scored_ids.append(sid)
    required_n = len(required_ids)
    sealed_n = len(sealed_ids)
    sealed_ratio = (float(sealed_n) / float(required_n)) if required_n else 0.0
    return {
        "required_count": required_n,
        "scored_count": len(scored_ids),
        "batch_fill_count": len(batch_fill_ids),
        "sealed_count": sealed_n,
        "missing_count": len(missing_ids),
        "sealed_ratio": round(sealed_ratio, 4),
        "sealed_ids": sealed_ids,
        "batch_fill_ids": batch_fill_ids[:24],
        "missing_ids": missing_ids[:24],
        "coverage_passes": _coverage_pass_count(doc),
        "sealed_ratio_max": _sealed_ratio_max(),
        "sealed_ratio_hard_max": _sealed_ratio_hard_max(),
        "sealed_ratio_rescue_done": bool(
            (doc.get("_meta") or {}).get("sealed_ratio_rescue_done")
        ),
    }


def _selection_critical_ids(ctx: RunContext, candidate_ids: list[str]) -> list[str]:
    """Prefer sealed ids that sit on the current selection order, else candidates as-is."""
    want = {str(s) for s in candidate_ids if s}
    if not want:
        return []
    ordered: list[str] = []
    if ctx.artifact_exists("master/selection.json"):
        try:
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                for sid in sel.get("ordered_segment_ids") or []:
                    s = str(sid or "")
                    if s in want and s not in ordered:
                        ordered.append(s)
        except Exception:
            pass
    if ordered:
        return ordered
    return [str(s) for s in candidate_ids if s]


def _pick_sealed_ratio_rescue_ids(
    ctx: RunContext, sealed_ids: list[str], *, max_ids: int | None = None
) -> list[str]:
    cap = max_ids if max_ids is not None else _sealed_ratio_rescue_max_ids()
    critical = _selection_critical_ids(ctx, sealed_ids)
    if not critical:
        critical = list(sealed_ids)
    return critical[: max(1, int(cap))]


def write_missing_framing_coverage_report(
    ctx: RunContext,
    doc: dict[str, Any],
    *,
    required_ids: list[str] | None = None,
    shard_empty_count: int = 0,
    shard_empty_retries: int = 0,
    rescue_attempted: bool = False,
    rescue_ids: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist MF coverage telemetry for forensics + sealed_ratio incompleteness."""
    ids = list(required_ids) if required_ids is not None else _gap_segment_ids(ctx)
    stats = _coverage_stats_from_doc(doc if isinstance(doc, dict) else {}, ids)
    risk = resolve_framing_risk_segment_ids(ctx, required_ids=ids)
    sealed_vs_risk = _sealed_vs_risk_ids(ctx, doc if isinstance(doc, dict) else {})
    risk_hit_sources = {
        sid: str((risk.get("sources") or {}).get(sid) or "unknown")
        for sid in sealed_vs_risk
    }
    report: dict[str, Any] = {
        **stats,
        "shard_empty_count": int(shard_empty_count),
        "shard_empty_retries": int(shard_empty_retries),
        "rescue_attempted": bool(rescue_attempted),
        "rescue_ids": list(rescue_ids or [])[:32],
        "producer_stage": "missing_framing",
        "framing_risk_mode": risk.get("mode"),
        "framing_risk_specialist_count": int(risk.get("specialist_count") or 0),
        "framing_risk_proxy_count": int(risk.get("proxy_count") or 0),
        "framing_risk_ids": list(risk.get("ordered_ids") or [])[:48],
        "framing_risk_sources": {
            sid: str(src)
            for sid, src in list((risk.get("sources") or {}).items())[:48]
        },
        "sealed_vs_risk_ids": sealed_vs_risk[:24],
        "sealed_vs_risk_sources": risk_hit_sources,
    }
    if extra:
        report.update(extra)
    try:
        from interview_mux.write_staging import write_committed_json

        write_committed_json(
            ctx,
            MISSING_FRAMING_COVERAGE_REPORT_REL,
            report,
            stage_key="missing_framing",
        )
    except Exception:
        try:
            ctx.write_json(
                MISSING_FRAMING_COVERAGE_REPORT_REL,
                report,
                skip_handoff=True,
            )
        except Exception:
            pass
    return report


def _stamp_sealed_ratio_rescue_done(merged: dict[str, Any]) -> dict[str, Any]:
    out = dict(merged)
    meta = dict(out.get("_meta") or {})
    meta["sealed_ratio_rescue_done"] = True
    out["_meta"] = meta
    return out


def _unseal_rows_for_rescue(
    merged: dict[str, Any], rescue_ids: list[str]
) -> dict[str, Any]:
    """Drop seal tags on rescue targets so a micro-volley can re-score them."""
    want = {str(s) for s in rescue_ids if s}
    if not want:
        return merged
    rows: list[dict[str, Any]] = []
    for row in merged.get("evaluations") or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("segment_id") or "")
        if sid not in want or not _gap_eval_is_coverage_seal(row):
            rows.append(row)
            continue
        # Omit from merge inputs — treat as missing so the rescue shard owns the id.
        continue
    out = dict(merged)
    out["evaluations"] = rows
    return out


def _gap_eval_is_unscored_fill(row: dict[str, Any]) -> bool:
    """True when a fill tag still means \"LLM must re-score\" (HG-3).

    Schema-only ``repair_gap_evaluations`` / ``default_value`` patches on rows that
    already carry severity+gap_type are keep-eligible (exec_11630: 13 leftovers
    poisoned by repair tags → coverage-cap halt loop). Fabricated / batch_coverage
    fills stay unscored.
    """
    from interview_mux.stage_completion import BATCH_FILL_BY, MISSING_FRAMING_FILL_TAGS

    filled_by = _gap_eval_filled_by(row)
    if filled_by == "coverage_exhausted_accept":
        return False
    if filled_by not in MISSING_FRAMING_FILL_TAGS:
        return False
    if filled_by == BATCH_FILL_BY:
        return True
    reason = str((row.get("_meta") or {}).get("reason") or "")
    if reason in ("fabricate_evaluation", "coverage_cap_seal"):
        # coverage_cap_seal is keep-eligible even if an older repair left the
        # repair_gap_evaluations filled_by tag (exec_13159).
        if reason == "coverage_cap_seal":
            return False
        return True
    if row.get("severity") and row.get("gap_type"):
        return False
    return True


def _missing_framing_fill_row(sid: str) -> dict[str, Any]:
    from interview_mux.stage_completion import BATCH_FILL_BY

    return {
        "segment_id": sid,
        "self_explanatory": True,
        "gap_type": "ok_with_light_bridge",
        "severity": "low",
        "listener_confusion": "",
        "_meta": {
            "filled_by": BATCH_FILL_BY,
            "reason": "llm_sparse_shard_output",
        },
    }


def _coverage_exhausted_accept_row(sid: str) -> dict[str, Any]:
    """Honest post-cap seal — keep-eligible (not MISSING_FRAMING_FILL_TAGS)."""
    row = _full_keep_eligible_seal_fields(sid)
    row["_meta"] = {
        "filled_by": "coverage_exhausted_accept",
        "producer": "coverage_exhausted_accept",
        "reason": "coverage_cap_seal",
    }
    return row


def _seal_coverage_exhausted_leftovers(
    merged: dict[str, Any], leftover_ids: list[str]
) -> dict[str, Any]:
    """Promote leftover/absent ids to keep-eligible rows after the coverage cap."""
    from interview_mux.stage_completion import MISSING_FRAMING_FILL_TAGS

    by_id: dict[str, dict[str, Any]] = {}
    for row in merged.get("evaluations") or []:
        if isinstance(row, dict) and row.get("segment_id"):
            by_id[str(row["segment_id"])] = row
    for sid in leftover_ids:
        if not sid:
            continue
        row = by_id.get(sid)
        if row is None:
            by_id[sid] = _coverage_exhausted_accept_row(sid)
            continue
        if _gap_eval_is_unscored_fill(row) or _gap_eval_filled_by(row) in MISSING_FRAMING_FILL_TAGS:
            sealed = _ensure_keep_eligible_fields(dict(row))
            meta = dict(sealed.get("_meta") or {})
            meta["filled_by"] = "coverage_exhausted_accept"
            meta["producer"] = "coverage_exhausted_accept"
            meta["reason"] = "coverage_cap_seal"
            sealed["_meta"] = meta
            by_id[sid] = sealed
    out = dict(merged)
    out["evaluations"] = list(by_id.values())
    return out


def _existing_gap_evaluations(ctx: RunContext) -> dict[str, Any]:
    rel = "understanding/gap_evaluations.json"
    if not ctx.artifact_exists(rel):
        return {}
    try:
        doc = ctx.read_json(rel)
    except Exception:
        return {}
    return doc if isinstance(doc, dict) else {}


def _split_keep_and_leftover(
    required_ids: list[str],
    existing_rows: list[Any],
    *,
    revisit_ids: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in existing_rows:
        if isinstance(row, dict) and row.get("segment_id"):
            by_id[str(row["segment_id"])] = row
    revisit = {str(s) for s in (revisit_ids or []) if s}
    keep: list[dict[str, Any]] = []
    leftover: list[str] = []
    for sid in required_ids:
        row = by_id.get(sid)
        if row is None:
            leftover.append(sid)
            continue
        producer = str((row.get("_meta") or {}).get("producer") or "")
        if producer == "gap_fill_skip":
            keep.append(row)
            continue
        if _gap_eval_is_unscored_fill(row):
            leftover.append(sid)
            continue
        if sid in revisit:
            leftover.append(sid)
            continue
        keep.append(row)
    return keep, leftover


def _coverage_pass_count(doc: dict[str, Any]) -> int:
    try:
        return int((doc.get("_meta") or {}).get("coverage_passes") or 0)
    except (TypeError, ValueError):
        return 0


def _stamp_coverage_passes(merged: dict[str, Any], count: int) -> dict[str, Any]:
    out = dict(merged)
    meta = dict(out.get("_meta") or {})
    meta["coverage_passes"] = max(0, int(count))
    out["_meta"] = meta
    return out


def _fill_missing_evaluations(
    merged: dict[str, Any],
    missing: list[str],
) -> dict[str, Any]:
    filled = [r for r in (merged.get("evaluations") or []) if isinstance(r, dict)]
    present = {str(r.get("segment_id") or "") for r in filled}
    for sid in missing:
        if sid and sid not in present:
            filled.append(_missing_framing_fill_row(sid))
            present.add(sid)
    out = dict(merged)
    out["evaluations"] = filled
    return out


def ensure_gap_fill_skipped(
    ctx: RunContext,
    *,
    reason: str,
    signals: dict[str, Any] | None = None,
) -> None:
    """Deterministic gap-path skip — valid artifacts, no LLM spend."""
    from interview_mux.artifact_writes import write_validated_artifact
    from interview_mux.gap_fill_eligibility import GAP_FILL_SKIP_REL, persist_gap_fill_mode
    from interview_mux.gap_fill_eligibility import GapFillDecision

    framing_key_set = False
    framing_yes = False
    if ctx.artifact_exists("run_meta.json"):
        meta = ctx.read_json("run_meta.json")
        if isinstance(meta, dict) and "gap_framing_enabled" in meta:
            framing_key_set = True
            framing_yes = bool(meta.get("gap_framing_enabled"))
    skip_signal = str((signals or {}).get("skip_signal") or "")
    if framing_key_set and framing_yes and skip_signal not in {
        "gap_framing_no",
        "operator_skip",
        "true_monologue",
        "topology_skip_class",
        "forced_skipped",
    }:
        ctx.log(
            "Refusing gap-fill skip stub while G-Framing is Yes",
            level="warning",
            stage="missing_framing",
            action_id="gap_fill.skip_refused_framing_yes",
            detail={"reason": reason},
        )
        return

    decision = GapFillDecision(eligible=False, reason=reason, signals=dict(signals or {}))
    skip_doc = {
        "status": "skipped",
        "reason": reason,
        "signals": dict(signals or {}),
        "skipped_at": datetime.now(timezone.utc).isoformat(),
        "eligible": False,
    }
    ctx.write_json(GAP_FILL_SKIP_REL, skip_doc, skip_handoff=True)
    persist_gap_fill_mode(ctx, decision, skipped=True)
    try:
        from interview_mux.pipeline_mode import persist_pipeline_mode

        decided_by = "deterministic_monologue"
        if skip_signal in {"gap_framing_no", "operator_skip", "forced_skipped"}:
            decided_by = "operator_g_framing"
        persist_pipeline_mode(
            ctx,
            "native_only",
            decided_by=decided_by,  # type: ignore[arg-type]
            reason_codes=[skip_signal or reason],
        )
    except Exception:
        pass

    segments: list[dict[str, Any]] = []
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        if isinstance(manifest, dict):
            segments = [
                s for s in (manifest.get("segments") or []) if isinstance(s, dict) and s.get("segment_id")
            ]

    evaluations = [
        {
            "segment_id": str(seg.get("segment_id")),
            "self_explanatory": True,
            "gap_type": "ok_with_light_bridge",
            "severity": "low",
            "listener_confusion": "",
        }
        for seg in segments
    ]
    if not evaluations:
        evaluations = [
            {
                "segment_id": "seg_001",
                "self_explanatory": True,
                "gap_type": "ok_with_light_bridge",
                "severity": "low",
                "listener_confusion": "",
            }
        ]

    eval_doc = {
        "evaluations": evaluations,
        "_meta": {"producer": "gap_fill_skip", "producer_stage": "missing_framing"},
    }
    report_doc = {
        "interviewer_lines": [],
        "gaps": [],
        "skipped": True,
        "empty_ok": True,
        "_meta": {
            "producer": "gap_fill_skip",
            "producer_stage": "missing_framing",
            "empty_allowlist": True,
        },
    }

    write_validated_artifact(
        ctx,
        "understanding/gap_evaluations.json",
        eval_doc,
        merge_from_disk=False,
        stage_key="missing_framing",
    )
    # Persist skip outputs on the running stage. Using optimal_questions as
    # stage_key discarded gap_report.json when missing_framing's wrap finished.
    write_validated_artifact(
        ctx,
        "understanding/gap_report.json",
        report_doc,
        merge_from_disk=False,
        stage_key="missing_framing",
    )
    # Do not double-write via bare write_json — that oscillates authority
    # action_class missing_framing↔write_json and trips authority_undo_thrash.
    from interview_mux.gap_framing import commit_interviewer_script

    commit_interviewer_script(
        ctx,
        "# Interviewer script — gap-fill skipped (no pickup lines required)\n",
        stage_key="missing_framing",
    )

    sync_gaps_to_state(ctx, eval_doc)
    update_completion_from_analysis(ctx)

    for stage_id in ("missing_framing", "gap_framing_compose", "optimal_questions"):
        from interview_mux.delivery_guardrails import seed_stage_complete
        if not seed_stage_complete(ctx, stage_id):
            # TH1b allow-stub: gap skip writes complete artifacts → incompleteness empty.
            heal_or_refuse_mark(ctx, stage_id, force=True)

    ctx.log(
        f"Gap-fill skipped: {reason}",
        level="info",
        stage="missing_framing",
        action_id="gap_fill.skip",
        detail={"signals": dict(signals or {})},
    )


def _missing_framing_payload(
    c: RunContext,
    *,
    segment_ids: list[str] | None = None,
    shard_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "segments": _compact_segments_payload(c, segment_ids=segment_ids),
        "content_brief": c.read_json("understanding/content_brief.json"),
    }
    if c.artifact_exists("understanding/talking_points.json"):
        tp = c.read_json("understanding/talking_points.json")
        if isinstance(tp, dict):
            payload["talking_points"] = {
                "strategy_summary": tp.get("strategy_summary"),
                "through_line": tp.get("through_line"),
                "talking_points": [
                    {
                        "talking_point_id": row.get("talking_point_id"),
                        "title": row.get("title"),
                        "importance": row.get("importance"),
                        "why_it_matters": row.get("why_it_matters"),
                    }
                    for row in (tp.get("talking_points") or [])
                    if isinstance(row, dict)
                ][:40],
            }
    risks = load_comprehension_risks(c, "missing_framing")
    if risks:
        payload["comprehension_risks"] = risks
    vf = compact_value_features_summary(c)
    if vf:
        payload["value_features_summary"] = vf
    from interview_mux.interview_spine.compact import attach_spine_to_payload

    attach_spine_to_payload(c, payload, "missing_framing")
    from interview_mux.coherence import attach_coherence_summary

    attach_coherence_summary(payload, c, "missing_framing")
    payload = attach_adaptation_to_payload(c, payload)
    try:
        from interview_mux.mastering_shape_runtime import provisional_mode_for_volley

        nm = provisional_mode_for_volley(c)
        if nm:
            payload["narrative_mode_priors"] = nm
    except Exception:
        pass
    from interview_mux.gap_vo_prior_context import (
        attach_prior_native_contexts_to_payload,
        attach_vo_partner_context_to_payload,
    )

    payload = attach_prior_native_contexts_to_payload(c, payload)
    # Shard payloads: keep prior contexts only for requested segment ids.
    if segment_ids and isinstance(payload.get("prior_native_contexts"), dict):
        want = {str(s) for s in segment_ids}
        payload["prior_native_contexts"] = {
            k: v
            for k, v in payload["prior_native_contexts"].items()
            if str(k) in want
        }
        highlights = payload.get("prior_impact_highlights")
        if isinstance(highlights, list):
            payload["prior_impact_highlights"] = [
                h
                for h in highlights
                if isinstance(h, dict) and str(h.get("before_target") or "") in want
            ][:40]
    payload = attach_vo_partner_context_to_payload(c, payload, segment_ids=segment_ids)
    if shard_meta:
        payload["_gap_eval_shard"] = shard_meta
        seg_ids = list(shard_meta.get("segment_ids") or segment_ids or [])
        payload["_coverage_contract"] = {
            "must_evaluate_all_segment_ids": True,
            "required_segment_ids": seg_ids,
            "omit_is_error": True,
            "sample_forbidden": True,
        }
    return payload


def run_missing_framing(ctx: RunContext) -> None:
    from interview_mux.boundary_enrich import restamp_run_span_speakers
    from interview_mux.llm_simple import run_llm_stage_simple

    restamp_run_span_speakers(ctx)

    persist = make_stage_persist("understanding/gap_evaluations.json", "missing_framing")
    prompt_rel = prompt_variant("interviewer-gap/missing-framing.system.txt", ctx)
    required_ids = _gap_segment_ids(ctx)
    batch_size = _gap_pass_batch_size()
    existing = _existing_gap_evaluations(ctx)
    revisit_ids = _wrong_keep_revisit_ids(
        ctx,
        list(existing.get("evaluations") or []) if existing else [],
        required_ids,
    )
    keep_rows, leftover_ids = _split_keep_and_leftover(
        required_ids,
        list(existing.get("evaluations") or []) if existing else [],
        revisit_ids=revisit_ids,
    )
    prev_passes = _coverage_pass_count(existing)
    leftover_reentry = bool(keep_rows) and bool(leftover_ids)
    target_ids = leftover_ids if leftover_ids else ([] if keep_rows else required_ids)

    def build_input(c: RunContext) -> dict:
        if target_ids:
            return _missing_framing_payload(c, segment_ids=list(target_ids))
        return _missing_framing_payload(c)

    shard_empty_count = 0
    shard_empty_retries = 0
    blocking_rerun_stage: str | None = None

    def _still_unscored(merged: dict[str, Any]) -> list[str]:
        by_id: dict[str, dict[str, Any]] = {}
        for row in merged.get("evaluations") or []:
            if isinstance(row, dict) and row.get("segment_id"):
                by_id[str(row["segment_id"])] = row
        still: list[str] = []
        for sid in required_ids:
            row = by_id.get(sid)
            if row is None:
                still.append(sid)
                continue
            producer = str((row.get("_meta") or {}).get("producer") or "")
            if producer == "gap_fill_skip":
                continue
            if _gap_eval_is_unscored_fill(row):
                still.append(sid)
        return still

    def _run_id_shards(
        ids: list[str],
        *,
        coverage_pass: bool,
        parts: list[dict[str, Any]],
    ) -> None:
        nonlocal shard_empty_count, shard_empty_retries
        if not ids:
            return
        shard_size = max(6, min(batch_size, 12)) if coverage_pass else batch_size
        batches = [ids[i : i + shard_size] for i in range(0, len(ids), shard_size)]
        if not coverage_pass:
            ctx.log(
                f"missing_framing proactive batch: {len(ids)} segments → "
                f"{len(batches)} shard(s) of ≤{shard_size}",
                level="info",
                stage="missing_framing",
                action_id="missing_framing.proactive_batch",
                detail={
                    "required_count": len(required_ids),
                    "target_count": len(ids),
                    "batch_size": shard_size,
                    "batches": len(batches),
                    "leftover_reentry": leftover_reentry,
                },
            )
        for bi, batch_ids in enumerate(batches):

            def build_batch(
                c: RunContext,
                *,
                _ids: list[str] = list(batch_ids),
                _bi: int = bi,
                _total: int = len(batches),
                _cov: bool = coverage_pass,
            ) -> dict:
                return _missing_framing_payload(
                    c,
                    segment_ids=_ids,
                    shard_meta={
                        "index": _bi + 1,
                        "total": _total,
                        "segment_ids": list(_ids),
                        "coverage_pass": _cov,
                    },
                )

            def _invoke_shard(*, attempt: int) -> dict[str, Any]:
                nonlocal blocking_rerun_stage
                ctx.log(
                    f"missing_framing shard {bi + 1}/{len(batches)} "
                    f"({len(batch_ids)} segment ids)"
                    + (f" retry={attempt}" if attempt > 1 else ""),
                    level="action",
                    stage="missing_framing",
                    action_id=(
                        "missing_framing.coverage_pass"
                        if coverage_pass
                        else "missing_framing.shard"
                    ),
                )

                def _noop_persist(_c: RunContext, _artifacts: dict) -> None:
                    return None

                envelope = run_llm_stage_simple(
                    ctx,
                    "missing_framing",
                    prompt_rel,
                    build_batch,
                    _noop_persist,
                    auto_complete=False,
                )
                if not isinstance(envelope, dict):
                    envelope = {}
                status = str(envelope.get("status") or "").strip().lower()
                needs = envelope.get("needs") if isinstance(envelope.get("needs"), list) else []
                pin = _blocking_rerun_stage_from_needs(needs)
                arts_preview = (
                    envelope.get("artifacts")
                    if isinstance(envelope.get("artifacts"), dict)
                    else {}
                )
                scored_ids = {
                    str(r.get("segment_id"))
                    for r in (arts_preview.get("evaluations") or [])
                    if isinstance(r, dict) and r.get("segment_id")
                }
                want_ids = {str(s) for s in batch_ids}
                coverage_ratio = (
                    float(len(scored_ids & want_ids)) / float(len(want_ids))
                    if want_ids
                    else 0.0
                )
                # Soft needs + usable scores: log only. Hard-stop when the shard
                # refused scoring (sparse/empty) or status is blocked/needs_input.
                hard_need = bool(pin) and (
                    status in {"blocked", "needs_input"}
                    or coverage_ratio < 0.5
                    or not scored_ids
                )
                if pin and hard_need:
                    blocking_rerun_stage = blocking_rerun_stage or pin
                    ctx.log(
                        f"missing_framing shard signaled needs.rerun_stage={pin} "
                        f"(hard — coverage {coverage_ratio:.0%})",
                        level="warning",
                        stage="missing_framing",
                        action_id="missing_framing.needs_rerun_stage",
                        detail={
                            "status": status,
                            "needs": needs[:4],
                            "coverage_ratio": round(coverage_ratio, 3),
                        },
                    )
                elif pin:
                    ctx.log(
                        f"missing_framing shard advisory needs.rerun_stage={pin} "
                        f"(soft — coverage {coverage_ratio:.0%}; continue scoring)",
                        level="info",
                        stage="missing_framing",
                        action_id="missing_framing.needs_rerun_advisory",
                        detail={
                            "status": status,
                            "needs": needs[:4],
                            "coverage_ratio": round(coverage_ratio, 3),
                        },
                    )
                arts = arts_preview if isinstance(arts_preview, dict) else {}
                return arts if isinstance(arts, dict) else {}

            arts = _invoke_shard(attempt=1)
            if not _shard_envelope_has_evaluations(arts):
                shard_empty_count += 1
                ctx.log(
                    f"missing_framing empty shard {bi + 1}/{len(batches)} — retrying once "
                    f"(ids={list(batch_ids)[:8]} coverage_pass={coverage_pass})",
                    level="warning",
                    stage="missing_framing",
                    action_id="missing_framing.shard_empty_retry",
                    detail={
                        "shard_index": bi + 1,
                        "shard_total": len(batches),
                        "segment_ids": list(batch_ids),
                        "coverage_pass": coverage_pass,
                    },
                )
                shard_empty_retries += 1
                arts = _invoke_shard(attempt=2)
                if not _shard_envelope_has_evaluations(arts):
                    shard_empty_count += 1
                    if coverage_pass:
                        # Coverage passes exist for sparse LLM output — leave ids
                        # unscored so CAP seal / batch_fill honesty can finish.
                        # Do not append an empty envelope (would look like progress).
                        ctx.log(
                            f"missing_framing coverage shard {bi + 1}/{len(batches)} "
                            "still empty after retry — defer to CAP/batch_fill",
                            level="warning",
                            stage="missing_framing",
                            action_id="missing_framing.shard_empty_coverage_defer",
                            detail={"segment_ids": list(batch_ids)[:12]},
                        )
                        continue
                    raise RuntimeError(
                        "missing_framing empty shard after retry — "
                        f"shard {bi + 1}/{len(batches)} returned no evaluations "
                        f"(segment_ids={list(batch_ids)[:12]}). "
                        "Refuse silent batch_fill of an empty proactive LLM response."
                    )
            parts.append(arts)

    def _finalize_and_heal(
        merged: dict[str, Any],
        *,
        force_write_no_merge: bool = False,
        rescue_attempted: bool = False,
        rescue_ids: list[str] | None = None,
    ) -> None:
        if revisit_ids:
            merged = _stamp_risk_revisit_done(merged, revisit_ids)
        write_missing_framing_coverage_report(
            ctx,
            merged,
            required_ids=required_ids,
            shard_empty_count=shard_empty_count,
            shard_empty_retries=shard_empty_retries,
            rescue_attempted=rescue_attempted,
            rescue_ids=rescue_ids,
        )
        if force_write_no_merge:
            from interview_mux.artifact_writes import write_validated_artifact

            write_validated_artifact(
                ctx,
                "understanding/gap_evaluations.json",
                merged,
                merge_from_disk=False,
                stage_key="missing_framing",
            )
        else:
            persist(ctx, merged)
        sync_gaps_to_state(ctx, merged)
        heal_or_raise(ctx, "missing_framing", force=True)
        _assert_gap_evaluations_complete(ctx)

    def _maybe_run_sealed_ratio_rescue(
        merged: dict[str, Any],
        *,
        parts: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], bool, list[str]]:
        """One bounded micro-volley when CAP seals exceed sealed_ratio_max.

        ASSETS 13159–13170 sealed 20–45% after CAP=2. Completing without a
        focused rescue ships thin VO downstream. Rescue once, re-seal only
        leftovers that stay unscored, stamp sealed_ratio_rescue_done so
        incompleteness does not thrash.
        """
        stats = _coverage_stats_from_doc(merged, required_ids)
        max_ratio = float(stats["sealed_ratio_max"])
        if stats.get("sealed_ratio_rescue_done"):
            return merged, False, []
        try:
            from interview_mux.gap_vo_gates import gap_framing_enabled

            if not gap_framing_enabled(ctx):
                return merged, False, []
        except Exception:
            pass
        sealed_ids = list(stats["sealed_ids"])
        risk_sealed = _sealed_vs_risk_ids(ctx, merged)
        if float(stats["sealed_ratio"]) <= max_ratio + 1e-9 and not risk_sealed:
            return merged, False, []
        pool = list(dict.fromkeys(list(risk_sealed) + sealed_ids))
        rescue_ids = _pick_sealed_ratio_rescue_ids(ctx, pool)
        if not rescue_ids:
            merged = _stamp_sealed_ratio_rescue_done(merged)
            return merged, False, []
        ctx.log(
            f"missing_framing sealed_ratio rescue: {stats['sealed_ratio']:.2%} sealed "
            f"> max {max_ratio:.2%} — re-volley {len(rescue_ids)} selection-critical id(s)",
            level="warning",
            stage="missing_framing",
            action_id="missing_framing.sealed_ratio_rescue",
            detail={
                "sealed_ratio": stats["sealed_ratio"],
                "sealed_ratio_max": max_ratio,
                "rescue_count": len(rescue_ids),
                "rescue_ids": rescue_ids[:12],
            },
        )
        working = _unseal_rows_for_rescue(merged, rescue_ids)
        rescue_parts: list[dict[str, Any]] = [
            {"evaluations": list(working.get("evaluations") or [])}
        ]
        _run_id_shards(rescue_ids, coverage_pass=True, parts=rescue_parts)
        working = _merge_gap_evaluations(rescue_parts, required_ids)
        by_id: dict[str, dict[str, Any]] = {}
        for row in working.get("evaluations") or []:
            if isinstance(row, dict) and row.get("segment_id"):
                by_id[str(row["segment_id"])] = row
        need_reseal = [
            sid
            for sid in rescue_ids
            if sid not in by_id or _gap_eval_is_unscored_fill(by_id[sid])
        ]
        if need_reseal:
            working = _seal_coverage_exhausted_leftovers(working, need_reseal)
            by_id = {}
            for row in working.get("evaluations") or []:
                if isinstance(row, dict) and row.get("segment_id"):
                    by_id[str(row["segment_id"])] = row
        pre_by: dict[str, dict[str, Any]] = {}
        for row in merged.get("evaluations") or []:
            if isinstance(row, dict) and row.get("segment_id"):
                pre_by[str(row["segment_id"])] = row
        rescue_set = set(rescue_ids)
        final_rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for sid in required_ids:
            if sid in rescue_set and sid in by_id:
                final_rows.append(by_id[sid])
                seen.add(sid)
            elif sid in pre_by:
                final_rows.append(pre_by[sid])
                seen.add(sid)
            elif sid in by_id:
                final_rows.append(by_id[sid])
                seen.add(sid)
        for sid, row in by_id.items():
            if sid not in seen:
                final_rows.append(row)
        working = dict(working)
        working["evaluations"] = final_rows
        working = _stamp_coverage_passes(
            working, max(prev_passes, _coverage_pass_count(merged))
        )
        working = _stamp_sealed_ratio_rescue_done(working)
        return working, True, rescue_ids

    if leftover_ids and prev_passes >= MISSING_FRAMING_COVERAGE_CAP:
        merged = _merge_gap_evaluations(
            [{"evaluations": keep_rows}, existing],
            required_ids,
        )
        merged = _fill_missing_evaluations(merged, leftover_ids)
        merged = _seal_coverage_exhausted_leftovers(merged, leftover_ids)
        merged = _stamp_coverage_passes(merged, prev_passes)
        ctx.log(
            f"missing_framing: sealed {len(leftover_ids)} leftover(s) after "
            f"{MISSING_FRAMING_COVERAGE_CAP} coverage passes",
            level="warning",
            stage="missing_framing",
            action_id="missing_framing.coverage_exhausted_seal",
            detail={"leftover_count": len(leftover_ids), "examples": leftover_ids[:8]},
        )
        with logged_step("missing_framing/llm_stage", ctx=ctx, stage="missing_framing"):
            parts: list[dict[str, Any]] = []
            merged, rescued, rescue_ids = _maybe_run_sealed_ratio_rescue(
                merged, parts=parts
            )
        _finalize_and_heal(
            merged,
            force_write_no_merge=True,
            rescue_attempted=rescued,
            rescue_ids=rescue_ids,
        )
        return

    if keep_rows and not leftover_ids:
        merged = _stamp_coverage_passes(
            _merge_gap_evaluations([{"evaluations": keep_rows}], required_ids),
            prev_passes,
        )
        stats = _coverage_stats_from_doc(merged, required_ids)
        risk_sealed = _sealed_vs_risk_ids(ctx, merged)
        needs_rescue = (
            not stats.get("sealed_ratio_rescue_done")
            and (
                float(stats["sealed_ratio"]) > float(stats["sealed_ratio_max"]) + 1e-9
                or bool(risk_sealed)
            )
        )
        if needs_rescue:
            with logged_step("missing_framing/llm_stage", ctx=ctx, stage="missing_framing"):
                parts = []
                merged, rescued, rescue_ids = _maybe_run_sealed_ratio_rescue(
                    merged, parts=parts
                )
            _finalize_and_heal(
                merged,
                force_write_no_merge=True,
                rescue_attempted=rescued,
                rescue_ids=rescue_ids,
            )
            return
        _finalize_and_heal(merged, force_write_no_merge=False)
        return

    # Pre-specialists on the full 300+ segment tape blow mini context; skip when sharding.
    if len(target_ids or required_ids) <= batch_size:
        with logged_step("missing_framing/pre_specialists", ctx=ctx, stage="missing_framing"):
            maybe_run_pre_stage_specialists(ctx, "missing_framing", build_input(ctx))

    with logged_step("missing_framing/llm_stage", ctx=ctx, stage="missing_framing"):
        parts: list[dict[str, Any]] = []
        if keep_rows:
            parts.append({"evaluations": keep_rows})

        extra_used = int(prev_passes)
        if leftover_reentry:
            extra_used += 1

        _run_id_shards(list(target_ids), coverage_pass=leftover_reentry, parts=parts)
        merged = _merge_gap_evaluations(parts, required_ids)
        still = _still_unscored(merged)
        while still and extra_used < MISSING_FRAMING_COVERAGE_CAP:
            extra_used += 1
            ctx.log(
                f"missing_framing coverage pass {extra_used}/{MISSING_FRAMING_COVERAGE_CAP} "
                f"for {len(still)} unscored segment(s)",
                level="warning",
                stage="missing_framing",
                action_id="missing_framing.coverage_pass",
            )
            _run_id_shards(still, coverage_pass=True, parts=parts)
            merged = _merge_gap_evaluations(parts, required_ids)
            still = _still_unscored(merged)
        if blocking_rerun_stage:
            raise RuntimeError(
                "missing_framing needs.rerun_stage — resume "
                f"{blocking_rerun_stage}: LLM shard refused scoring until upstream "
                f"is fixed (do not CAP-seal over blocking needs)"
            )
        if still and extra_used >= MISSING_FRAMING_COVERAGE_CAP:
            # Same-invoke seal after honest leftover volleys hit CAP (exec_11630 #3).
            merged = _seal_coverage_exhausted_leftovers(merged, still)
            ctx.log(
                f"missing_framing: sealed {len(still)} leftover(s) after "
                f"{MISSING_FRAMING_COVERAGE_CAP} in-invoke coverage passes",
                level="warning",
                stage="missing_framing",
                action_id="missing_framing.coverage_exhausted_seal",
                detail={"leftover_count": len(still), "examples": still[:8]},
            )
            merged = _stamp_coverage_passes(merged, extra_used)
            merged, rescued, rescue_ids = _maybe_run_sealed_ratio_rescue(
                merged, parts=parts
            )
            _finalize_and_heal(
                merged,
                force_write_no_merge=True,
                rescue_attempted=rescued,
                rescue_ids=rescue_ids,
            )
        elif still:
            # Deterministic fill — LLM sparsely samples even with sharded ids.
            # Fills stay on disk and refuse done (HG-3); leftover re-volley scores them.
            merged = _fill_missing_evaluations(merged, still)
            ctx.log(
                f"missing_framing: filled {len(still)} uncovered segment(s) with defaults",
                level="warning",
                stage="missing_framing",
                action_id="missing_framing.batch_fill",
                detail={"filled_count": len(still), "examples": still[:8]},
            )
            merged = _stamp_coverage_passes(merged, extra_used)
            _finalize_and_heal(merged, force_write_no_merge=False)
        else:
            merged = _stamp_coverage_passes(merged, extra_used)
            _finalize_and_heal(merged, force_write_no_merge=False)
        ctx.log(
            f"missing_framing batched complete ({len(merged.get('evaluations') or [])} evaluations)",
            level="success",
            stage="missing_framing",
            action_id="missing_framing.proactive_batch_complete",
        )



def _assert_gap_evaluations_complete(ctx: RunContext) -> None:
    """Fail closed when too many selection-relevant gap rows are unscored stubs."""
    from interview_mux.creative_delivery import creative_delivery_required
    from interview_mux.listenability_guards import gap_eval_scored_ratio, listenability_guards_cfg

    if not creative_delivery_required():
        return
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled

        if not gap_framing_enabled(ctx):
            return
    except Exception:
        pass
    # Default unscored LLM stubs before measuring completeness.
    if ctx.artifact_exists("understanding/gap_evaluations.json"):
        try:
            from interview_mux.artifact_repairs import repair_gap_evaluations
            from interview_mux.artifact_writes import write_validated_artifact

            doc = ctx.read_json("understanding/gap_evaluations.json")
            if isinstance(doc, dict):
                repaired, notes = repair_gap_evaluations(ctx, doc)
                if notes:
                    write_validated_artifact(
                        ctx,
                        "understanding/gap_evaluations.json",
                        repaired,
                        merge_from_disk=False,
                        stage_key="missing_framing",
                    )
                    from interview_mux.stage_completion import (
                        stage_artifact_incompleteness as _inc,
                    )

                    tagged = _inc(ctx, "missing_framing")
                    if tagged and "batch_fill" in str(tagged):
                        raise RuntimeError(tagged)
        except Exception as exc:
            ctx.log(
                f"gap_evaluations repair before completeness assert failed: {exc}",
                level="warning",
                stage="missing_framing",
            )
    ratio = gap_eval_scored_ratio(ctx)
    floor = float(listenability_guards_cfg().get("gap_eval_scored_min_ratio") or 0.95)
    if ratio + 0.001 >= floor:
        return
    raise RuntimeError(
        f"gap_evaluations incomplete: scored_ratio={ratio:.3f} < min={floor:.3f}. "
        "Re-run missing_framing / fill-artifact-gaps until selection segments have severity+gap_type."
    )


def _filter_gap_evaluations_for_ids(
    doc: dict[str, Any] | None, segment_ids: list[str] | None
) -> dict[str, Any]:
    if not isinstance(doc, dict):
        return {"evaluations": []}
    evals = [e for e in (doc.get("evaluations") or []) if isinstance(e, dict)]
    if segment_ids is None:
        return {"evaluations": evals, **{k: v for k, v in doc.items() if k != "evaluations"}}
    want = {str(s) for s in segment_ids}
    return {
        "evaluations": [e for e in evals if str(e.get("segment_id") or "") in want],
    }


def _trim_prior_contexts_to_ids(payload: dict[str, Any], segment_ids: list[str] | None) -> dict[str, Any]:
    if not segment_ids:
        return payload
    want = {str(s) for s in segment_ids}
    for key in (
        "prior_native_contexts",
        "target_native_contexts",
        "vo_missions",
    ):
        raw = payload.get(key)
        if isinstance(raw, dict):
            payload[key] = {k: v for k, v in raw.items() if str(k) in want}
    highlights = payload.get("prior_impact_highlights")
    if isinstance(highlights, list):
        payload["prior_impact_highlights"] = [
            h
            for h in highlights
            if isinstance(h, dict) and str(h.get("before_target") or "") in want
        ][:40]
    return payload


def _refresh_hosted_vo_after_gap_compose(ctx: RunContext) -> None:
    """Re-identify floor + thin orientation apply after compose seats land."""
    try:
        from interview_mux.hosted_vo_authority import (
            apply_orientation,
            identify_hosted_vo_floor,
        )

        identify_hosted_vo_floor(ctx, stage_id="gap_framing_compose", persist=True)
        if not ctx.artifact_exists("understanding/gap_report.json"):
            return
        if not ctx.artifact_exists("master/selection.json"):
            return
        gap = ctx.read_json("understanding/gap_report.json")
        sel = ctx.read_json("master/selection.json")
        if not isinstance(gap, dict) or not isinstance(sel, dict):
            return
        ordered = [str(x) for x in (sel.get("ordered_segment_ids") or []) if x]
        if not ordered:
            return
        updated, actions = apply_orientation(ctx, gap, ordered)
        if actions:
            ctx.write_json(
                "understanding/gap_report.json",
                updated,
                stage_key="gap_framing_compose",
            )
    except Exception:
        pass


def _heal_gap_framing_compose_if_complete(ctx: RunContext) -> None:
    """Mark done only when land-honest complete; else raise (no hollow Finished).

    Never early-return on bare ``is_done`` — hollow stamps must go through
    heal_or_raise so incompleteness can unmark (Land Honesty).
    """
    _refresh_hosted_vo_after_gap_compose(ctx)
    from interview_mux.stage_completion import heal_or_raise

    heal_or_raise(ctx, "gap_framing_compose")


def _merge_gap_report_parts(parts: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge sharded gap_framing_compose artifacts (lines + gaps + plan).

    Plans: prefer the richest (most impact_blocks / framing_line_ids), not first-wins.
    Gaps: dedupe by segment_id (last wins for field updates).
    """
    lines_by_id: dict[str, dict[str, Any]] = {}
    gaps_by_sid: dict[str, Any] = {}
    gaps_no_sid: list[Any] = []
    plans: list[dict[str, Any]] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        for line in part.get("interviewer_lines") or []:
            if not isinstance(line, dict):
                continue
            lid = str(line.get("line_id") or "").strip()
            if not lid:
                tgt = str(line.get("targets_segment_id") or line.get("segment_id") or "")
                cat = str(line.get("line_category") or "line")
                lid = f"vo_{cat}_{tgt}" if tgt else f"vo_auto_{len(lines_by_id)+1}"
                line = {**line, "line_id": lid}
            if lid not in lines_by_id:
                lines_by_id[lid] = line
        for g in part.get("gaps") or []:
            if not isinstance(g, dict):
                gaps_no_sid.append(g)
                continue
            sid = str(g.get("segment_id") or "").strip()
            if sid:
                gaps_by_sid[sid] = g
            else:
                gaps_no_sid.append(g)
        gp = part.get("gap_framing_plan")
        if isinstance(gp, dict):
            plans.append(gp)
    plan: dict[str, Any] | None = None
    if plans:
        def _plan_richness(p: dict[str, Any]) -> int:
            score = 0
            for act in p.get("acts") or []:
                if not isinstance(act, dict):
                    continue
                blocks = act.get("impact_blocks") or []
                if isinstance(blocks, list):
                    score += len(blocks)
                    for b in blocks:
                        if isinstance(b, dict):
                            score += len(b.get("framing_line_ids") or [])
            return score

        plan = max(plans, key=_plan_richness)
    out: dict[str, Any] = {
        "interviewer_lines": list(lines_by_id.values()),
        "gaps": list(gaps_by_sid.values()) + gaps_no_sid,
    }
    if plan is not None:
        out["gap_framing_plan"] = plan
    return out


def _compose_framing_warrants_vo(ctx: RunContext) -> bool:
    """True when G-Framing Yes and evals warrant hosted VO (floor/fill honesty)."""
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled
        from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
        from interview_mux.stage_completion import _gap_evals_warrant_hosted_vo

        if gap_fill_was_skipped(ctx) or not gap_framing_enabled(ctx):
            return False
        return bool(_gap_evals_warrant_hosted_vo(ctx))
    except Exception:
        return False


def _uncovered_high_segment_ids(
    ctx: RunContext, gap_report: dict[str, Any] | None
) -> list[str]:
    """High-severity eval segment_ids with no targeting interviewer line."""
    if not ctx.artifact_exists("understanding/gap_evaluations.json"):
        return []
    try:
        from interview_mux.high_gap_vo import targeted_segment_ids

        evals = ctx.read_json("understanding/gap_evaluations.json")
    except Exception:
        return []
    if not isinstance(evals, dict):
        return []
    report = gap_report if isinstance(gap_report, dict) else {}
    lines = report.get("interviewer_lines") if isinstance(report.get("interviewer_lines"), list) else []
    targeted = targeted_segment_ids(lines, ctx)
    out: list[str] = []
    for row in evals.get("evaluations") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("severity") or "").lower() != "high":
            continue
        sid = str(row.get("segment_id") or "").strip()
        if sid and sid not in targeted:
            out.append(sid)
    return out


def _warrant_gap_count(ctx: RunContext) -> int:
    """Count medium/high / missing_* evals for VO budget scaling (not full manifest)."""
    if not ctx.artifact_exists("understanding/gap_evaluations.json"):
        return 0
    try:
        doc = ctx.read_json("understanding/gap_evaluations.json")
    except Exception:
        return 0
    if not isinstance(doc, dict):
        return 0
    n = 0
    for row in doc.get("evaluations") or []:
        if not isinstance(row, dict):
            continue
        gtype = str(row.get("gap_type") or "").strip().lower()
        if not gtype or gtype in {"ok_with_light_bridge", "null", "none"}:
            continue
        sev = str(row.get("severity") or "").strip().lower()
        if sev in {"medium", "high"}:
            n += 1
        elif sev == "low" and gtype.startswith("missing_"):
            n += 1
    return n


def _log_gap_compose_needs(ctx: RunContext, exc: BaseException) -> None:
    """Structured signal for mid-compose LLM needs / partial — never invent complete."""
    msg = str(exc)
    ctx.log(
        f"gap_compose_needs: {msg[:400]}",
        level="warning",
        stage="gap_framing_compose",
        action_id="gap_compose_needs",
        detail={"error": msg[:500]},
    )


def _gap_framing_compose_payload(
    c: RunContext,
    *,
    segment_ids: list[str] | None = None,
    shard_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from interview_mux.gap_framing import gap_framing_cfg
    from interview_mux.config import merged_config
    import math

    evals_doc = (
        c.read_json("understanding/gap_evaluations.json")
        if c.artifact_exists("understanding/gap_evaluations.json")
        else {"evaluations": []}
    )
    payload: dict[str, Any] = {
        "gap_evaluations": _filter_gap_evaluations_for_ids(
            evals_doc if isinstance(evals_doc, dict) else {}, segment_ids
        ),
        "segments": _compact_segments_payload(c, segment_ids=segment_ids),
        "content_brief": c.read_json("understanding/content_brief.json"),
        "gap_framing_policy": gap_framing_cfg(),
    }
    ordered_ids: list[str] = []
    if segment_ids:
        ordered_ids = [str(s) for s in segment_ids if s]
    elif c.artifact_exists("master/selection.json"):
        sel = c.read_json("master/selection.json")
        if isinstance(sel, dict):
            ordered_ids = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
    if not ordered_ids and c.artifact_exists("segments/manifest.json"):
        man = c.read_json("segments/manifest.json")
        ordered_ids = [
            str(r.get("segment_id"))
            for r in ((man or {}).get("segments") or [])
            if isinstance(r, dict) and r.get("segment_id")
        ]
    payload["ordered_segment_ids"] = ordered_ids
    if c.artifact_exists("understanding/delivery_brief.json"):
        payload["delivery_brief"] = c.read_json("understanding/delivery_brief.json")
    if c.artifact_exists("understanding/episode_structure.json"):
        payload["episode_structure"] = c.read_json("understanding/episode_structure.json")
    # VO density contract for compose. Prefer air-order / episode structure /
    # warrant count — never inflate from full manifest before selection exists.
    gf = ((merged_config().get("analysis") or {}).get("gap_framing") or {})
    min_r = float(gf.get("min_vo_insert_ratio") or 0.0)
    tgt_r = float(gf.get("target_vo_insert_ratio") or 0.08)
    if segment_ids is not None:
        ordered_n = len(segment_ids)
    else:
        ordered_n = 0
        if c.artifact_exists("master/selection.json"):
            sel = c.read_json("master/selection.json")
            if isinstance(sel, dict):
                ordered_n = len([s for s in (sel.get("ordered_segment_ids") or []) if s])
        if ordered_n <= 0 and c.artifact_exists("understanding/episode_structure.json"):
            ep = c.read_json("understanding/episode_structure.json")
            if isinstance(ep, dict):
                order = ep.get("ordered_segment_ids") or ep.get("segment_order") or []
                if isinstance(order, list) and order:
                    ordered_n = len([s for s in order if s])
        if ordered_n <= 0:
            # Scale from gap warrant count (medium/high / missing_*), not full manifest.
            ordered_n = _warrant_gap_count(c)
    vo_min = int(math.ceil(ordered_n * min_r)) if ordered_n and min_r > 0 else 0
    vo_ideal = max(vo_min, int(math.ceil(ordered_n * tgt_r))) if ordered_n else vo_min
    qb = {}
    if isinstance(payload.get("delivery_brief"), dict) and segment_ids is None:
        qb = (
            (payload["delivery_brief"].get("question_budget") or {})
            if isinstance(payload["delivery_brief"].get("question_budget"), dict)
            else {}
        )
    payload["vo_line_budget"] = {
        "min": int(qb.get("min") or vo_min),
        "ideal": int(qb.get("ideal") or vo_ideal),
        "max": int(qb.get("max") or max(vo_ideal, vo_min)),
        "scale_basis": (
            "shard"
            if segment_ids is not None
            else (
                "selection"
                if c.artifact_exists("master/selection.json") and ordered_n
                else "warrant_gaps"
            )
        ),
        "ordered_n": ordered_n,
    }
    vf = compact_value_features_summary(c)
    if vf:
        payload["value_features_summary"] = vf
    payload = attach_adaptation_to_payload(c, payload)
    try:
        from interview_mux.mastering_plan_loader import (
            best_available_mode,
            compose_plan_bind_mode,
            validate_or_degrade,
        )
        from interview_mux.narrative_mode import prefer_forbid_volley_block

        plan = validate_or_degrade(c)
        mode = best_available_mode(plan)
        status = str(plan.get("plan_status") or "degraded")
        bind_mode = compose_plan_bind_mode(plan)
        authoritative = bind_mode == "authoritative"
        # GF-02 honesty: never pretend soft-gate/thin plan is authoritative for compose.
        if not authoritative and status == "complete":
            status = "degraded_for_compose"
        payload["mastering_plan_summary"] = {
            "narrative_mode": mode,
            "pass": plan.get("pass"),
            "plan_status": status,
            "plan_authoritative": authoritative,
            "plan_status_raw": plan.get("plan_status"),
            "bind_mode": bind_mode,
            "montage_grammar": plan.get("montage_grammar"),
            "pov": plan.get("pov"),
        }
        payload["narrative_mode_priors"] = prefer_forbid_volley_block(mode, plan)
        if not authoritative:
            payload["mastering_plan_summary"]["note"] = (
                "soft_gate_or_degraded — compose treats plan as advisory only"
            )
    except Exception:
        payload["mastering_plan_summary"] = {
            "plan_status": "missing",
            "plan_authoritative": False,
            "bind_mode": "advisory",
        }
    # Address labels for name/group-aware VO (never invent names)
    try:
        from interview_mux.speaker_delivery_plan import (
            build_speaker_delivery_plan,
            write_speaker_delivery_plan,
        )

        if c.artifact_exists("understanding/speaker_delivery_plan.json"):
            sdp = c.read_json("understanding/speaker_delivery_plan.json")
        else:
            sdp = build_speaker_delivery_plan(c)
            try:
                write_speaker_delivery_plan(c)
            except Exception:
                pass
        if isinstance(sdp, dict):
            payload["address_labels"] = sdp.get("address_labels") or {}
            payload["speaker_delivery_plan"] = {
                "clone_speaker_id": sdp.get("clone_speaker_id"),
                "insert_strategy": sdp.get("insert_strategy"),
                "address_mode": sdp.get("address_mode"),
                "group_label": sdp.get("group_label"),
                "speaker_count": sdp.get("speaker_count"),
            }
    except Exception:
        pass
    if c.artifact_exists("understanding/reorder_bridges.json"):
        payload["reorder_bridges"] = c.read_json("understanding/reorder_bridges.json")
    from interview_mux.gap_vo_prior_context import (
        attach_prior_native_contexts_to_payload,
        attach_vo_partner_context_to_payload,
    )

    payload = attach_prior_native_contexts_to_payload(c, payload)
    payload = attach_vo_partner_context_to_payload(c, payload, segment_ids=segment_ids)
    payload = _trim_prior_contexts_to_ids(payload, segment_ids)
    if shard_meta:
        payload["_gap_compose_shard"] = shard_meta
    return _compact_gap_compose_packet(payload)


def _compact_gap_compose_packet(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep seam context, drop quote walls that push later keys past the model window."""
    for key in ("prior_native_contexts", "target_native_contexts"):
        raw = payload.get(key)
        if not isinstance(raw, dict):
            continue
        compact: dict[str, Any] = {}
        for sid, pkt in raw.items():
            if not isinstance(pkt, dict):
                continue
            quote = str(pkt.get("quote_span") or pkt.get("text") or pkt.get("excerpt") or "")
            compact[str(sid)] = {
                "segment_id": pkt.get("segment_id") or sid,
                "quote_span": quote[:280],
                "prior_impact_beat": pkt.get("prior_impact_beat"),
                "prior_complete_thought": pkt.get("prior_complete_thought"),
                "chapter_title": pkt.get("chapter_title"),
                "target_is_micro": pkt.get("target_is_micro"),
            }
        payload[key] = compact
    missions = payload.get("vo_missions")
    if isinstance(missions, dict):
        payload["vo_missions"] = {
            str(sid): {
                "segment_id": (pkt.get("segment_id") if isinstance(pkt, dict) else sid) or sid,
                "gap_type": pkt.get("gap_type") if isinstance(pkt, dict) else None,
                "severity": pkt.get("severity") if isinstance(pkt, dict) else None,
                "mission": str((pkt or {}).get("mission") or "")[:220] if isinstance(pkt, dict) else "",
            }
            for sid, pkt in missions.items()
        }
    segs = payload.get("segments")
    rows = segs.get("segments") if isinstance(segs, dict) else segs
    if isinstance(rows, list):
        trimmed = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            trimmed.append(
                {
                    "segment_id": row.get("segment_id"),
                    "speaker_id": row.get("speaker_id"),
                    "speaker_role": row.get("speaker_role"),
                    "type": row.get("type"),
                    "start_ms": row.get("start_ms"),
                    "end_ms": row.get("end_ms"),
                    "text": str(row.get("text") or "")[:220],
                }
            )
        if isinstance(segs, dict):
            payload["segments"] = {**segs, "segments": trimmed}
        else:
            payload["segments"] = trimmed
    return payload


def run_gap_framing_compose(ctx: RunContext) -> None:
    """Compose full gap framing script (questions, summaries, prefaces, bridges)."""
    from interview_mux.llm_simple import run_llm_stage_simple

    # Nugget Layup owns contentful before-VO. Re-running the interviewer-script
    # LLM under layup authority (or after seat freeze) rewrites gap_report,
    # invalidates WAVs, and thrash-rewinds past EDL (forensics exec_11136).
    try:
        from interview_mux.nugget_layup import (
            PLAN_REL,
            gap_report_has_layup_authority,
            nugget_layup_enabled,
            publish_layup_plan_to_gap_report,
        )
        from interview_mux.artifact_ownership import freeze_write_allowed
        # heal_or_refuse_mark: module import from stage_completion (not write_staging).

        gap = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else {}
        )
        # Orphan stamp (authority without plan): clear stamp and fall through to
        # analysis-era compose. Silent no-op here hollow-Finishes and thrash-pins
        # gap_framing_compose forever (high_gap_unframed never flips).
        if (
            nugget_layup_enabled()
            and isinstance(gap, dict)
            and bool(gap.get("nugget_layup_authority"))
            and not ctx.artifact_exists(PLAN_REL)
        ):
            cleared = dict(gap)
            cleared["nugget_layup_authority"] = False
            meta = cleared.get("_meta") if isinstance(cleared.get("_meta"), dict) else {}
            repairs = list(meta.get("repairs") or [])
            repairs.append(
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "action": "clear_orphan_nugget_layup_authority",
                    "reason": "stamp_without_plan",
                }
            )
            cleared["_meta"] = {**meta, "repairs": repairs}
            ctx.write_json(
                "understanding/gap_report.json",
                cleared,
                skip_handoff=True,
            )
            gap = cleared
            ctx.log(
                "gap_framing_compose: cleared orphan layup authority stamp "
                "(no nugget_layup_plan) — falling through to analysis-era compose",
                level="warning",
                stage="gap_framing_compose",
                action_id="gap_framing_compose.clear_orphan_layup_authority",
            )
        plan_contentful = False
        if ctx.artifact_exists(PLAN_REL):
            try:
                plan_doc = ctx.read_json(PLAN_REL)
                plan_contentful = bool(
                    isinstance(plan_doc, dict)
                    and (
                        plan_doc.get("lines")
                        or plan_doc.get("nuggets")
                        or plan_doc.get("placements")
                        or plan_doc.get("interviewer_lines")
                    )
                )
            except Exception:
                plan_contentful = False
        layup_owns = bool(
            nugget_layup_enabled()
            and (
                gap_report_has_layup_authority(gap if isinstance(gap, dict) else None)
                or plan_contentful
            )
        )
        # Authority flap: contentful plan on disk without stamp → refuse LLM.
        # Empty/thin plan file is not ownership (Land Honesty stamp registry).
        # Stamp-without-plan is healed above (clear + fall through), not no-op'd.
        flap = False
        if nugget_layup_enabled() and isinstance(gap, dict):
            stamped = bool(gap.get("nugget_layup_authority"))
            if plan_contentful and not stamped:
                flap = True
                ctx.log(
                    "gap_framing_compose: layup plan on disk without authority stamp — "
                    "fail-closed no-op (authority flap)",
                    level="warning",
                    stage="gap_framing_compose",
                    action_id="gap_framing_compose.layup_authority_flap",
                )
        frozen = not freeze_write_allowed(
            ctx,
            "gap_framing_compose",
            "compose_copy",
        )
        if layup_owns or frozen or flap:
            why = (
                "layup_authority_flap"
                if flap and not layup_owns
                else ("layup_authority" if layup_owns else "seat_freeze")
            )
            try:
                if ctx.artifact_exists(PLAN_REL):
                    publish_layup_plan_to_gap_report(ctx)
            except Exception as pub_exc:
                ctx.log(
                    f"gap_framing_compose: {why} no-op publish skipped: {pub_exc}",
                    level="warning",
                    stage="gap_framing_compose",
                )
            ctx.log(
                f"gap_framing_compose: no-op under {why}",
                level="info",
                stage="gap_framing_compose",
            )
            from interview_mux.delivery_guardrails import seed_stage_complete

            if not seed_stage_complete(ctx, "gap_framing_compose"):
                try:
                    # Land Honesty: never force-stamp when incompleteness / unpaid land open
                    # (flap / freeze no-op must not greenwash stamp-alone or thin gap).
                    from interview_mux.done_authority import unpaid_land_reason
                    from interview_mux.stage_completion import (
                        heal_or_refuse_mark,
                        stage_artifact_incompleteness,
                    )

                    if (
                        unpaid_land_reason(ctx, "gap_framing_compose") is None
                        and stage_artifact_incompleteness(ctx, "gap_framing_compose")
                        is None
                    ):
                        heal_or_refuse_mark(ctx, "gap_framing_compose", force=True)
                except Exception:
                    pass
            return
    except ImportError:
        # Wrong-module imports must not fall through into LLM rewrite under freeze.
        raise
    except Exception as exc:
        # Fail-closed when layup/freeze evidence exists; never fall through into LLM.
        # If neither armed and authority unknown, raise loud (no hollow done, no rewrite).
        plan_exists = False
        freeze_hint = False
        try:
            from interview_mux.nugget_layup import PLAN_REL as _PLAN_REL

            plan_exists = bool(ctx.artifact_exists(_PLAN_REL))
        except Exception:
            plan_exists = False
        try:
            from interview_mux.seat_authority import hard_freeze_active, soft_freeze_active

            freeze_hint = bool(soft_freeze_active(ctx) or hard_freeze_active(ctx))
        except Exception:
            freeze_hint = False
        if not (plan_exists or freeze_hint):
            raise RuntimeError(
                f"gap_framing_compose: authority/freeze guard error with no "
                f"layup/freeze evidence — refusing LLM fall-through ({exc})"
            ) from exc
        ctx.log(
            f"gap_framing_compose: authority/freeze guard error — fail-closed no-op: {exc}",
            level="warning",
            stage="gap_framing_compose",
        )
        try:
            from interview_mux.nugget_layup import (
                PLAN_REL as _PLAN_REL2,
                publish_layup_plan_to_gap_report as _pub,
            )

            if ctx.artifact_exists(_PLAN_REL2):
                _pub(ctx)
        except Exception as pub_exc:
            ctx.log(
                f"gap_framing_compose: fail-closed publish skipped: {pub_exc}",
                level="warning",
                stage="gap_framing_compose",
            )
        from interview_mux.delivery_guardrails import seed_stage_complete

        if not seed_stage_complete(ctx, "gap_framing_compose"):
            try:
                from interview_mux.done_authority import unpaid_land_reason
                from interview_mux.stage_completion import stage_artifact_incompleteness

                if (
                    unpaid_land_reason(ctx, "gap_framing_compose") is None
                    and stage_artifact_incompleteness(ctx, "gap_framing_compose")
                    is None
                ):
                    heal_or_refuse_mark(ctx, "gap_framing_compose", force=True)
            except Exception:
                pass
        return

    # R2 opt-in: when layup will own body and corpus/plan is ready, seed
    # orientation + high-gap deterministic cover only — skip full compose LLM.
    try:
        from interview_mux.config import merged_config
        from interview_mux.nugget_layup import PLAN_REL as _LAYUP_PLAN, nugget_layup_enabled

        nl = ((merged_config().get("analysis") or {}).get("nugget_layup") or {})
        if (
            nugget_layup_enabled()
            and bool(nl.get("compose_orientation_only_when_plan_ready"))
            and (
                ctx.artifact_exists(_LAYUP_PLAN)
                or ctx.artifact_exists("understanding/nugget_corpus.json")
            )
        ):
            from interview_mux.high_gap_vo import (
                fill_uncovered_high_gaps,
                seed_uncovered_high_gaps_deterministic,
            )
            from interview_mux.artifact_writes import write_validated_artifact
            from interview_mux.gap_framing import persist_gap_framing_companion_artifacts

            seed: dict[str, Any] = (
                ctx.read_json("understanding/gap_report.json")
                if ctx.artifact_exists("understanding/gap_report.json")
                else {"interviewer_lines": []}
            )
            if not isinstance(seed.get("interviewer_lines"), list):
                seed["interviewer_lines"] = []
            applied: list[dict[str, Any]] = []
            fill_uncovered_high_gaps(
                ctx, seed, applied=applied, origin="compose_orientation_only_fill"
            )
            seed_uncovered_high_gaps_deterministic(
                ctx, seed, applied=applied, origin="compose_orientation_only_seed"
            )
            seed["_meta"] = {
                **(seed.get("_meta") if isinstance(seed.get("_meta"), dict) else {}),
                "producer": "gap_framing_compose",
                "compose_mode": "orientation_only_layup_ready",
            }
            persist_gap_framing_companion_artifacts(ctx, seed)
            write_validated_artifact(
                ctx,
                "understanding/gap_report.json",
                seed,
                merge_from_disk=True,
                stage_key="gap_framing_compose",
            )
            ctx.log(
                "gap_framing_compose: orientation-only stub (layup plan/corpus ready)",
                level="info",
                stage="gap_framing_compose",
                action_id="gap_framing_compose.orientation_only",
            )
            _heal_gap_framing_compose_if_complete(ctx)
            return
    except Exception as stub_exc:
        ctx.log(
            f"gap_framing_compose: orientation-only stub skipped: {stub_exc}",
            level="warning",
            stage="gap_framing_compose",
        )

    required_ids = _gap_segment_ids(ctx)
    batch_size = _gap_pass_batch_size()
    prompt_rel = prompt_variant("interviewer-gap/gap-framing-compose.system.txt", ctx)

    def build_input(c: RunContext) -> dict:
        return _gap_framing_compose_payload(c)

    def persist(c: RunContext, artifacts: dict) -> None:
        from interview_mux.artifact_repairs import repair_gap_report
        from interview_mux.artifact_writes import write_validated_artifact
        from interview_mux.gap_framing import persist_gap_framing_companion_artifacts
        from interview_mux.gap_vo_prior_context import (
            stamp_lines_prior_provenance,
            write_gap_vo_context_audit,
        )

        plan = artifacts.pop("gap_framing_plan", None)
        repaired, _ = repair_gap_report(c, artifacts)
        from interview_mux.high_gap_vo import fill_uncovered_high_gaps, resolve_seats

        fill_applied: list[dict[str, Any]] = []
        filled = 0
        warrants = _compose_framing_warrants_vo(c)
        try:
            filled = fill_uncovered_high_gaps(
                c, repaired, applied=fill_applied, origin="high_gap_vo_fill"
            )
        except Exception as exc:
            uncovered = _uncovered_high_segment_ids(c, repaired)
            c.log(
                f"gap_framing_compose: high-gap fill failed: {exc}",
                level="warning",
                stage="gap_framing_compose",
            )
            if warrants and uncovered:
                raise RuntimeError(
                    "gap_framing_compose: high-gap fill failed while framing Yes "
                    f"leaves uncovered high gaps {uncovered[:8]} — refusing silent skip ({exc})"
                ) from exc
        # One fill retry when still uncovered under warrant (demote honesty).
        if warrants and _uncovered_high_segment_ids(c, repaired):
            try:
                filled += fill_uncovered_high_gaps(
                    c,
                    repaired,
                    applied=fill_applied,
                    origin="high_gap_vo_fill_retry",
                )
            except Exception as retry_exc:
                c.log(
                    f"gap_framing_compose: high-gap fill retry failed: {retry_exc}",
                    level="warning",
                    stage="gap_framing_compose",
                )
        if filled:
            c.log(
                f"gap_framing_compose: filled {filled} uncovered high gap(s)",
                level="info",
                stage="gap_framing_compose",
            )
        # Spoken-copy omit can drop seed/fill lines that still "target" a high gap.
        repaired, _ = repair_gap_report(c, repaired)
        lines = repaired.get("interviewer_lines")
        if isinstance(lines, list):
            repaired["interviewer_lines"] = stamp_lines_prior_provenance(c, lines)
            write_gap_vo_context_audit(c, repaired["interviewer_lines"])
        persist_gap_framing_companion_artifacts(c, repaired)
        if isinstance(plan, dict):
            c.write_json(
                "understanding/gap_framing_plan.json",
                plan,
                stage_key="gap_framing_compose",
            )
        still_uncovered = _uncovered_high_segment_ids(c, repaired)
        # Do not demote-to-green when framing Yes still warrants VO + uncovered highs.
        if still_uncovered and warrants:
            c.log(
                "gap_framing_compose: refusing demote of "
                f"{len(still_uncovered)} uncovered high gap(s) under framing Yes — "
                "heal_or_raise will mark incomplete",
                level="warning",
                stage="gap_framing_compose",
                detail={"uncovered": still_uncovered[:12]},
            )
        else:
            resolution = resolve_seats(c, intent="compose_persist", gap_report=repaired)
            if resolution.demoted:
                c.log(
                    "gap_framing_compose: demoted "
                    f"{resolution.demoted} uncovered high gap(s) after fill",
                    level="warning",
                    stage="gap_framing_compose",
                )
        write_validated_artifact(
            c,
            "understanding/gap_report.json",
            repaired,
            merge_from_disk=True,
            stage_key="gap_framing_compose",
        )

    with logged_step("gap_framing_compose/llm_stage", ctx=ctx, stage="gap_framing_compose"):
        if len(required_ids) <= batch_size:
            try:
                run_analysis_llm_stage(
                    ctx,
                    "gap_framing_compose",
                    prompt_rel,
                    build_input,
                    persist,
                    auto_complete=False,
                )
            except Exception as exc:
                _log_gap_compose_needs(ctx, exc)
                ctx.log(
                    f"gap_framing_compose flagship failed — high-gap fill: {exc}",
                    level="warning",
                    stage="gap_framing_compose",
                )
                from interview_mux.high_gap_vo import fill_uncovered_high_gaps

                seed = (
                    ctx.read_json("understanding/gap_report.json")
                    if ctx.artifact_exists("understanding/gap_report.json")
                    else {"interviewer_lines": []}
                )
                applied: list[dict[str, Any]] = []
                fill_uncovered_high_gaps(ctx, seed, applied=applied, origin="high_gap_vo_fill")
                persist(ctx, seed)
            # CSP-05 / GFC-B1: assert completeness before done (zero lines under Yes → incomplete).
            _heal_gap_framing_compose_if_complete(ctx)
            return

        batches = [
            required_ids[i : i + batch_size]
            for i in range(0, len(required_ids), batch_size)
        ]
        ctx.log(
            f"gap_framing_compose proactive batch: {len(required_ids)} segments → "
            f"{len(batches)} shard(s) of ≤{batch_size}",
            level="info",
            stage="gap_framing_compose",
            action_id="gap_framing_compose.proactive_batch",
            detail={
                "required_count": len(required_ids),
                "batch_size": batch_size,
                "batches": len(batches),
            },
        )

        def _noop_persist(_c: RunContext, _artifacts: dict) -> None:
            return None

        parts: list[dict[str, Any]] = []
        for bi, batch_ids in enumerate(batches):

            def build_batch(
                c: RunContext,
                *,
                _ids: list[str] = list(batch_ids),
                _bi: int = bi,
                _total: int = len(batches),
            ) -> dict:
                return _gap_framing_compose_payload(
                    c,
                    segment_ids=_ids,
                    shard_meta={
                        "index": _bi + 1,
                        "total": _total,
                        "segment_ids": list(_ids),
                    },
                )

            ctx.log(
                f"gap_framing_compose shard {bi + 1}/{len(batches)} "
                f"({len(batch_ids)} segment ids)",
                level="action",
                stage="gap_framing_compose",
                action_id="gap_framing_compose.shard",
            )
            try:
                envelope = run_llm_stage_simple(
                    ctx,
                    "gap_framing_compose",
                    prompt_rel,
                    build_batch,
                    _noop_persist,
                    auto_complete=False,
                )
            except Exception as exc:
                # Nested LLM may ask to rerun ranking / starve a shard. Keep
                # sibling shards and host-fill instead of aborting the stage.
                _log_gap_compose_needs(ctx, exc)
                ctx.log(
                    f"gap_framing_compose shard {bi + 1}/{len(batches)} failed — "
                    f"continue with remaining shards: {exc}",
                    level="warning",
                    stage="gap_framing_compose",
                )
                envelope = {}
            arts = envelope.get("artifacts") if isinstance(envelope.get("artifacts"), dict) else {}
            if isinstance(arts, dict) and arts:
                parts.append(arts)
            # Surface blocking needs without inventing completion.
            if isinstance(envelope, dict):
                needs = envelope.get("needs") or []
                status = str(envelope.get("status") or "")
                if status == "partial" or (
                    isinstance(needs, list) and any(
                        isinstance(n, dict) and n.get("blocking") for n in needs
                    )
                ):
                    _log_gap_compose_needs(
                        ctx,
                        RuntimeError(
                            f"shard {bi + 1} status={status!r} needs={needs!r}"
                        ),
                    )

        merged = _merge_gap_report_parts(parts)
        line_count = len(merged.get("interviewer_lines") or [])
        all_shards_empty = not parts or line_count == 0
        if all_shards_empty:
            ctx.log(
                "gap_framing_compose shards returned no lines — filling uncovered high gaps",
                level="warning",
                stage="gap_framing_compose",
            )
            from interview_mux.high_gap_vo import fill_uncovered_high_gaps

            seed: dict[str, Any] = {"interviewer_lines": []}
            if isinstance(merged, dict):
                seed.update({k: v for k, v in merged.items() if k != "interviewer_lines"})
                seed["interviewer_lines"] = []
            applied: list[dict[str, Any]] = []
            fill_uncovered_high_gaps(ctx, seed, applied=applied, origin="high_gap_vo_fill")
            merged = seed
        persist(ctx, merged)
        # Same completeness bar as single-batch — never soft-green after empty shards.
        _heal_gap_framing_compose_if_complete(ctx)
        final_n = len(
            (merged.get("interviewer_lines") or [])
            if isinstance(merged, dict)
            else []
        )
        if all_shards_empty and _compose_framing_warrants_vo(ctx) and final_n == 0:
            ctx.log(
                "gap_framing_compose batched fill-only under framing Yes — "
                "awaiting heal_or_raise incompleteness (no premature success)",
                level="warning",
                stage="gap_framing_compose",
                action_id="gap_framing_compose.proactive_batch_empty",
            )
        else:
            ctx.log(
                f"gap_framing_compose batched complete ({final_n} lines)",
                level="success",
                stage="gap_framing_compose",
                action_id="gap_framing_compose.proactive_batch_complete",
            )


def run_optimal_questions(ctx: RunContext) -> None:
    """Legacy alias — delegates to gap_framing_compose."""
    run_gap_framing_compose(ctx)


def run_optimal_questions_legacy(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        payload = {
            "gap_evaluations": c.read_json("understanding/gap_evaluations.json"),
            "segments": _compact_segments_payload(c),
            "content_brief": c.read_json("understanding/content_brief.json"),
        }
        vf = compact_value_features_summary(c)
        if vf:
            payload["value_features_summary"] = vf
        return attach_adaptation_to_payload(c, payload)

    def persist(c: RunContext, artifacts: dict) -> None:
        from interview_mux.artifact_repairs import repair_gap_report
        from interview_mux.artifact_writes import write_validated_artifact

        repaired, _ = repair_gap_report(c, artifacts)
        write_validated_artifact(
            c,
            "understanding/gap_report.json",
            repaired,
            merge_from_disk=True,
            stage_key="optimal_questions",
        )
        persist_optimal_questions_companion_artifacts(c, repaired)

    with logged_step("optimal_questions/llm_stage", ctx=ctx, stage="optimal_questions"):
        run_analysis_llm_stage(
            ctx,
            "optimal_questions",
            prompt_variant("interviewer-gap/optimal-questions.system.txt", ctx),
            build_input,
            persist,
        )


def gap_compose_stage_done(ctx: RunContext) -> bool:
    """True when gap compose (or optimal_questions alias) is land-honest complete.

    Never bare ``is_done`` — hollow stamps must not look compose-done (Land Honesty).
    """
    from interview_mux.done_authority import land_honest

    return land_honest(ctx, "gap_framing_compose") or land_honest(
        ctx, "optimal_questions"
    )


def persist_optimal_questions_companion_artifacts(ctx: RunContext, artifacts: dict) -> None:
    """Write interviewer_script.txt after gap_report.json (resilience + merge persist)."""
    lines = artifacts.get("interviewer_lines") or []
    eligible = pickup_eligible_speaker_id(ctx)
    for i, line in enumerate(lines):
        if "line_id" not in line:
            line["line_id"] = f"line_{i+1:03d}"
        if not line.get("placement"):
            line["placement"] = "before"
        if line.get("delivery") == "synthesize" and not line.get("voice_speaker_id"):
            eligible = pickup_eligible_speaker_id(ctx)
            if eligible:
                line["voice_speaker_id"] = eligible
        if line.get("delivery") == "record" and eligible:
            line["voice_speaker_id"] = eligible
    _write_interviewer_script(ctx, lines)


def _write_interviewer_script(ctx: RunContext, lines: list[dict]) -> None:
    from interview_mux.gap_framing import commit_interviewer_script

    rows = [
        "# Interviewer script — record to vo_pickup/{line_id}.wav or synthesize at G1",
        "",
    ]
    for line in lines:
        lid = line.get("line_id", "line_unknown")
        rows.append(f"## {lid} ({line.get('delivery', 'record')})")
        rows.append(f"Target: {line.get('targets_segment_id', '')} — {line.get('gap_type', '')}")
        rows.append(line.get("text", ""))
        rows.append("")
    commit_interviewer_script(ctx, "\n".join(rows), stage_key="optimal_questions")


def ingest_vo_pickup(ctx: RunContext) -> None:
    """Validate VO files exist; optionally normalize loudness for mix."""
    import subprocess

    from interview_mux.config import merged_config

    report = ctx.read_json("understanding/gap_report.json")
    pickup = ctx.final_path("vo_pickup")
    missing = []
    normalized = 0
    mix_cfg = merged_config().get("mix") or {}
    normalize = bool(mix_cfg.get("normalize_vo_pickup", True))
    adjacent_match = mix_cfg.get("vo_adjacent_level_match") or {}
    skip_absolute_loudnorm = bool(
        isinstance(adjacent_match, dict) and adjacent_match.get("enabled", False)
    )
    with logged_step("vo_ingest/validate_pickups", ctx=ctx, stage="vo_ingest"):
        from interview_mux.stages.assembly import resolve_vo_pickup_path

        for line in report.get("interviewer_lines") or []:
            delivery = str(line.get("delivery") or "").lower()
            if delivery not in {"record", "synthesize"}:
                continue
            if line.get("skipped_optional"):
                continue
            lid = line.get("line_id", "")
            found = resolve_vo_pickup_path(ctx, line)
            if not found:
                missing.append(lid or line.get("targets_segment_id", ""))
                continue
            if normalize and found.parent == pickup:
                norm_dir = pickup / "normalized"
                norm_dir.mkdir(parents=True, exist_ok=True)
                out = norm_dir / found.name
                from interview_mux.operator_subprocess import run_command

                if skip_absolute_loudnorm:
                    # Adjacent-native level match in mix owns loudness — only
                    # peak-sanitize / resample / mono-copy here.
                    run_command(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            str(found),
                            "-af",
                            "aresample=48000,pan=mono|c0=c0",
                            "-ar",
                            "48000",
                            "-ac",
                            "1",
                            "-c:a",
                            "pcm_s16le",
                            str(out),
                        ],
                        ctx=ctx,
                        stage="vo_ingest",
                        label=f"ffmpeg peak-sanitize pickup {found.name}",
                        capture_output=True,
                    )
                else:
                    run_command(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            str(found),
                            "-af",
                            "loudnorm=I=-18:TP=-1.5:LRA=11",
                            "-ar",
                            "48000",
                            "-ac",
                            "1",
                            "-c:a",
                            "pcm_s16le",
                            str(out),
                        ],
                        ctx=ctx,
                        stage="vo_ingest",
                        label=f"ffmpeg normalize pickup {found.name}",
                        capture_output=True,
                    )
                normalized += 1
    if missing:
        raise RuntimeError(
            f"Missing VO pickup files for: {missing}. "
            f"Record and place under {pickup}"
        )
    if normalized:
        ctx.log(
            f"vo_ingest: normalized {normalized} pickup WAV(s) under vo_pickup/normalized/",
            level="info",
            stage="vo_ingest",
        )
    else:
        ctx.log("vo_ingest: all pickup WAVs already normalized.", level="info", stage="vo_ingest")
    try:
        from interview_mux.asset_transcripts import sync_vo_sidecars_from_gap_report

        sync_vo_sidecars_from_gap_report(ctx)
    except Exception as exc:
        ctx.log(f"VO sidecar sync skipped: {exc}", level="warning", stage="vo_ingest")
    ctx.mark_done("vo_ingest")
