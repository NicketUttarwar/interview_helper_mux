"""Context-rich synthetic framing planned only after native selection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.artifact_completeness import make_stage_persist
from interview_mux.run_context import RunContext
from interview_mux.stage_enrichment import compact_manifest_for_volley
from interview_mux.stage_completion import heal_or_refuse_mark

CONTEXT_REL = "understanding/synthetic_context_packet.json"
PLAN_REL = "understanding/synthetic_framing_plan.json"
STAGE_ID = "synthetic_framing_plan"
PROMPT_REL = "assembly/synthetic-framing-plan.system.txt"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def synthetic_framing_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    from interview_mux.config import merged_config

    raw = ((cfg or merged_config()).get("mastering") or {}).get("synthetic_framing") or {}
    defaults = {
        "respect_native_speakers": True,
        "allow_canned_bridge_fallback": False,
        "duration_ratio_min": 0.4,
        "duration_ratio_max": 2.0,
    }
    return {**defaults, **(raw if isinstance(raw, dict) else {})}


def _ratio_bounds(cfg: dict[str, Any] | None = None) -> tuple[float, float]:
    conf = synthetic_framing_cfg(cfg)
    try:
        low = float(conf.get("duration_ratio_min") or 0.4)
        high = float(conf.get("duration_ratio_max") or 2.0)
    except (TypeError, ValueError):
        return 0.4, 2.0
    if high < low:
        return 0.4, 2.0
    return low, high


def _compact_gap_evaluations(value: dict[str, Any]) -> dict[str, Any]:
    """Keep placement/severity signal; drop long rationales that blow the volley."""
    rows: list[dict[str, Any]] = []
    for row in value.get("evaluations") or []:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "segment_id": row.get("segment_id"),
                "gap_type": row.get("gap_type"),
                "secondary_gap_type": row.get("secondary_gap_type"),
                "severity": row.get("severity"),
                "self_explanatory": row.get("self_explanatory"),
                "recommended_framing": row.get("recommended_framing"),
                "candidate_for_summary": row.get("candidate_for_summary"),
            }
        )
    return {"evaluations": rows, "_compacted_for": STAGE_ID}


def _compact_content_brief(value: dict[str, Any]) -> dict[str, Any]:
    """Keep spine fields; drop bulky digests that do not steer seam framing."""
    out: dict[str, Any] = {"_compacted_for": STAGE_ID}
    for key in (
        "thesis",
        "logline",
        "title",
        "subtitle",
        "episode_promise",
        "audience",
        "tone",
        "narrative_mode",
        "guest_name",
        "host_name",
    ):
        if key in value:
            out[key] = value[key]
    topics = value.get("topics")
    if isinstance(topics, list):
        slim_topics: list[Any] = []
        for t in topics[:12]:
            if isinstance(t, dict):
                slim_topics.append(
                    {
                        "topic_id": t.get("topic_id") or t.get("id"),
                        "label": t.get("label") or t.get("name") or t.get("title"),
                        "summary": str(t.get("summary") or t.get("blurb") or "")[:180],
                    }
                )
            elif t:
                slim_topics.append(str(t)[:120])
        out["topics"] = slim_topics
    claims = value.get("key_claims")
    if isinstance(claims, list):
        out["key_claims"] = [
            (c if isinstance(c, str) else str((c or {}).get("claim") or c))[:160]
            for c in claims[:12]
        ]
    beats = value.get("emotional_beats")
    if isinstance(beats, list):
        out["emotional_beats"] = [
            (b if isinstance(b, str) else str((b or {}).get("label") or b))[:120]
            for b in beats[:8]
        ]
    gloss = value.get("jargon_glossary")
    if isinstance(gloss, list):
        out["jargon_glossary"] = gloss[:12]
    elif isinstance(gloss, dict):
        out["jargon_glossary"] = dict(list(gloss.items())[:12])
    return out


def _compact_optional_packet_value(key: str, value: dict[str, Any]) -> dict[str, Any]:
    if key == "prior_gap_report":
        from interview_mux.gap_framing import compact_gap_report_for_ranking

        compact = compact_gap_report_for_ranking(value)
        compact["_compacted_for"] = STAGE_ID
        return compact
    if key == "gap_evaluations":
        return _compact_gap_evaluations(value)
    if key == "content_brief":
        return _compact_content_brief(value)
    if key == "reorder_bridges":
        bridges = value.get("bridges") if isinstance(value.get("bridges"), list) else value.get("items")
        if isinstance(bridges, list):
            slim = []
            for row in bridges[:120]:
                if not isinstance(row, dict):
                    continue
                slim.append(
                    {
                        "after_segment_id": row.get("after_segment_id") or row.get("from_segment_id"),
                        "before_segment_id": row.get("before_segment_id") or row.get("to_segment_id"),
                        "kind": row.get("kind") or row.get("bridge_kind"),
                        "needed": row.get("needed"),
                    }
                )
            return {"bridges": slim, "_compacted_for": STAGE_ID}
    return value


def build_context_packet(ctx: RunContext) -> dict[str, Any]:
    selection = ctx.read_json("master/selection.json")
    if not isinstance(selection, dict):
        raise ValueError("master/selection.json required before synthetic framing")
    ordered = [str(x) for x in (selection.get("ordered_segment_ids") or []) if x]
    from interview_mux.order_hash import stamp_order_hash

    if not selection.get("order_content_hash"):
        selection = stamp_order_hash(selection)
        ctx.write_json("master/selection.json", selection, stage_key="full_master_ranking")
    ordered_hash = str(selection.get("order_content_hash") or "")
    manifest = (
        ctx.read_json("segments/manifest.json")
        if ctx.artifact_exists("segments/manifest.json")
        else {}
    )
    # Keep native excerpts short — full gap_report text previously pushed o3 over 128k.
    compact = compact_manifest_for_volley(
        manifest if isinstance(manifest, dict) else {}, text_max=160
    )
    segments = [
        row
        for row in (compact.get("segments") or [])
        if isinstance(row, dict) and str(row.get("segment_id") or "") in set(ordered)
    ]
    packet: dict[str, Any] = {
        "version": 1,
        "generated_at": _now(),
        "selection_order_content_hash": ordered_hash,
        "ordered_segment_ids": ordered,
        "selected_native_segments": segments,
        "native_duration_ms": sum(
            max(
                0,
                int(row.get("end_ms") or 0) - int(row.get("start_ms") or 0),
            )
            for row in segments
        ),
        "policy": {
            "plan_after_native_selection": True,
            "respect_native_speakers": bool(
                synthetic_framing_cfg().get("respect_native_speakers", True)
            ),
            "never_talk_over_guest_impact_or_dense_answer": True,
            "prefer_native_extension_or_air_when_continuity_is_good": True,
            "duration_ratio_min": _ratio_bounds()[0],
            "duration_ratio_max": _ratio_bounds()[1],
            "allow_canned_bridge_fallback": bool(
                synthetic_framing_cfg().get("allow_canned_bridge_fallback", False)
            ),
            "synthetic_input_share_guide_min": 0.2,
            "synthetic_input_share_guide_max": 0.8,
            "share_is_not_a_hard_cap": True,
            "speaker_policy": "current_host_clone",
            "music_preference": "contiguous_scene_beds",
        },
    }
    optional = {
        "mastering_plan": "mastering/mastering_plan.json",
        "narrative_plan": "master/narrative_plan.json",
        "coverage_audit": "master/coverage_audit.json",
        "content_brief": "understanding/content_brief.json",
        "gap_evaluations": "understanding/gap_evaluations.json",
        "prior_gap_report": "understanding/gap_report.json",
        "reorder_bridges": "understanding/reorder_bridges.json",
        "seam_autopsy": "master/seam_autopsy.json",
        "speaker_delivery_plan": "understanding/speaker_delivery_plan.json",
    }
    for key, rel in optional.items():
        if ctx.artifact_exists(rel):
            value = ctx.read_json(rel)
            if isinstance(value, dict):
                packet[key] = _compact_optional_packet_value(key, value)
    # Required reorder seams must be planned explicitly — no canned mint later.
    try:
        from interview_mux.bridge_completeness import missing_reorder_bridges
        from interview_mux.seam_glue import rebuild_reorder_bridges

        by_id = {
            str(row.get("segment_id")): row
            for row in (manifest.get("segments") or [])
            if isinstance(row, dict) and row.get("segment_id")
        }
        bridges = rebuild_reorder_bridges(ctx, ordered, by_id)
        gap = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else None
        )
        transitions = (
            ctx.read_json("master/transitions.json")
            if ctx.artifact_exists("master/transitions.json")
            else None
        )
        required = missing_reorder_bridges(
            bridges, gap_report=gap if isinstance(gap, dict) else None, transitions=transitions
        )
        packet["required_reorder_seams"] = required
    except Exception:
        packet["required_reorder_seams"] = []

    _commit_json(ctx, CONTEXT_REL, packet)
    return packet


def _commit_json(ctx: RunContext, rel: str, data: dict[str, Any]) -> None:
    """Persist even when nested under another stage's write-staging root."""
    try:
        from interview_mux.write_staging import write_committed_json

        write_committed_json(ctx, rel, data)
    except Exception:
        ctx.write_json(rel, data)


