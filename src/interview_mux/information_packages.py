"""Shape information packages + required episode-close music.

Canon: docs/cross-cutting/information-packages.md
Mid-body packages (0–2, high bar) are optional. Episode-close theme_outro is always required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

CANDIDATES_REL = "mastering/shape/information_package_candidates.json"
AUDIT_REL = "mastering/shape/information_packages_audit.json"
PLAN_REL = "mastering/mastering_plan.json"
CORPUS_REL = "understanding/nugget_corpus.json"
SELECTION_REL = "master/selection.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def information_packages_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    root = cfg if isinstance(cfg, dict) else merged_config()
    mastering = root.get("mastering") if isinstance(root.get("mastering"), dict) else {}
    shape = mastering.get("shape") if isinstance(mastering.get("shape"), dict) else {}
    block = shape.get("information_packages") if isinstance(shape.get("information_packages"), dict) else {}
    close = shape.get("episode_close") if isinstance(shape.get("episode_close"), dict) else {}
    return {
        "enable": bool(block.get("enable", True)),
        "mode": str(block.get("mode") or "shadow"),
        "max_per_episode": int(block.get("max_per_episode") or 2),
        "min_novelty": float(block.get("min_novelty") or 0.75),
        "min_necessity": float(block.get("min_necessity") or 0.75),
        "min_listen_uplift": float(block.get("min_listen_uplift") or 0.7),
        "min_dense_words": int(block.get("min_dense_words") or 55),
        "min_nugget_count": int(block.get("min_nugget_count") or 2),
        "min_seam_gap_segments": int(block.get("min_seam_gap_segments") or 2),
        "allow_regroup": bool(block.get("allow_regroup", False)),
        "require_corpus": bool(block.get("require_corpus", True)),
        "min_ms_from_bookends": int(block.get("min_ms_from_bookends") or 45_000),
        "dense_max_layup_words": int(block.get("dense_max_layup_words") or 140),
        "episode_close": {
            "require_music": bool(close.get("require_music", True)),
            "role": str(close.get("role") or "theme_outro"),
            "fade_out_ms": int(close.get("fade_out_ms") or 2200),
            "may_underscore_last_native_tail": bool(
                close.get("may_underscore_last_native_tail", True)
            ),
            "placement": str(close.get("placement") or "after_last_native"),
        },
    }


def default_episode_close() -> dict[str, Any]:
    cfg = information_packages_cfg()["episode_close"]
    return {
        "music": {
            "required": bool(cfg["require_music"]),
            "role": str(cfg["role"]),
            "placement": str(cfg["placement"]),
            "fade_out": "gentle_long",
            "fade_out_ms": int(cfg["fade_out_ms"]),
            "may_underscore_last_native_tail": bool(cfg["may_underscore_last_native_tail"]),
        },
        "rationale": "Signal episode complete with an enjoyable resolving cadence",
        "evidence_refs": ["mastering/shape/agenda.json"],
        "confidence": 1.0,
    }


def ensure_episode_close_on_plan(plan: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(plan) if isinstance(plan, dict) else {}
    existing = out.get("episode_close")
    if not isinstance(existing, dict) or not isinstance(existing.get("music"), dict):
        out["episode_close"] = default_episode_close()
        return out
    music = dict(existing.get("music") or {})
    defaults = default_episode_close()["music"]
    music.setdefault("required", defaults["required"])
    music.setdefault("role", defaults["role"])
    music.setdefault("placement", defaults["placement"])
    music.setdefault("fade_out", defaults["fade_out"])
    music.setdefault("fade_out_ms", defaults["fade_out_ms"])
    music.setdefault(
        "may_underscore_last_native_tail", defaults["may_underscore_last_native_tail"]
    )
    out["episode_close"] = {
        **existing,
        "music": music,
        "rationale": existing.get("rationale") or default_episode_close()["rationale"],
        "evidence_refs": list(existing.get("evidence_refs") or default_episode_close()["evidence_refs"]),
        "confidence": float(existing.get("confidence") if existing.get("confidence") is not None else 1.0),
    }
    return out


def _ordered_ids(ctx: RunContext) -> list[str]:
    if not ctx.artifact_exists(SELECTION_REL):
        return []
    sel = ctx.read_json(SELECTION_REL)
    if not isinstance(sel, dict):
        return []
    return [str(x) for x in (sel.get("ordered_segment_ids") or []) if x]


def _manifest_by_id(ctx: RunContext) -> dict[str, dict[str, Any]]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return {}
    man = ctx.read_json("segments/manifest.json")
    rows = (man.get("segments") or []) if isinstance(man, dict) else []
    return {
        str(r.get("segment_id")): r
        for r in rows
        if isinstance(r, dict) and r.get("segment_id")
    }


def _corpus_nuggets(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists(CORPUS_REL):
        return []
    doc = ctx.read_json(CORPUS_REL)
    if not isinstance(doc, dict):
        return []
    return [n for n in (doc.get("nuggets") or []) if isinstance(n, dict)]


def _topic_key(row: dict[str, Any]) -> str:
    tags = row.get("topic_tags") or row.get("topics") or []
    if isinstance(tags, list) and tags:
        bits = []
        for t in tags[:3]:
            if isinstance(t, dict):
                bits.append(str(t.get("name") or t.get("label") or "").lower())
            else:
                bits.append(str(t).lower())
        joined = "|".join(b for b in bits if b)
        if joined:
            return joined
    text = str(row.get("text") or "").lower()
    words = [w for w in text.split() if len(w) > 4][:4]
    return " ".join(words)


def _source_contiguous(prev: dict[str, Any], nxt: dict[str, Any]) -> bool:
    try:
        prev_end = int(prev.get("end_ms") or 0)
        nxt_start = int(nxt.get("start_ms") or 0)
    except Exception:
        return True
    return abs(nxt_start - prev_end) <= 2500


def score_seam(
    *,
    after_id: str,
    before_id: str,
    after_row: dict[str, Any],
    before_row: dict[str, Any],
    unused_nuggets: list[dict[str, Any]],
    is_final_seam: bool,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic objective scores for one post-native seam."""
    reject: list[str] = []
    if is_final_seam:
        reject.append("final_seam_reserved_for_episode_close")

    unused_high = [
        n
        for n in unused_nuggets
        if not bool(n.get("in_selection"))
        and str(n.get("salience") or "").lower() in {"high", "must_keep", "critical"}
    ]
    unused_any = [n for n in unused_nuggets if not bool(n.get("in_selection"))]
    pool = unused_high or unused_any
    nugget_count = len(pool)
    novelty = min(1.0, nugget_count / max(1.0, float(cfg["min_nugget_count"]) * 1.5))
    if nugget_count < int(cfg["min_nugget_count"]):
        reject.append("insufficient_unused_nuggets")

    topic_shift = _topic_key(after_row) != _topic_key(before_row) and bool(
        _topic_key(after_row) and _topic_key(before_row)
    )
    jump = not _source_contiguous(after_row, before_row)
    necessity = 0.35
    if topic_shift:
        necessity += 0.35
    if jump:
        necessity += 0.25
    if nugget_count >= int(cfg["min_nugget_count"]) + 1:
        necessity += 0.15
    necessity = min(1.0, necessity)
    if necessity + 1e-9 < float(cfg["min_necessity"]):
        reject.append("necessity_below_floor")

    est_words = min(200, max(20, nugget_count * 28 + (18 if topic_shift else 0) + (12 if jump else 0)))
    if est_words < int(cfg["min_dense_words"]):
        reject.append("magnitude_below_dense_words")

    uplift = 0.4
    if topic_shift and nugget_count >= int(cfg["min_nugget_count"]):
        uplift += 0.25
    if jump:
        uplift += 0.15
    if unused_high:
        uplift += 0.15
    uplift = min(1.0, uplift)
    if uplift + 1e-9 < float(cfg["min_listen_uplift"]):
        reject.append("uplift_below_floor")
    if novelty + 1e-9 < float(cfg["min_novelty"]):
        reject.append("novelty_below_floor")

    would_commit = not reject
    cited = [str(n.get("nugget_id") or "") for n in pool[:4] if n.get("nugget_id")]
    claim = "; ".join(
        str(n.get("text_claim") or "")[:120] for n in pool[:2] if n.get("text_claim")
    )
    return {
        "after_segment_id": after_id,
        "before_segment_id": before_id,
        "before_segment_ids": [before_id],
        "gate_scores": {
            "novelty": round(novelty, 3),
            "necessity_for_next_block": round(necessity, 3),
            "listen_uplift": round(uplift, 3),
            "est_dense_words": est_words,
            "unused_nugget_count": nugget_count,
        },
        "topic_shift": topic_shift,
        "source_jump": jump,
        "nugget_ids": cited,
        "new_information_claim": claim or "unused corpus facts for upcoming block",
        "why_package_required": (
            "Music face-out + dense before-VO improves context for the next native block "
            f"(topic_shift={topic_shift}, source_jump={jump}, unused_nuggets={nugget_count})."
        ),
        "reject_reasons": reject,
        "would_commit": would_commit,
        "confidence": round(min(novelty, necessity, uplift), 3),
    }


