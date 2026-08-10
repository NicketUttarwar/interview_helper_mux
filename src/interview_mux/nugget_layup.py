"""Nugget Layup System — flagship full-tape mining → per-native pre-VO lay-ups.

Authoritative planner for contentful ``before`` synthetic VO. Publishes into
``understanding/gap_report.json`` for G1 synthesis and EDL placement.
"""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

CORPUS_REL = "understanding/nugget_corpus.json"
PLAN_REL = "understanding/nugget_layup_plan.json"
GAP_REL = "understanding/gap_report.json"
QC_REL = "understanding/nugget_layup_qc.json"


def nugget_layup_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    root = cfg if isinstance(cfg, dict) else merged_config()
    analysis = root.get("analysis") if isinstance(root.get("analysis"), dict) else {}
    block = analysis.get("nugget_layup") if isinstance(analysis.get("nugget_layup"), dict) else {}
    return {
        "enabled": bool(block.get("enabled", True)),
        "require_layup_per_native": bool(block.get("require_layup_per_native", True)),
        "min_layup_coverage": float(block.get("min_layup_coverage", 0.9)),
        "min_layup_words": int(block.get("min_layup_words", 18)),
        "max_layup_words": int(block.get("max_layup_words", 90)),
        "prefer_excluded_nuggets": bool(block.get("prefer_excluded_nuggets", True)),
        "segment_text_max_chars": int(block.get("segment_text_max_chars", 420)),
        "suppress_placeholder_seams_when_layup": bool(
            block.get("suppress_placeholder_seams_when_layup", True)
        ),
        "demote_synthetic_framing_content": bool(
            block.get("demote_synthetic_framing_content", True)
        ),
        "authoritative_gap_report": bool(block.get("authoritative_gap_report", True)),
        "block_on_open_must_keep": bool(block.get("block_on_open_must_keep", True)),
        "honor_information_package_dense_budget": bool(
            block.get("honor_information_package_dense_budget", True)
        ),
    }


def nugget_layup_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(nugget_layup_cfg(cfg).get("enabled", True))


def _ordered_ids(ctx: RunContext) -> list[str]:
    if not ctx.artifact_exists("master/selection.json"):
        return []
    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        return []
    return [str(x) for x in (sel.get("ordered_segment_ids") or []) if x]


def _manifest_segments(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return []
    man = ctx.read_json("segments/manifest.json")
    if not isinstance(man, dict):
        return []
    rows = man.get("segments") or []
    return [r for r in rows if isinstance(r, dict)]


def _clip_text(text: str, max_chars: int) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= max_chars:
        return t
    return t[: max(0, max_chars - 1)].rstrip() + "…"


def build_corpus_mine_input(ctx: RunContext) -> dict[str, Any]:
    """Compact full-tape packet for flagship corpus mining."""
    cfg = nugget_layup_cfg()
    max_chars = int(cfg["segment_text_max_chars"])
    ordered = _ordered_ids(ctx)
    oset = set(ordered)
    segments: list[dict[str, Any]] = []
    for row in _manifest_segments(ctx):
        sid = str(row.get("segment_id") or "")
        if not sid:
            continue
        segments.append(
            {
                "segment_id": sid,
                "speaker_id": row.get("speaker_id"),
                "speaker_role": row.get("speaker_role"),
                "start_ms": row.get("start_ms"),
                "end_ms": row.get("end_ms"),
                "type": row.get("type"),
                "in_selection": sid in oset,
                "text": _clip_text(str(row.get("text") or ""), max_chars),
            }
        )
    talking_points = (
        ctx.read_json("understanding/talking_points.json")
        if ctx.artifact_exists("understanding/talking_points.json")
        else {}
    )
    ideal_cuts = (
        ctx.read_json("understanding/ideal_cuts.json")
        if ctx.artifact_exists("understanding/ideal_cuts.json")
        else {}
    )
    gap_evals = (
        ctx.read_json("understanding/gap_evaluations.json")
        if ctx.artifact_exists("understanding/gap_evaluations.json")
        else {}
    )
    content_brief = (
        ctx.read_json("understanding/content_brief.json")
        if ctx.artifact_exists("understanding/content_brief.json")
        else {}
    )
    return {
        "ordered_segment_ids": ordered,
        "segments": segments,
        "talking_points": talking_points if isinstance(talking_points, dict) else {},
        "ideal_cuts": ideal_cuts if isinstance(ideal_cuts, dict) else {},
        "gap_evaluations_hint": _compact_gap_evals(gap_evals if isinstance(gap_evals, dict) else {}),
        "content_brief": {
            "thesis": (content_brief or {}).get("thesis") if isinstance(content_brief, dict) else None,
            "topics": (content_brief or {}).get("topics") if isinstance(content_brief, dict) else [],
            "key_claims": (content_brief or {}).get("key_claims") if isinstance(content_brief, dict) else [],
        },
        "prefer_excluded_nuggets": bool(cfg["prefer_excluded_nuggets"]),
    }


def _compact_gap_evals(doc: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in doc.get("evaluations") or []:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "segment_id": row.get("segment_id"),
                "gap_type": row.get("gap_type"),
                "severity": row.get("severity"),
                "recommended_framing": row.get("recommended_framing"),
                "listener_confusion": _clip_text(str(row.get("listener_confusion") or ""), 180),
            }
        )
        if len(out) >= 80:
            break
    return out