def _ordered_index(ordered_ids: list[str]) -> dict[str, int]:
    return {sid: i for i, sid in enumerate(ordered_ids) if sid}


def _is_stock_bridge_text(text: str) -> bool:
    from interview_mux.spoken_copy_guard import normalize_script

    clean = normalize_script(text).casefold()
    if not clean:
        return True
    if clean.startswith("turning to ") and clean.endswith(", what changed?"):
        return True
    if clean.startswith("moving from ") and clean.endswith(", what changed?"):
        return True
    if clean.startswith("with ") and clean.endswith(" established, what changed?"):
        return True
    return False


def _canonicalize_between_ids(
    row: dict[str, Any], index: dict[str, int]
) -> str | None:
    """Return drop reason, or None if row kept (possibly rewritten).

    Air order: after = prior native, before = next native, must be adjacent.
    """
    after = str(row.get("after_segment_id") or "")
    before = str(row.get("before_segment_id") or "")
    if not after and not before:
        return None
    if after and before and after == before:
        return "self_loop"
    if after and after not in index:
        row["after_segment_id"] = None
        after = ""
    if before and before not in index:
        row["before_segment_id"] = None
        before = ""
    if after and before:
        ia, ib = index[after], index[before]
        if ia > ib:
            row["after_segment_id"], row["before_segment_id"] = before, after
            after, before = before, after
            ia, ib = ib, ia
            row["adopted_seam_repair"] = "reversed"
        if ib != ia + 1:
            # Keep text+anchor for flexible adopt; clear wrong chronology.
            row["after_segment_id"] = None
            row["before_segment_id"] = None
            row.pop("adopted_seam_repair", None)
    return None