def build_candidates(ctx: RunContext) -> dict[str, Any]:
    cfg = information_packages_cfg()
    ordered = _ordered_ids(ctx)
    by_id = _manifest_by_id(ctx)
    nuggets = _corpus_nuggets(ctx)
    candidates: list[dict[str, Any]] = []
    if len(ordered) < 2:
        return {
            "version": 1,
            "generated_at": _now(),
            "ordered_segment_ids": ordered,
            "candidates": [],
            "warnings": ["too_few_segments"],
        }
    for i in range(len(ordered) - 1):
        after_id = ordered[i]
        before_id = ordered[i + 1]
        is_final = i == len(ordered) - 2
        row = score_seam(
            after_id=after_id,
            before_id=before_id,
            after_row=by_id.get(after_id) or {},
            before_row=by_id.get(before_id) or {},
            unused_nuggets=nuggets,
            is_final_seam=is_final,
            cfg=cfg,
        )
        candidates.append(row)
    return {
        "version": 1,
        "generated_at": _now(),
        "ordered_segment_ids": ordered,
        "config_snapshot": {
            "mode": cfg["mode"],
            "max_per_episode": cfg["max_per_episode"],
            "min_novelty": cfg["min_novelty"],
            "min_necessity": cfg["min_necessity"],
            "min_listen_uplift": cfg["min_listen_uplift"],
        },
        "candidates": candidates,
    }