def build_layup_compose_input(ctx: RunContext) -> dict[str, Any]:
    """Packet for per-native lay-up composition."""
    cfg = nugget_layup_cfg()
    max_chars = int(cfg["segment_text_max_chars"])
    ordered = _ordered_ids(ctx)
    by_id = {
        str(r.get("segment_id")): r
        for r in _manifest_segments(ctx)
        if r.get("segment_id")
    }
    natives: list[dict[str, Any]] = []
    for sid in ordered:
        row = by_id.get(sid) or {}
        natives.append(
            {
                "segment_id": sid,
                "speaker_id": row.get("speaker_id"),
                "type": row.get("type"),
                "start_ms": row.get("start_ms"),
                "end_ms": row.get("end_ms"),
                "text": _clip_text(str(row.get("text") or ""), max_chars),
            }
        )
    corpus = ctx.read_json(CORPUS_REL) if ctx.artifact_exists(CORPUS_REL) else {"nuggets": []}
    talking_points = (
        ctx.read_json("understanding/talking_points.json")
        if ctx.artifact_exists("understanding/talking_points.json")
        else {}
    )
    dense_targets: dict[str, Any] = {}
    dense_max = int(cfg["max_layup_words"])
    if cfg.get("honor_information_package_dense_budget", True):
        try:
            from interview_mux.information_packages import (
                dense_targets_from_plan,
                information_packages_cfg,
                packages_affect_air,
            )

            if packages_affect_air() and ctx.artifact_exists("mastering/mastering_plan.json"):
                mp = ctx.read_json("mastering/mastering_plan.json")
                dense_targets = dense_targets_from_plan(mp if isinstance(mp, dict) else {})
                dense_max = int(
                    information_packages_cfg().get("dense_max_layup_words") or max(dense_max, 140)
                )
        except Exception:
            dense_targets = {}
    return {
        "ordered_segment_ids": ordered,
        "natives": natives,
        "nugget_corpus": corpus if isinstance(corpus, dict) else {"nuggets": []},
        "talking_points": talking_points if isinstance(talking_points, dict) else {},
        "min_layup_words": int(cfg["min_layup_words"]),
        "max_layup_words": int(cfg["max_layup_words"]),
        "dense_max_layup_words": dense_max,
        "information_package_dense_targets": dense_targets,
        "require_layup_per_native": bool(cfg["require_layup_per_native"]),
        "prefer_excluded_nuggets": bool(cfg["prefer_excluded_nuggets"]),
    }


def _word_count(text: str) -> int:
    return len([w for w in str(text or "").split() if w])