def _line_covers_pair(line: dict[str, Any], a: str, b: str) -> bool:
    return (
        str(line.get("placement") or "") == "between_segments"
        and str(line.get("after_segment_id") or "") == a
        and str(line.get("before_segment_id") or "") == b
        and bool(str(line.get("text") or "").strip())
    )


def _sole_cover_of_other_required(
    line: dict[str, Any],
    *,
    a: str,
    b: str,
    required_pairs: list[tuple[str, str]],
    cleaned: list[dict[str, Any]],
) -> bool:
    """True when this line is the only cover of a different required seam."""
    la = str(line.get("after_segment_id") or "")
    lb = str(line.get("before_segment_id") or "")
    if not la or not lb or (la, lb) == (a, b):
        return False
    if (la, lb) not in required_pairs:
        return False
    others = [
        row
        for row in cleaned
        if row is not line and _line_covers_pair(row, la, lb)
    ]
    return not others


def _bind_line_to_seam(
    line: dict[str, Any],
    *,
    a: str,
    b: str,
    repair: str,
    native_by_id: dict[str, dict[str, Any]],
    cleaned: list[dict[str, Any]],
    pair: dict[str, Any],
) -> bool:
    """Rewrite line onto air-order seam if spoken guard accepts. Mutates line."""
    from interview_mux.seam_glue import bridge_guard_evidence, enrich_bridge_pair_excerpts
    from interview_mux.spoken_copy_guard import assert_guarded_spoken_copy, normalize_script

    text = normalize_script(str(line.get("text") or ""))
    if not text:
        return False
    if line.get("auto_minted_seam") or _is_stock_bridge_text(text):
        # Prefer non-stock planned VO; stock may still bind only if nothing else can.
        if repair != "stock_ok":
            return False
    enriched = enrich_bridge_pair_excerpts(dict(pair), native_by_id)
    try:
        guarded = assert_guarded_spoken_copy(
            text,
            evidence=bridge_guard_evidence(enriched),
            purpose=f"synthetic_adopt[{a}->{b}]",
            seen_texts=[
                str(x.get("text") or "")
                for x in cleaned
                if x is not line and str(x.get("text") or "").strip()
            ],
        )
    except ValueError:
        return False
    if guarded.get("action") in {"block", "omit"}:
        return False
    violations = list(guarded.get("violations") or [])
    if any(
        v.split(":", 1)[0]
        in {
            "spoken_chronology_mismatch",
            "spoken_next_clip_restatement",
            "spoken_path_or_filename",
            "spoken_production_jargon",
            "spoken_placeholder",
            "spoken_malformed_fragment",
        }
        for v in violations
    ):
        return False
    line["placement"] = "between_segments"
    line["after_segment_id"] = a
    line["before_segment_id"] = b
    line["role"] = line.get("role") or "bridge"
    if a and not str(line.get("anchor_segment_id") or ""):
        line["anchor_segment_id"] = a
    line["text"] = str(guarded.get("text") or text)
    line["adopted_seam_repair"] = repair
    line["spoken_copy_guard"] = {
        "action": guarded.get("action"),
        "script_hash": guarded.get("script_hash"),
        "context_hash": guarded.get("context_hash"),
    }
    line.pop("auto_minted_seam", None)
    return True