def select_commits(
    candidates_doc: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    cfg = cfg or information_packages_cfg()
    max_n = int(cfg["max_per_episode"])
    gap = int(cfg["min_seam_gap_segments"])
    viable = [
        c
        for c in (candidates_doc.get("candidates") or [])
        if isinstance(c, dict) and c.get("would_commit")
    ]
    viable.sort(
        key=lambda c: (
            -float((c.get("gate_scores") or {}).get("listen_uplift") or 0),
            -float((c.get("gate_scores") or {}).get("novelty") or 0),
        )
    )
    ordered = [str(x) for x in (candidates_doc.get("ordered_segment_ids") or []) if x]
    index = {sid: i for i, sid in enumerate(ordered)}
    chosen: list[dict[str, Any]] = []
    chosen_idx: list[int] = []
    for c in viable:
        if len(chosen) >= max_n:
            break
        after = str(c.get("after_segment_id") or "")
        ai = index.get(after)
        if ai is None:
            continue
        if any(abs(ai - oi) < gap for oi in chosen_idx):
            continue
        chosen.append(c)
        chosen_idx.append(ai)
    return chosen


def package_from_candidate(cand: dict[str, Any], *, idx: int) -> dict[str, Any]:
    before_ids = [str(x) for x in (cand.get("before_segment_ids") or []) if x]
    if not before_ids and cand.get("before_segment_id"):
        before_ids = [str(cand["before_segment_id"])]
    target = before_ids[0] if before_ids else ""
    return {
        "package_id": f"info_pkg_{idx}",
        "after_segment_id": str(cand.get("after_segment_id") or ""),
        "before_segment_ids": before_ids,
        "music": {
            "faceout_role": "theme_chapter_resolve",
            "gentle_transition": True,
        },
        "vo": {
            "placement": "before",
            "targets_segment_id": target,
            "detail_budget": "dense",
            "nugget_ids": list(cand.get("nugget_ids") or []),
        },
        "new_information_claim": str(cand.get("new_information_claim") or ""),
        "why_package_required": str(cand.get("why_package_required") or ""),
        "evidence_refs": [CORPUS_REL] + [f"{CORPUS_REL}#{nid}" for nid in (cand.get("nugget_ids") or [])[:4]],
        "confidence": float(cand.get("confidence") or 0.0),
        "gate_scores": dict(cand.get("gate_scores") or {}),
    }


def packages_affect_air(cfg: dict[str, Any] | None = None) -> bool:
    cfg = cfg or information_packages_cfg()
    if not cfg.get("enable", True):
        return False
    return str(cfg.get("mode") or "shadow") in {"commit_music_vo", "commit_with_regroup"}


def committed_packages_from_plan(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(plan, dict):
        return []
    return [p for p in (plan.get("information_packages") or []) if isinstance(p, dict)]


def dense_targets_from_plan(plan: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Map targets_segment_id → package vo metadata for layup dense budget."""
    out: dict[str, dict[str, Any]] = {}
    for pkg in committed_packages_from_plan(plan):
        vo = pkg.get("vo") if isinstance(pkg.get("vo"), dict) else {}
        tid = str(vo.get("targets_segment_id") or "")
        if not tid:
            continue
        if str(vo.get("detail_budget") or "") != "dense":
            continue
        out[tid] = {
            "package_id": pkg.get("package_id"),
            "nugget_ids": list(vo.get("nugget_ids") or []),
            "detail_budget": "dense",
        }
    return out


def patch_mastering_plan(
    ctx: RunContext,
    packages: list[dict[str, Any]],
    *,
    mode: str,
) -> dict[str, Any]:
    plan: dict[str, Any] = {}
    if ctx.artifact_exists(PLAN_REL):
        raw = ctx.read_json(PLAN_REL)
        if isinstance(raw, dict):
            plan = dict(raw)
    plan = ensure_episode_close_on_plan(plan)
    if mode in {"commit_music_vo", "commit_with_regroup"}:
        plan["information_packages"] = packages
    else:
        # Shadow: do not bind air packages; keep empty list on plan.
        plan["information_packages"] = []
    # Preserve grammar hint when packages would commit.
    grammar = list(plan.get("montage_grammar") or [])
    if packages and "information_package_then_block" not in grammar:
        if mode != "shadow":
            grammar.append("information_package_then_block")
            plan["montage_grammar"] = grammar
    ctx.write_json(PLAN_REL, plan)
    return plan


def run_information_package_plan(ctx: RunContext) -> None:
    """Score seams, audit, optionally commit ≤2 packages onto mastering_plan."""
    cfg = information_packages_cfg()
    candidates = build_candidates(ctx)
    corpus_missing = bool(cfg.get("require_corpus") and not _corpus_nuggets(ctx))
    if corpus_missing:
        for c in candidates.get("candidates") or []:
            if isinstance(c, dict):
                c["would_commit"] = False
                reasons = list(c.get("reject_reasons") or [])
                if "corpus_missing" not in reasons:
                    reasons.append("corpus_missing")
                c["reject_reasons"] = reasons
        candidates["warnings"] = list(candidates.get("warnings") or []) + ["corpus_missing_or_empty"]

    ctx.write_json(CANDIDATES_REL, candidates)

    if not cfg.get("enable", True):
        plan = ensure_episode_close_on_plan(
            ctx.read_json(PLAN_REL) if ctx.artifact_exists(PLAN_REL) else {}
        )
        plan["information_packages"] = []
        ctx.write_json(PLAN_REL, plan)
        ctx.write_json(
            AUDIT_REL,
            {
                "version": 1,
                "generated_at": _now(),
                "mode": "disabled",
                "would_commit": [],
                "committed": [],
                "episode_close": plan.get("episode_close"),
            },
        )
        from interview_mux.stage_completion import heal_or_raise

        heal_or_raise(ctx, "information_package_plan")
        return

    # IPP-B2: still write audit evidence, but refuse done when require_corpus + empty.
    if corpus_missing and cfg.get("enable", True):
        plan = ensure_episode_close_on_plan(
            ctx.read_json(PLAN_REL) if ctx.artifact_exists(PLAN_REL) else {}
        )
        plan["information_packages"] = []
        ctx.write_json(PLAN_REL, plan)
        ctx.write_json(
            AUDIT_REL,
            {
                "version": 1,
                "generated_at": _now(),
                "mode": str(cfg.get("mode") or "shadow"),
                "would_commit": [],
                "committed": [],
                "warnings": ["corpus_missing_or_empty"],
                "episode_close": plan.get("episode_close"),
            },
        )
        from interview_mux.stage_completion import heal_or_raise

        heal_or_raise(ctx, "information_package_plan")
        return

    selected = select_commits(candidates, cfg=cfg)
    packages = [package_from_candidate(c, idx=i + 1) for i, c in enumerate(selected)]
    mode = str(cfg.get("mode") or "shadow")
    # Phase-1: regroup disabled even in commit_with_regroup until allow_regroup.
    if mode == "commit_with_regroup" and not cfg.get("allow_regroup"):
        mode = "commit_music_vo"

    plan = patch_mastering_plan(ctx, packages, mode=mode)
    audit = {
        "version": 1,
        "generated_at": _now(),
        "mode": mode,
        "config": {
            "max_per_episode": cfg["max_per_episode"],
            "allow_regroup": cfg["allow_regroup"],
        },
        "would_commit": packages,
        "committed": packages if packages_affect_air({**cfg, "mode": mode}) else [],
        "rejected_count": sum(
            1
            for c in (candidates.get("candidates") or [])
            if isinstance(c, dict) and not c.get("would_commit")
        ),
        "episode_close": plan.get("episode_close"),
        "regroup_applied": False,
    }
    ctx.write_json(AUDIT_REL, audit)
    from interview_mux.stage_completion import heal_or_raise

    heal_or_raise(ctx, "information_package_plan")


def count_before_vo_for_target(gap_report: dict[str, Any] | None, segment_id: str) -> int:
    from interview_mux.opening_orientation import is_episode_orientation

    if not isinstance(gap_report, dict) or not segment_id:
        return 0
    n = 0
    for ln in gap_report.get("interviewer_lines") or []:
        if not isinstance(ln, dict):
            continue
        if is_episode_orientation(ln):
            continue
        if str(ln.get("placement") or "") != "before":
            continue
        if str(ln.get("targets_segment_id") or "") != segment_id:
            continue
        if not str(ln.get("text") or "").strip():
            continue
        n += 1
    return n
