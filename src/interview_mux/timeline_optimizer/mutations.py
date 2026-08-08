"""Apply timeline mutations to a candidate snapshot (structure + glue + SDP)."""

from __future__ import annotations

import copy
import re
from typing import Any


def _clone(cand: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(cand)


def apply_mutation(candidate: dict[str, Any], mutation: dict[str, Any]) -> dict[str, Any]:
    """Return a new candidate with mutation applied."""
    op = str(mutation.get("op") or "")
    out = _clone(candidate)
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    excluded = [str(s) for s in (out.get("excluded_segment_ids") or []) if s]
    notes = list(out.get("mutations") or [])

    if op == "ensure_hook_early":
        from interview_mux.listen_quality import ensure_hook_early

        hook = mutation.get("hook_segment_id")
        ordered, moved = ensure_hook_early(ordered, str(hook) if hook else None)
        if moved:
            notes.append({"op": op, "hook_segment_id": hook})

    elif op == "topo_repair":
        from interview_mux.selection_order_repair import topo_satisfy_order

        plan = mutation.get("narrative_plan")
        ordered, applied = topo_satisfy_order(
            ordered, narrative_plan=plan if isinstance(plan, dict) else None
        )
        if applied:
            notes.append({"op": op, "applied": applied[:6]})

    elif op == "swap":
        a = str(mutation.get("a") or "")
        b = str(mutation.get("b") or "")
        if a in ordered and b in ordered:
            i, j = ordered.index(a), ordered.index(b)
            ordered[i], ordered[j] = ordered[j], ordered[i]
            notes.append({"op": op, "a": a, "b": b})

    elif op == "move_before":
        sid = str(mutation.get("segment_id") or "")
        before = str(mutation.get("before_segment_id") or "")
        if sid in ordered:
            ordered = [s for s in ordered if s != sid]
            if before in ordered:
                ordered.insert(ordered.index(before), sid)
            else:
                ordered.insert(0, sid)
            notes.append({"op": op, "segment_id": sid, "before_segment_id": before})

    elif op == "rotate_block":
        start = int(mutation.get("start_index") or 0)
        end = int(mutation.get("end_index") or start)
        if 0 <= start < end <= len(ordered) and end - start >= 2:
            block = ordered[start:end]
            k = int(mutation.get("rotate_by") or 1) % len(block)
            ordered = ordered[:start] + block[k:] + block[:k] + ordered[end:]
            notes.append({"op": op, "start": start, "end": end, "rotate_by": k})

    elif op == "exclude":
        sid = str(mutation.get("segment_id") or "")
        if sid in ordered and len(ordered) > 3:
            ordered = [s for s in ordered if s != sid]
            if sid not in excluded:
                excluded.append(sid)
            notes.append({"op": op, "segment_id": sid})

    elif op == "drop_redundant_sibling":
        # Drop later of identical split siblings
        for i in range(len(ordered) - 1):
            a, b = ordered[i], ordered[i + 1]
            m1 = re.match(r"^(seg_\d+)([a-z]+)?$", a)
            m2 = re.match(r"^(seg_\d+)([a-z]+)?$", b)
            if m1 and m2 and m1.group(1) == m2.group(1) and m1.group(2) and m2.group(2):
                ordered = [s for s in ordered if s != b]
                if b not in excluded:
                    excluded.append(b)
                notes.append({"op": op, "kept": a, "dropped": b})
                break

    elif op == "set_order":
        new_order = [str(s) for s in (mutation.get("ordered_segment_ids") or []) if s]
        if new_order:
            # Keep only known ids; append missing from prior order
            kept = set(ordered) | set(excluded)
            filtered = [s for s in new_order if s in kept or not kept]
            if not filtered:
                filtered = new_order
            missing = [s for s in ordered if s not in filtered]
            ordered = filtered + missing
            notes.append({"op": op, "count": len(filtered)})

    elif op == "mint_bridge":
        from interview_mux.seam_glue import (
            bridge_guard_evidence,
            default_bridge_text,
            enrich_bridge_pair_excerpts,
        )

        after = str(mutation.get("after_segment_id") or "")
        before = str(mutation.get("before_segment_id") or "")
        text = str(mutation.get("text") or "").strip()
        if after and before:
            tr = out.get("transitions") if isinstance(out.get("transitions"), dict) else {"transitions": []}
            tr = copy.deepcopy(tr)
            items = list(tr.get("transitions") or [])
            exists = any(
                isinstance(t, dict)
                and str(t.get("after_segment_id")) == after
                and str(t.get("before_segment_id")) == before
                for t in items
            )
            if not exists:
                # Content-anchored hinge (excerpts on the mutation when present).
                pair = enrich_bridge_pair_excerpts(mutation, None)
                fallback = str(mutation.get("suggested_text") or "").strip() or default_bridge_text(
                    pair
                )
                from interview_mux.spoken_copy_guard import guard_spoken_copy

                guarded = guard_spoken_copy(
                    text or fallback,
                    evidence=bridge_guard_evidence(pair),
                    required=True,
                    purpose=f"optimizer_bridge[{after}->{before}]",
                )
                if guarded["action"] == "block":
                    notes.append(
                        {
                            "op": op,
                            "rejected": True,
                            "reason": "unsafe_spoken_copy",
                            "after": after,
                            "before": before,
                        }
                    )
                    out["ordered_segment_ids"] = ordered
                    out["excluded_segment_ids"] = excluded
                    out["mutations"] = notes
                    return out
                items.append(
                    {
                        "after_segment_id": after,
                        "before_segment_id": before,
                        "text": guarded["text"],
                        "type": mutation.get("type") or "bridge",
                        "tone": mutation.get("tone") or "bridge",
                        "optimizer_minted": True,
                        "spoken_copy_guard": {
                            "action": guarded["action"],
                            "script_hash": guarded["script_hash"],
                            "context_hash": guarded["context_hash"],
                        },
                    }
                )
                tr["transitions"] = items
                out["transitions"] = tr
                notes.append({"op": op, "after": after, "before": before})

    elif op == "rewrite_bridge":
        after = str(mutation.get("after_segment_id") or "")
        before = str(mutation.get("before_segment_id") or "")
        text = str(mutation.get("text") or "").strip()
        tr = out.get("transitions") if isinstance(out.get("transitions"), dict) else None
        if tr and text:
            from interview_mux.spoken_copy_guard import guard_spoken_copy
            from interview_mux.seam_glue import bridge_guard_evidence

            guarded = guard_spoken_copy(
                text,
                evidence=bridge_guard_evidence(mutation),
                required=True,
                purpose=f"optimizer_rewrite[{after}->{before}]",
            )
            if guarded["action"] == "block":
                notes.append(
                    {
                        "op": op,
                        "rejected": True,
                        "reason": "unsafe_spoken_copy",
                        "after": after,
                        "before": before,
                    }
                )
                out["ordered_segment_ids"] = ordered
                out["excluded_segment_ids"] = excluded
                out["mutations"] = notes
                return out
            tr = copy.deepcopy(tr)
            for t in tr.get("transitions") or []:
                if (
                    isinstance(t, dict)
                    and str(t.get("after_segment_id")) == after
                    and str(t.get("before_segment_id")) == before
                ):
                    t["text"] = guarded["text"]
                    t["optimizer_rewritten"] = True
                    t["spoken_copy_guard"] = {
                        "action": guarded["action"],
                        "script_hash": guarded["script_hash"],
                        "context_hash": guarded["context_hash"],
                    }
                    notes.append({"op": op, "after": after, "before": before})
                    break
            out["transitions"] = tr

    elif op == "gap_line_hint":
        # Soft: attach optimizer hint onto matching gap line for later recompose
        target = str(mutation.get("targets_segment_id") or "")
        text = str(mutation.get("text") or "").strip()
        gap = out.get("gap_report") if isinstance(out.get("gap_report"), dict) else None
        if gap and target and text:
            from interview_mux.spoken_copy_guard import guard_spoken_copy

            guarded = guard_spoken_copy(
                text,
                evidence=mutation,
                required=False,
                purpose=f"optimizer_gap_hint[{target}]",
            )
            if guarded["action"] == "omit":
                notes.append(
                    {
                        "op": op,
                        "rejected": True,
                        "reason": "unsafe_spoken_copy",
                        "targets_segment_id": target,
                    }
                )
                out["ordered_segment_ids"] = ordered
                out["excluded_segment_ids"] = excluded
                out["mutations"] = notes
                return out
            gap = copy.deepcopy(gap)
            for ln in gap.get("interviewer_lines") or []:
                if isinstance(ln, dict) and str(ln.get("targets_segment_id")) == target:
                    ln["optimizer_text_hint"] = guarded["text"]
                    if mutation.get("replace") and guarded["text"]:
                        ln["text"] = guarded["text"]
                    notes.append({"op": op, "targets_segment_id": target})
                    break
            out["gap_report"] = gap

    elif op == "remap_cold_open_music":
        sdp = out.get("sound_design_plan")
        if isinstance(sdp, dict):
            sdp = copy.deepcopy(sdp)
            cues = list(sdp.get("cues") or sdp.get("placements") or [])
            changed = False
            for cue in cues:
                if not isinstance(cue, dict):
                    continue
                role = str(cue.get("role") or "")
                if role in {"theme_cold_open", "cold_open"} or "cold" in str(
                    cue.get("placement") or ""
                ):
                    cue["placement"] = "cold_open"
                    cue["role"] = "theme_cold_open"
                    cue["optimizer_remapped"] = True
                    changed = True
            if changed:
                if "cues" in sdp:
                    sdp["cues"] = cues
                elif "placements" in sdp:
                    sdp["placements"] = cues
                out["sound_design_plan"] = sdp
                notes.append({"op": op})

    elif op == "hinge_punctuator":
        after = str(mutation.get("after_segment_id") or "")
        sdp = out.get("sound_design_plan")
        if isinstance(sdp, dict) and after:
            sdp = copy.deepcopy(sdp)
            cues = list(sdp.get("cues") or sdp.get("placements") or [])
            cues.append(
                {
                    "role": "theme_transition",
                    "placement": "after_segment",
                    "after_segment_id": after,
                    "optimizer_minted": True,
                    "level_db": -22.0,
                }
            )
            if "cues" in sdp:
                sdp["cues"] = cues
            else:
                sdp["placements"] = cues
            out["sound_design_plan"] = sdp
            notes.append({"op": op, "after_segment_id": after})

    out["ordered_segment_ids"] = ordered
    out["excluded_segment_ids"] = excluded
    out["mutations"] = notes
    return out