def _candidate_rank_key(line: dict[str, Any], a: str, b: str) -> tuple[int, int]:
    """Lower is better. Prefer exact, reverse, following, prior, then anchor."""
    la = str(line.get("after_segment_id") or "")
    lb = str(line.get("before_segment_id") or "")
    anchor = str(line.get("anchor_segment_id") or "")
    text = str(line.get("text") or "")
    stock = 1 if (line.get("auto_minted_seam") or _is_stock_bridge_text(text)) else 0
    if la == a and lb == b:
        return (0, stock)
    if la == b and lb == a:
        return (1, stock)
    if lb == b:
        return (2, stock)
    if la == a:
        return (3, stock)
    if anchor in {a, b}:
        return (4, stock)
    return (9, stock)


def normalize_synthetic_plan(
    ctx: RunContext, plan: dict[str, Any], packet: dict[str, Any]
) -> dict[str, Any]:
    """Force the plan onto the frozen native selection before validation."""
    out = dict(plan)
    out["selection_order_content_hash"] = packet.get("selection_order_content_hash")
    out["generated_at"] = _now()
    ordered_list = [str(x) for x in (packet.get("ordered_segment_ids") or []) if x]
    ordered = set(ordered_list)
    index = _ordered_index(ordered_list)
    native_by_id = {
        str(row.get("segment_id")): row
        for row in (packet.get("selected_native_segments") or [])
        if isinstance(row, dict) and row.get("segment_id")
    }
    cleaned: list[dict[str, Any]] = []
    for index_i, line in enumerate(out.get("lines") or []):
        if not isinstance(line, dict):
            continue
        row = dict(line)
        anchor = str(row.get("anchor_segment_id") or "")
        if anchor not in ordered:
            continue
        after = str(row.get("after_segment_id") or "")
        before = str(row.get("before_segment_id") or "")
        if after and after not in ordered:
            row["after_segment_id"] = None
        if before and before not in ordered:
            row["before_segment_id"] = None
        drop = _canonicalize_between_ids(row, index)
        if drop == "self_loop":
            ctx.log(
                f"synthetic_framing: dropped self-loop line {row.get('line_id')}",
                level="info",
                stage=STAGE_ID,
            )
            continue
        try:
            ratio = float(row.get("duration_ratio"))
        except (TypeError, ValueError):
            ratio = 1.0
        ratio_min, ratio_max = _ratio_bounds()
        ratio = max(ratio_min, min(ratio_max, ratio))
        row["duration_ratio"] = ratio
        native = native_by_id.get(anchor) or {}
        native_ms = max(
            250,
            int(native.get("end_ms") or 0) - int(native.get("start_ms") or 0),
        )
        try:
            target = int(row.get("target_duration_ms") or 0)
        except (TypeError, ValueError):
            target = 0
        if target < 250:
            target = int(native_ms * ratio)
        row["target_duration_ms"] = max(250, target)
        row["native_respect_violation"] = False
        if not str(row.get("comprehension_reason") or "").strip():
            row["comprehension_reason"] = (
                f"Orientation for selected native segment {anchor}"
            )
        if not str(row.get("line_id") or "").strip():
            row["line_id"] = f"syn_{index_i:03d}_{anchor}"
        if row.get("speaker_policy") is None:
            row["speaker_policy"] = ""
        elif not isinstance(row.get("speaker_policy"), str):
            row["speaker_policy"] = str(row.get("speaker_policy") or "")
        if not str(row.get("text") or "").strip():
            continue
        from interview_mux.spoken_copy_guard import guard_spoken_copy

        after_row = native_by_id.get(str(row.get("after_segment_id") or "")) or {}
        before_row = native_by_id.get(str(row.get("before_segment_id") or "")) or {}
        evidence = {
            "after_excerpt": after_row.get("text") or after_row.get("text_excerpt"),
            "before_excerpt": before_row.get("text") or before_row.get("text_excerpt"),
            "target_excerpt": native.get("text") or native.get("text_excerpt"),
            "source_gap_ms": row.get("source_gap_ms"),
            "strict_grounding": True,
        }
        required_line = str(row.get("placement") or "") == "between_segments"
        guarded = guard_spoken_copy(
            str(row.get("text") or ""),
            evidence=evidence,
            required=required_line,
            purpose=f"synthetic_framing[{row.get('line_id') or index_i}]",
            seen_texts=[str(x.get("text") or "") for x in cleaned],
        )
        if guarded["action"] in {"block", "omit"}:
            # An uncurable line is dropped; its seam plays without spoken glue
            # (ISSUES 185). A required one used to fail the plan twice and stop
            # transitions with synthetic_framing_plan_invalid.
            continue
        row["text"] = guarded["text"]
        row["spoken_copy_guard"] = {
            "action": guarded["action"],
            "script_hash": guarded["script_hash"],
            "context_hash": guarded["context_hash"],
        }
        cleaned.append(row)
    out["lines"] = cleaned
    if out.get("synthetic_input_share_estimate") is None:
        speech = max(1, len(ordered))
        out["synthetic_input_share_estimate"] = round(
            len(cleaned) / float(speech + len(cleaned)), 4
        )
    if not str(out.get("strategy_summary") or "").strip():
        out["strategy_summary"] = (
            "Synthetic host framing only where selected native continuity needs help."
        )
    # Ensure between_segments fields for required reorder seams — prefer planned
    # VO (exact / reverse / endpoint) over stock mint.
    required = [p for p in (packet.get("required_reorder_seams") or []) if isinstance(p, dict)]
    required_pairs = [
        (str(p.get("after_segment_id") or ""), str(p.get("before_segment_id") or ""))
        for p in required
        if p.get("after_segment_id") and p.get("before_segment_id")
    ]
    covered = {
        (str(line.get("after_segment_id") or ""), str(line.get("before_segment_id") or ""))
        for line in cleaned
        if _line_covers_pair(
            line,
            str(line.get("after_segment_id") or ""),
            str(line.get("before_segment_id") or ""),
        )
    }
    from interview_mux.seam_glue import (
        bridge_guard_evidence,
        default_bridge_text,
        enrich_bridge_pair_excerpts,
    )

    def _mint_seam(pair: dict[str, Any], a: str, b: str) -> None:
        if a == b:
            return
        native = native_by_id.get(a) or native_by_id.get(b) or {}
        native_ms = max(
            250,
            int(native.get("end_ms") or 0) - int(native.get("start_ms") or 0),
        )
        enriched = enrich_bridge_pair_excerpts(pair, native_by_id)
        text = default_bridge_text(enriched)
        from interview_mux.spoken_copy_guard import assert_guarded_spoken_copy

        if not str(text or "").strip():
            return  # no grounded bridge text: the seam stays unglued (ISSUES 185)
        try:
            guarded = assert_guarded_spoken_copy(
                text,
                evidence=bridge_guard_evidence(enriched),
                purpose=f"synthetic_reorder_seam[{a}->{b}]",
                seen_texts=[str(x.get("text") or "") for x in cleaned],
                ctx=ctx,
            )
        except ValueError:
            return  # uncurable bridge copy: the seam stays unglued (ISSUES 185)
        cleaned.append(
            {
                "line_id": f"syn_seam_{a}_{b}",
                "role": "bridge",
                "placement": "between_segments",
                "anchor_segment_id": a if a in ordered else b,
                "after_segment_id": a,
                "before_segment_id": b,
                "text": guarded["text"],
                "duration_ratio": 1.0,
                "target_duration_ms": max(250, min(3500, int(native_ms * 0.6) or 1200)),
                "comprehension_reason": (
                    f"Required reorder seam {a}->{b}: orient the listener "
                    f"across the selected continuity break."
                ),
                "native_respect_violation": False,
                "auto_minted_seam": True,
                "speaker_policy": "current_host_clone",
                "spoken_copy_guard": {
                    "action": guarded["action"],
                    "script_hash": guarded["script_hash"],
                    "context_hash": guarded["context_hash"],
                },
            }
        )
        covered.add((a, b))
        ctx.log(
            f"synthetic_framing: minted stock seam {a}->{b} (no safe planned VO)",
            level="info",
            stage=STAGE_ID,
        )

    def _try_adopt(pair: dict[str, Any], a: str, b: str) -> bool:
        if a == b or (a, b) in covered:
            return True
        candidates: list[tuple[tuple[int, int], dict[str, Any], str]] = []
        for line in cleaned:
            if not str(line.get("text") or "").strip():
                continue
            if _sole_cover_of_other_required(
                line, a=a, b=b, required_pairs=required_pairs, cleaned=cleaned
            ):
                continue
            la = str(line.get("after_segment_id") or "")
            lb = str(line.get("before_segment_id") or "")
            anchor = str(line.get("anchor_segment_id") or "")
            if la == a and lb == b:
                repair = "exact"
            elif la == b and lb == a:
                repair = "reversed"
            elif lb == b:
                repair = "endpoint"
            elif la == a:
                repair = "endpoint"
            elif anchor in {a, b} and not (la and lb and {la, lb} - {a, b}):
                repair = "anchor"
            else:
                continue
            rank = _candidate_rank_key(line, a, b)
            candidates.append((rank, line, repair))
        candidates.sort(key=lambda item: item[0])
        # Prefer non-stock; allow stock bind only if that is the only candidate.
        non_stock = [c for c in candidates if c[0][1] == 0]
        pool = non_stock or [(r, line, "stock_ok") for r, line, _ in candidates]
        for _rank, line, repair in pool:
            if _line_covers_pair(line, a, b):
                covered.add((a, b))
                return True
            if _bind_line_to_seam(
                line,
                a=a,
                b=b,
                repair=repair,
                native_by_id=native_by_id,
                cleaned=cleaned,
                pair=pair,
            ):
                covered.add((a, b))
                ctx.log(
                    f"synthetic_framing: adopted planned VO onto {a}->{b} "
                    f"({repair}, line={line.get('line_id')})",
                    level="info",
                    stage=STAGE_ID,
                )
                return True
        return False

    for pair in required:
        a = str(pair.get("after_segment_id") or "")
        b = str(pair.get("before_segment_id") or "")
        if not a or not b or (a, b) in covered:
            continue
        if not _try_adopt(pair, a, b):
            _mint_seam(pair, a, b)

    # Second pass: rebuild coverage from actual line fields, then remint gaps.
    covered = {
        (
            str(line.get("after_segment_id") or ""),
            str(line.get("before_segment_id") or ""),
        )
        for line in cleaned
        if str(line.get("placement") or "") == "between_segments"
        and str(line.get("after_segment_id") or "")
        and str(line.get("before_segment_id") or "")
        and str(line.get("text") or "").strip()
    }
    for pair in required:
        a = str(pair.get("after_segment_id") or "")
        b = str(pair.get("before_segment_id") or "")
        if not a or not b or a == b or (a, b) in covered:
            continue
        if not _try_adopt(pair, a, b):
            _mint_seam(pair, a, b)

    out["lines"] = cleaned
    return out