def layup_line_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a plan layup row into a gap_report interviewer_line (or None if skip)."""
    if not isinstance(row, dict):
        return None
    if row.get("skip"):
        return None
    text = str(row.get("text") or "").strip()
    tid = str(row.get("target_segment_id") or "").strip()
    if not text or not tid:
        return None
    lid = str(row.get("line_id") or "").strip() or f"vo_layup_{tid}"
    nugget_ids = [str(x) for x in (row.get("nugget_ids") or []) if x]
    tp_ids = [str(x) for x in (row.get("talking_point_ids") or []) if x]
    detail_budget = str(row.get("detail_budget") or "").strip() or None
    line = {
        "line_id": lid,
        "gap_type": "nugget_layup",
        "line_category": "extracted_context",
        "text": text,
        "targets_segment_id": tid,
        "placement": "before",
        "delivery": "synthesize",
        "supports_segment_ids": [tid],
        "rationale": str(row.get("why_relevant_to_target") or "nugget_layup").strip(),
        "origin": "nugget_layup",
        "nugget_ids": nugget_ids,
        "recovery_of_talking_point_ids": tp_ids,
        "forward_cue_ok": bool(row.get("forward_cue_ok", True)),
        "word_count": int(row.get("word_count") or _word_count(text)),
        "severity": "high" if tp_ids or nugget_ids else "medium",
    }
    if detail_budget:
        line["detail_budget"] = detail_budget
    if row.get("information_package_id"):
        line["information_package_id"] = row.get("information_package_id")
    return line


def publish_layup_plan_to_gap_report(
    ctx: RunContext,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge lay-up before-VO into gap_report while preserving episode orientation."""
    from interview_mux.opening_orientation import (
        ensure_episode_orientation,
        is_episode_orientation,
    )
    from interview_mux.artifact_writes import write_validated_artifact

    if plan is None:
        plan = ctx.read_json(PLAN_REL) if ctx.artifact_exists(PLAN_REL) else {}
    if not isinstance(plan, dict):
        plan = {}

    existing = ctx.read_json(GAP_REL) if ctx.artifact_exists(GAP_REL) else {}
    if not isinstance(existing, dict):
        existing = {}
    prior_lines = [ln for ln in (existing.get("interviewer_lines") or []) if isinstance(ln, dict)]
    orientation = [ln for ln in prior_lines if is_episode_orientation(ln)]

    body: list[dict[str, Any]] = []
    seen_targets: set[str] = set()
    dense_meta: dict[str, dict[str, Any]] = {}
    try:
        from interview_mux.information_packages import (
            dense_targets_from_plan,
            packages_affect_air,
        )

        if packages_affect_air() and ctx.artifact_exists("mastering/mastering_plan.json"):
            mp = ctx.read_json("mastering/mastering_plan.json")
            dense_meta = dense_targets_from_plan(mp if isinstance(mp, dict) else {})
    except Exception:
        dense_meta = {}

    for row in plan.get("layups") or []:
        row_d = dict(row) if isinstance(row, dict) else {}
        tid = str(row_d.get("target_segment_id") or "").strip()
        if tid and tid in dense_meta:
            row_d["detail_budget"] = "dense"
            row_d["information_package_id"] = dense_meta[tid].get("package_id")
            # Prefer package-cited nuggets when the layup row is empty.
            if not row_d.get("nugget_ids") and dense_meta[tid].get("nugget_ids"):
                row_d["nugget_ids"] = list(dense_meta[tid]["nugget_ids"])
        line = layup_line_from_row(row_d)
        if not line:
            continue
        tid = str(line["targets_segment_id"])
        if tid in seen_targets:
            continue
        seen_targets.add(tid)
        body.append(line)

    # Keep non-orientation operator pins that are not superseded by a layup target.
    for ln in prior_lines:
        if is_episode_orientation(ln):
            continue
        if str(ln.get("origin") or "") == "operator":
            tid = str(ln.get("targets_segment_id") or "")
            if tid and tid not in seen_targets:
                body.append(ln)
                seen_targets.add(tid)

    report = {
        **{k: v for k, v in existing.items() if k not in ("interviewer_lines", "_meta")},
        "interviewer_lines": orientation + body,
        "nugget_layup_authority": True,
    }
    ordered = _ordered_ids(ctx)
    report, _notes = ensure_episode_orientation(ctx, report, ordered)
    write_validated_artifact(
        ctx,
        GAP_REL,
        report,
        merge_from_disk=False,
        stage_key="nugget_layup_compose",
    )
    return report


def gap_has_layup_before(gap_report: dict[str, Any] | None, segment_id: str) -> bool:
    """True when a contentful before-VO (layup or framing) targets this segment."""
    if not isinstance(gap_report, dict) or not segment_id:
        return False
    for ln in gap_report.get("interviewer_lines") or []:
        if not isinstance(ln, dict):
            continue
        if str(ln.get("placement") or "") != "before":
            continue
        if str(ln.get("targets_segment_id") or "") != segment_id:
            continue
        if not str(ln.get("text") or "").strip():
            continue
        # Orientation is not a per-native layup substitute for seam suppression
        # when it targets a different open segment — still counts for its target.
        return True
    return False


def normalize_layup_talking_point_ledger(
    ctx: RunContext, plan: dict[str, Any]
) -> dict[str, Any]:
    """Reconcile discharged/open talking-point ids before QC.

    LLMs often leave should_keep ids in ``open_talking_point_ids`` or list the
    same must_keep id in both open and discharged. Layup attachments win.
    """
    out = dict(plan) if isinstance(plan, dict) else {}
    layups = [r for r in (out.get("layups") or []) if isinstance(r, dict)]
    layup_tps = {
        str(x)
        for row in layups
        for x in (row.get("talking_point_ids") or [])
        if x
    }
    discharged = {
        str(x) for x in (out.get("discharged_talking_point_ids") or []) if x
    } | layup_tps
    must_keep_ids: set[str] = set()
    if ctx.artifact_exists("understanding/talking_points.json"):
        tp_doc = ctx.read_json("understanding/talking_points.json")
        for tp in (tp_doc.get("talking_points") or []) if isinstance(tp_doc, dict) else []:
            if not isinstance(tp, dict):
                continue
            if str(tp.get("importance") or "") != "must_keep":
                continue
            tpid = str(tp.get("talking_point_id") or "")
            if tpid:
                must_keep_ids.add(tpid)
    open_ids = []
    seen: set[str] = set()
    for raw in out.get("open_talking_point_ids") or []:
        tpid = str(raw or "")
        if not tpid or tpid in seen:
            continue
        seen.add(tpid)
        if tpid in must_keep_ids and tpid not in discharged:
            open_ids.append(tpid)
    for tpid in sorted(must_keep_ids):
        if tpid not in discharged and tpid not in seen:
            open_ids.append(tpid)
            seen.add(tpid)
    out["discharged_talking_point_ids"] = sorted(discharged)
    out["open_talking_point_ids"] = open_ids
    return out