def validate_synthetic_plan(
    ctx: RunContext,
    plan: dict[str, Any],
    *,
    packet: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    conf = synthetic_framing_cfg()
    ratio_min, ratio_max = _ratio_bounds()
    allow_canned = bool(conf.get("allow_canned_bridge_fallback", False))
    selection = ctx.read_json("master/selection.json")
    ordered_list = [str(x) for x in (selection.get("ordered_segment_ids") or []) if x]
    ordered = set(ordered_list)
    air_index = _ordered_index(ordered_list)
    if str(plan.get("selection_order_content_hash") or "") != str(
        selection.get("order_content_hash") or ""
    ):
        errors.append("selection_order_content_hash does not match native selection")
    for index, line in enumerate(plan.get("lines") or []):
        if not isinstance(line, dict):
            errors.append(f"lines[{index}] must be an object")
            continue
        anchor = str(line.get("anchor_segment_id") or "")
        if anchor not in ordered:
            errors.append(f"lines[{index}].anchor_segment_id not selected: {anchor}")
        try:
            ratio = float(line.get("duration_ratio"))
        except (TypeError, ValueError):
            errors.append(f"lines[{index}].duration_ratio missing")
            continue
        if not ratio_min <= ratio <= ratio_max:
            errors.append(
                f"lines[{index}].duration_ratio outside {ratio_min}..{ratio_max}"
            )
        if line.get("native_respect_violation") and conf.get("respect_native_speakers", True):
            errors.append(f"lines[{index}] violates native speaker protection")
        if not str(line.get("comprehension_reason") or "").strip():
            errors.append(f"lines[{index}].comprehension_reason missing")
        if str(line.get("placement") or "") == "between_segments":
            after = str(line.get("after_segment_id") or "")
            before = str(line.get("before_segment_id") or "")
            if after and before:
                if after == before:
                    errors.append(f"lines[{index}] self-loop seam {after}->{before}")
                elif after in air_index and before in air_index:
                    if air_index[after] > air_index[before]:
                        errors.append(
                            f"lines[{index}] reversed air-order seam {after}->{before}"
                        )
                    elif air_index[before] != air_index[after] + 1:
                        errors.append(
                            f"lines[{index}] non-adjacent seam {after}->{before}"
                        )
    # Required reorder seams must be covered by speakable between_segments lines.
    try:
        if packet is None:
            packet = (
                ctx.read_json(CONTEXT_REL)
                if ctx.artifact_exists(CONTEXT_REL)
                else build_context_packet(ctx)
            )
        required = packet.get("required_reorder_seams") or []
        covered = {
            (
                str(line.get("after_segment_id") or ""),
                str(line.get("before_segment_id") or ""),
            )
            for line in (plan.get("lines") or [])
            if isinstance(line, dict)
            and str(line.get("placement") or "") == "between_segments"
            and str(line.get("text") or "").strip()
        }
        for pair in required:
            if not isinstance(pair, dict):
                continue
            a = str(pair.get("after_segment_id") or "")
            b = str(pair.get("before_segment_id") or "")
            if not a or not b or (a, b) in covered:
                continue
            # Advisory (ISSUES 185): an uncovered reorder seam plays without
            # spoken glue; seam_glue mints a bridge when it can ground one.
            continue
    except Exception as exc:
        errors.append(f"required_reorder_seams check failed: {exc}")
    return errors


def run_synthetic_framing_plan(ctx: RunContext, *, force: bool = False) -> dict[str, Any]:
    from interview_mux.nugget_layup import nugget_layup_enabled

    packet = build_context_packet(ctx)
    # S3A: when Nugget Layup is on, always demote-empty — never re-LLM content
    # (seam_glue may still mint structural hinges).
    if not force and nugget_layup_enabled():
        empty = {
            "selection_order_content_hash": packet.get("selection_order_content_hash"),
            "strategy_summary": "nugget_layup_authority — content VO owned by layup plan",
            "synthetic_input_share_estimate": 0.0,
            "lines": [],
            "generated_at": _now(),
            "demoted": True,
            "demote_reason": "nugget_layup_enabled",
        }
        _commit_json(ctx, PLAN_REL, empty)
        if not ctx.is_done(STAGE_ID):
            try:
                heal_or_refuse_mark(ctx, STAGE_ID, force=True)
            except Exception:
                pass
        ctx.log(
            "synthetic_framing_plan: demoted under nugget_layup authority (empty lines)",
            level="info",
            stage=STAGE_ID,
        )
        return empty

    if not force and ctx.artifact_exists(PLAN_REL):
        prior = ctx.read_json(PLAN_REL)
        if isinstance(prior, dict) and not validate_synthetic_plan(ctx, prior, packet=packet):
            return prior

    persist_base = make_stage_persist(PLAN_REL, STAGE_ID)

    def build_input(_ctx: RunContext) -> dict[str, Any]:
        return packet

    def persist(c: RunContext, artifacts: dict[str, Any]) -> None:
        # Always normalize + validate against the same in-memory packet. Reading
        # CONTEXT_REL via resolve_read_path can return a stale staged copy with a
        # different required_reorder_seams set, which made mint/validate diverge.
        doc = normalize_synthetic_plan(c, dict(artifacts), packet)
        errors = validate_synthetic_plan(c, doc, packet=packet)
        if errors:
            raise ValueError("synthetic framing plan invalid: " + "; ".join(errors[:8]))
        persist_base(c, doc)
        # Nested under transitions staging — commit so flush cannot drop the plan.
        _commit_json(c, PLAN_REL, doc)

    # llm_simple only retries schema failures; wrap persist errors as schema feedback.
    from interview_mux.llm_simple import StageError, run_llm_stage_simple

    last_error: Exception | None = None
    for attempt in (1, 2):
        try:
            if attempt == 2:
                # Rebuild packet and include previous failure as soft guidance.
                packet = build_context_packet(ctx)
                packet["retry_note"] = (
                    "Previous plan referenced non-selected segments, drifted from "
                    "selection_order_content_hash, or missed required_reorder_seams. "
                    "Cover every required_reorder_seams pair with a between_segments "
                    "line using only ordered_segment_ids from this packet."
                )
                _commit_json(ctx, CONTEXT_REL, packet)
            run_llm_stage_simple(
                ctx,
                STAGE_ID,
                PROMPT_REL,
                build_input,
                persist,
                auto_complete=True,
            )
            last_error = None
            break
        except (ValueError, StageError) as exc:
            last_error = exc
            ctx.log(
                f"synthetic_framing_plan attempt {attempt} failed: {exc}",
                level="warning",
                stage=STAGE_ID,
            )
    if last_error is not None:
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            f"Synthetic framing plan failed after 2 attempts: {last_error}",
            stage="transitions",
            reason="synthetic_framing_plan_invalid",
            cause=last_error,
        )
    plan = ctx.read_json(PLAN_REL)
    if not isinstance(plan, dict):
        raise RuntimeError("synthetic framing plan was not persisted")
    return plan


def planned_transition_for_pair(
    plan: dict[str, Any] | None, after_id: str, before_id: str
) -> dict[str, Any] | None:
    if not isinstance(plan, dict):
        return None

    def _ok_placement(line: dict[str, Any]) -> bool:
        return str(line.get("placement") or "") in {
            "between_segments",
            "before_segment",
            "after_segment",
        }

    for line in plan.get("lines") or []:
        if not isinstance(line, dict) or not _ok_placement(line):
            continue
        if str(line.get("after_segment_id") or "") != after_id:
            continue
        if str(line.get("before_segment_id") or "") != before_id:
            continue
        return line
    # Belt: reversed ids — rewrite to requested air-order pair before return.
    for line in plan.get("lines") or []:
        if not isinstance(line, dict) or not _ok_placement(line):
            continue
        if str(line.get("after_segment_id") or "") != before_id:
            continue
        if str(line.get("before_segment_id") or "") != after_id:
            continue
        fixed = dict(line)
        fixed["after_segment_id"] = after_id
        fixed["before_segment_id"] = before_id
        fixed["adopted_seam_repair"] = fixed.get("adopted_seam_repair") or "reversed"
        return fixed
    return None