def evaluate_layup_qc(
    ctx: RunContext,
    plan: dict[str, Any] | None = None,
    corpus: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Coverage / recovery QC for the lay-up plan."""
    cfg = nugget_layup_cfg()
    if plan is None:
        plan = ctx.read_json(PLAN_REL) if ctx.artifact_exists(PLAN_REL) else {}
    if corpus is None:
        corpus = ctx.read_json(CORPUS_REL) if ctx.artifact_exists(CORPUS_REL) else {}
    plan = normalize_layup_talking_point_ledger(ctx, plan if isinstance(plan, dict) else {})
    corpus = corpus if isinstance(corpus, dict) else {}

    ordered = [str(x) for x in (plan.get("ordered_segment_ids") or _ordered_ids(ctx)) if x]
    layups = [r for r in (plan.get("layups") or []) if isinstance(r, dict)]
    by_target = {str(r.get("target_segment_id") or ""): r for r in layups if r.get("target_segment_id")}

    present = 0
    skips: list[dict[str, Any]] = []
    missing: list[str] = []
    for sid in ordered:
        row = by_target.get(sid)
        if row is None:
            missing.append(sid)
            continue
        if row.get("skip") or not str(row.get("text") or "").strip():
            skips.append(
                {
                    "segment_id": sid,
                    "skip_reason_code": row.get("skip_reason_code") or "empty_or_skip",
                }
            )
            continue
        present += 1

    coverage = (present / len(ordered)) if ordered else 1.0
    open_must = [str(x) for x in (plan.get("open_talking_point_ids") or []) if x]

    open_high = [str(x) for x in (plan.get("open_high_salience_nugget_ids") or []) if x]
    for nug in corpus.get("nuggets") or []:
        if not isinstance(nug, dict):
            continue
        if nug.get("already_aired_in_selection"):
            continue
        sal = str(nug.get("salience") or "")
        if sal not in ("high", "critical"):
            continue
        if nug.get("in_selection") and not cfg.get("prefer_excluded_nuggets"):
            continue
        nid = str(nug.get("nugget_id") or "")
        if not nid:
            continue
        discharged_n = {str(x) for x in (plan.get("discharged_nugget_ids") or []) if x}
        waived = {
            str(x.get("nugget_id") or x)
            for x in (plan.get("waived_nugget_ids") or [])
            if isinstance(x, (dict, str))
        }
        assigned = False
        for row in layups:
            if nid in [str(x) for x in (row.get("nugget_ids") or [])]:
                assigned = True
                break
        if not assigned and nid not in discharged_n and nid not in waived and nid not in open_high:
            if not nug.get("in_selection"):
                open_high.append(nid)

    errors: list[str] = []
    if ordered and coverage + 1e-9 < float(cfg["min_layup_coverage"]):
        errors.append(
            f"layup_coverage={coverage:.3f} below min_layup_coverage={cfg['min_layup_coverage']}"
        )
    if missing and cfg.get("require_layup_per_native"):
        errors.append(f"missing_layup_rows={missing[:12]}")
    if open_must and cfg.get("block_on_open_must_keep"):
        errors.append(f"open_must_keep_talking_points={open_must[:12]}")

    return {
        "version": 1,
        "ordered_count": len(ordered),
        "layup_present_count": present,
        "layup_coverage": round(coverage, 4),
        "skips": skips,
        "missing_targets": missing,
        "open_must_keep_talking_point_ids": open_must,
        "open_high_salience_nugget_ids": open_high,
        "errors": errors,
        "ok": not errors,
    }


def assert_layup_qc_or_raise(ctx: RunContext, qc: dict[str, Any]) -> None:
    from interview_mux.artifact_writes import write_validated_artifact

    # QC artifact may lack a dedicated schema validator — write via ctx.
    try:
        write_validated_artifact(
            ctx,
            QC_REL,
            qc,
            merge_from_disk=False,
            stage_key="nugget_layup_compose",
        )
    except Exception:
        ctx.write_json(QC_REL, qc)
    if qc.get("ok"):
        return
    from interview_mux.loud_fail import raise_loud_failure

    raise_loud_failure(
        ctx,
        "Nugget layup QC failed: " + "; ".join(str(e) for e in (qc.get("errors") or [])[:8]),
        stage="nugget_layup_compose",
        reason="nugget_layup_qc_failed",
    )
