"""Deterministic episode structure composer — sparse slot_plan + segment_order."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, repo_root
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext

STRUCTURE_PATH = "understanding/episode_structure.json"
COMPACT_DIGEST_PATH = "understanding/episode_structure_compact.txt"
PACKS_DIR_REL = "docs/cross-cutting/episode-structure-packs"


def commit_episode_structure_compact(ctx: RunContext, text: str, *, stage_key: str) -> Any:
    """Persist the compact digest under the ownership constitution.

    The digest is plain text, so ``ctx.write_json`` cannot carry it. This mirrors
    ``gap_framing.commit_interviewer_script``: assert authority for the named
    stage first, then write through ``ctx.path`` so the write lands in that
    stage's staging root and commits on the normal flush. A raw
    ``Path.write_text`` skipped the authority check entirely.
    """
    from interview_mux.artifact_ownership import assert_write
    from interview_mux.file_store import write_text as fs_write_text
    from interview_mux.write_staging import active_stage_id

    sk = str(stage_key or "").strip() or (active_stage_id() or "")
    assert_write(ctx, COMPACT_DIGEST_PATH, sk, role="producer", verb="persist")
    dest = ctx.path(*COMPACT_DIGEST_PATH.split("/"))
    fs_write_text(dest, text)
    return dest


MUSIC_VERBS = frozenset(
    {
        "into_speech",
        "after_speech",
        "under_speech",
        "between_islands",
        "around_vo",
        "motif_callback",
        "bed_morph",
        "silence_as_transition",
        "resolve_swell",
        "tension_hold",
    }
)

STD_CATALOG: list[dict[str, Any]] = [
    {
        "component_id": "STD_cold_open_slot",
        "class": "standard",
        "gate": "prefer",
        "speech_job": "hook_quote",
        "music_transition": "into_speech",
        "asset_role": "cold_open",
        "placement": "pre_body",
        "priority": 10,
    },
    {
        "component_id": "STD_orientation",
        "class": "standard",
        "gate": "prefer",
        "speech_job": "host_stakes",
        "music_transition": "after_speech",
        "asset_role": "vo_bridge",
        "placement": "pre_body",
        "priority": 20,
    },
    {
        "component_id": "STD_act_body",
        "class": "standard",
        "gate": "prefer",
        "speech_job": "interview_mass",
        "music_transition": "under_speech",
        "asset_role": "ambient_bed",
        "placement": "body",
        "priority": 50,
    },
    {
        "component_id": "STD_chapter_hinge",
        "class": "standard",
        "gate": "allow",
        "speech_job": "chapter_reset",
        "music_transition": "between_islands",
        "asset_role": "chapter_stinger",
        "placement": "body",
        "priority": 40,
    },
    {
        "component_id": "STD_comprehension_bridge",
        "class": "standard",
        "gate": "allow",
        "speech_job": "gap_vo_bridge",
        "music_transition": "around_vo",
        "asset_role": "vo_bridge",
        "placement": "body",
        "priority": 45,
    },
    {
        "component_id": "STD_payoff_close",
        "class": "standard",
        "gate": "allow",
        "speech_job": "resolve",
        "music_transition": "resolve_swell",
        "asset_role": "outro",
        "placement": "post_body",
        "priority": 80,
    },
    {
        "component_id": "STD_outro_button",
        "class": "standard",
        "gate": "allow",
        "speech_job": "signoff",
        "music_transition": "after_speech",
        "asset_role": "outro",
        "placement": "post_body",
        "priority": 90,
    },
]

DYN_CATALOG: dict[str, dict[str, Any]] = {
    "DYN_mid_quote_cold_open": {
        "class": "dynamic",
        "gate": "prefer",
        "speech_job": "hook_quote",
        "music_transition": "into_speech",
        "asset_role": "cold_open",
        "placement": "pre_body",
        "priority": 11,
    },
    "DYN_teaser_montage": {
        "class": "dynamic",
        "gate": "allow",
        "speech_job": "tease",
        "music_transition": "between_islands",
        "asset_role": "cold_open",
        "placement": "pre_body",
        "priority": 12,
    },
    "DYN_content_warning_pad": {
        "class": "dynamic",
        "gate": "must",
        "speech_job": "content_warning",
        "music_transition": "silence_as_transition",
        "asset_role": "vo_bridge",
        "placement": "pre_body",
        "priority": 5,
    },
    "DYN_rebuttal_pair_lock": {
        "class": "dynamic",
        "gate": "prefer",
        "speech_job": "keep_qa_pair",
        "music_transition": "silence_as_transition",
        "asset_role": "",
        "placement": "body",
        "priority": 55,
    },
    "DYN_topic_shift_spoken": {
        "class": "dynamic",
        "gate": "allow",
        "speech_job": "topic_bridge",
        "music_transition": "around_vo",
        "asset_role": "vo_bridge",
        "placement": "body",
        "priority": 48,
    },
    "DYN_nostalgia_bed": {
        "class": "dynamic",
        "gate": "prefer",
        "speech_job": "",
        "music_transition": "under_speech",
        "asset_role": "ambient_bed",
        "placement": "body",
        "priority": 52,
    },
    "DYN_triumph_sting": {
        "class": "dynamic",
        "gate": "forbid",
        "speech_job": "",
        "music_transition": "resolve_swell",
        "asset_role": "chapter_stinger",
        "placement": "post_body",
        "priority": 99,
    },
}


def structure_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict((cfg or merged_config()).get("structure") or {})


def structure_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(structure_cfg(cfg).get("enabled", True))


def structure_strict_slots(cfg: dict[str, Any] | None = None) -> bool:
    return bool(structure_cfg(cfg).get("strict_slots", False))


def hook_reel_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(structure_cfg(cfg).get("hook_reel_enabled", True))


def max_dynamic_slots(cfg: dict[str, Any] | None = None) -> int:
    return max(1, int(structure_cfg(cfg).get("max_dynamic_slots", 24)))


def packs_dir() -> Path:
    return repo_root() / PACKS_DIR_REL


def _read_yaml(path: Path) -> dict[str, Any]:
    import yaml  # type: ignore

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def load_pack(pack_id: str) -> dict[str, Any]:
    path = packs_dir() / f"{pack_id}.yaml"
    if not path.is_file():
        path = packs_dir() / "default.yaml"
    if not path.is_file():
        return {"pack_id": pack_id, "default_gates": {}, "unlock_dynamic": [], "forbid": [], "prefer": []}
    data = _read_yaml(path)
    if not isinstance(data, dict):
        return {"pack_id": pack_id, "default_gates": {}}
    return data


def _policy_hash(doc: dict[str, Any]) -> str:
    payload = {k: v for k, v in doc.items() if k not in ("policy_hash", "compact_digest")}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _segments(ctx: RunContext) -> list[dict[str, Any]]:
    try:
        if not ctx.artifact_exists("segments/manifest.json"):
            return []
        doc = ctx.read_json("segments/manifest.json")
    except Exception:
        return []
    segs = doc.get("segments") if isinstance(doc, dict) else None
    return [s for s in (segs or []) if isinstance(s, dict) and s.get("segment_id")]


def _detect_axes(ctx: RunContext) -> dict[str, str]:
    from interview_mux.sonic_context import classify_atlas_bucket, load_sonic_context

    state: dict[str, Any] = {}
    try:
        if ctx.artifact_exists("understanding/analysis_state.json"):
            state = ctx.read_json("understanding/analysis_state.json") or {}
    except Exception:
        state = {}
    style = state.get("style") if isinstance(state.get("style"), dict) else {}
    format_class = str(style.get("format_class") or "").strip()
    if not format_class and ctx.artifact_exists("understanding/speakers.json"):
        try:
            spk = ctx.read_json("understanding/speakers.json") or {}
            profile = spk.get("conversation_profile") if isinstance(spk.get("conversation_profile"), dict) else {}
            format_class = str(profile.get("format_class_candidate") or "").strip()
        except Exception:
            format_class = ""
    sonic = load_sonic_context(ctx) or {}
    scenario = sonic.get("scenario") if isinstance(sonic.get("scenario"), dict) else {}
    atlas = str(scenario.get("atlas_bucket") or "").strip()
    if not atlas:
        try:
            atlas = classify_atlas_bucket(ctx)
        except Exception:
            atlas = "one_on_one"
    return {
        "format_class": format_class or str(scenario.get("format_class") or "unknown"),
        "tone_class": str(style.get("tone_class") or scenario.get("tone_class") or "unknown"),
        "atlas_bucket": atlas or "one_on_one",
        "production_style": str(style.get("production_style") or ""),
    }


def _score_std(component_id: str, *, segs: list[dict[str, Any]], axes: dict[str, str], pack: dict[str, Any]) -> float:
    gates = pack.get("default_gates") if isinstance(pack.get("default_gates"), dict) else {}
    gate = str(gates.get(component_id) or "allow")
    if gate == "forbid":
        return -1.0
    n = len(segs)
    if component_id == "STD_act_body":
        return 1.0 if n else 0.0
    if component_id == "STD_cold_open_slot":
        # Prefer when we have a quotable-looking mid segment
        if n < 3:
            return 0.2
        return 0.75 if gate in ("prefer", "must") else 0.45
    if component_id == "STD_orientation":
        return 0.6 if gate == "prefer" else 0.35
    if component_id == "STD_chapter_hinge":
        return 0.55 if n >= 8 else 0.15
    if component_id == "STD_comprehension_bridge":
        return 0.5 if n >= 6 else 0.2
    if component_id in ("STD_payoff_close", "STD_outro_button"):
        # Never force — score only when pack prefers
        if gate == "prefer":
            return 0.55
        return 0.25
    return 0.4


def _pick_hook_segment(segs: list[dict[str, Any]]) -> str | None:
    if len(segs) < 3:
        return None
    # Prefer a mid-body short segment with substantial text
    best_id = None
    best_score = -1.0
    for i, s in enumerate(segs):
        if i == 0:
            continue
        text = str(s.get("text") or "")
        score = min(len(text), 400) / 400.0
        if "quote" in " ".join(str(t) for t in (s.get("topic_tags") or [])).lower():
            score += 0.3
        if score > best_score:
            best_score = score
            best_id = str(s.get("segment_id"))
    return best_id


def _order_segments(segs: list[dict[str, Any]], hook_id: str | None) -> list[str]:
    ids = [str(s["segment_id"]) for s in segs]
    if not ids:
        return []
    # Cold open: place hook speech at timeline front when STD_cold_open_slot bound a hook_reel id.
    # Remaining body keeps relative order (hook removed from later slot to avoid double occupancy
    # unless hook_reel.repeat_allowed documents intentional replay outside segment_order).
    if hook_id and hook_id in ids:
        return [hook_id] + [sid for sid in ids if sid != hook_id]
    return ids


def check_occupancy(
    segment_order: list[str],
    slot_plan: list[dict[str, Any]],
    *,
    hook_id: str | None,
    repeat_allowed: bool,
) -> list[str]:
    counts: dict[str, int] = {}
    for sid in segment_order:
        counts[sid] = counts.get(sid, 0) + 1
    for slot in slot_plan:
        for sid in slot.get("bound_segment_ids") or []:
            counts[str(sid)] = counts.get(str(sid), 0) + 1
    violations: list[str] = []
    for sid, n in counts.items():
        if n <= 1:
            continue
        if repeat_allowed and hook_id and sid == hook_id and n == 2:
            continue
        violations.append(f"segment_id:{sid}:count={n}")
    return violations


def check_integrity(segs: list[dict[str, Any]], segment_order: list[str]) -> tuple[bool, list[str]]:
    """Reject orders that invert adjacent question→answer pairs when typed."""
    by_id = {str(s.get("segment_id")): s for s in segs}
    flags: list[str] = []
    id_index = {str(s.get("segment_id")): idx for idx, s in enumerate(segs)}
    for i in range(len(segment_order) - 1):
        a = by_id.get(segment_order[i]) or {}
        b = by_id.get(segment_order[i + 1]) or {}
        ta = str(a.get("type") or a.get("segment_type") or "").lower()
        tb = str(b.get("type") or b.get("segment_type") or "").lower()
        ia = id_index.get(segment_order[i], -1)
        ib = id_index.get(segment_order[i + 1], -1)
        # Answer immediately followed by the question that originally preceded it
        if "answer" in ta and "question" in tb and ia >= 0 and ib >= 0 and ia == ib + 1:
            flags.append(f"qa_inversion:{segment_order[i]}->{segment_order[i+1]}")
    # Orphan answers: answer with no prior question in order
    seen_q = False
    for sid in segment_order:
        s = by_id.get(sid) or {}
        t = str(s.get("type") or s.get("segment_type") or "").lower()
        if "question" in t:
            seen_q = True
        if "answer" in t and not seen_q and any(
            "question" in str(x.get("type") or x.get("segment_type") or "").lower() for x in segs
        ):
            flags.append(f"orphan_answer:{sid}")
            break
    return (len(flags) == 0), flags


def lint_episode_structure(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    slots = doc.get("slot_plan") if isinstance(doc.get("slot_plan"), list) else []
    seen_ids: set[str] = set()
    for slot in slots:
        if not isinstance(slot, dict):
            errors.append("slot_plan:non_object")
            continue
        sid = str(slot.get("slot_id") or "")
        if not sid:
            errors.append("slot_missing_slot_id")
        elif sid in seen_ids:
            errors.append(f"duplicate_slot_id:{sid}")
        seen_ids.add(sid)
        gate = str(slot.get("gate") or "")
        if gate not in ("must", "prefer", "allow", "forbid"):
            errors.append(f"illegal_gate:{sid}:{gate}")
        verb = str(slot.get("music_transition") or "")
        if verb and verb not in MUSIC_VERBS:
            errors.append(f"illegal_music_verb:{sid}:{verb}")
    # No forced STD checklist — payoff/outro may be absent
    req_payoff = bool(structure_cfg().get("require_payoff", False))
    req_outro = bool(structure_cfg().get("require_outro", False))
    emitted = {str(s.get("component_id")) for s in slots if isinstance(s, dict)}
    if req_payoff and "STD_payoff_close" not in emitted:
        errors.append("require_payoff_missing")
    if req_outro and "STD_outro_button" not in emitted:
        errors.append("require_outro_missing")
    occ = (doc.get("occupancy") or {}).get("violations") or []
    if occ:
        errors.extend([f"occupancy:{v}" for v in occ])
    integ = doc.get("integrity") or {}
    if integ.get("ok") is False:
        errors.append("integrity_failed")
    return errors


def build_compact_digest(doc: dict[str, Any]) -> str:
    axes = doc.get("axes") or {}
    slots = doc.get("slot_plan") or []
    omits = doc.get("omit_reasons") or []
    high_omit = [
        o.get("component_id")
        for o in omits
        if isinstance(o, dict)
        and str(o.get("component_id") or "").startswith("STD_")
        and str(o.get("component_id")) in ("STD_payoff_close", "STD_outro_button", "STD_cold_open_slot", "STD_orientation")
    ]
    lines = [
        f"axes: format={axes.get('format_class')} tone={axes.get('tone_class')} atlas={axes.get('atlas_bucket')}",
        "slots: "
        + ", ".join(
            f"{s.get('component_id')}({s.get('gate')})" for s in slots if isinstance(s, dict)
        )[:500],
        "segment_order: " + ",".join(str(x) for x in (doc.get("segment_order") or [])[:40]),
        "omit_high_profile: " + ",".join(str(x) for x in high_omit),
        f"hook_reel: {json.dumps(doc.get('hook_reel') or {}, ensure_ascii=False)}",
    ]
    text = "\n".join(lines)
    if len(text) > 3200:
        text = text[:3190] + "…"
    return text


def build_episode_structure(ctx: RunContext, *, refresh: bool = False) -> dict[str, Any]:
    cfg = merged_config()
    axes = _detect_axes(ctx)
    pack = load_pack(axes.get("atlas_bucket") or "default")
    segs = _segments(ctx)
    # Prefer ranked selection on refresh
    if refresh and ctx.artifact_exists("master/selection.json"):
        try:
            sel = ctx.read_json("master/selection.json") or {}
            ordered = sel.get("ordered_segment_ids") or sel.get("segment_ids") or []
            if isinstance(ordered, list) and ordered:
                by_id = {str(s.get("segment_id")): s for s in segs}
                segs = [by_id[str(i)] for i in ordered if str(i) in by_id] or segs
        except Exception:
            pass

    gates = pack.get("default_gates") if isinstance(pack.get("default_gates"), dict) else {}
    forbid = {str(x) for x in (pack.get("forbid") or [])}
    prefer_dyn = {str(x) for x in (pack.get("prefer") or [])}
    unlock = [str(x) for x in (pack.get("unlock_dynamic") or [])]

    omit_reasons: list[dict[str, str]] = []
    rationale: list[str] = []
    slot_plan: list[dict[str, Any]] = []
    slot_i = 0

    threshold = 0.4
    for std in STD_CATALOG:
        cid = std["component_id"]
        gate = str(gates.get(cid) or std["gate"])
        if gate == "forbid" or cid in forbid:
            omit_reasons.append({"component_id": cid, "reason": "pack_forbid"})
            continue
        score = _score_std(cid, segs=segs, axes=axes, pack={**pack, "default_gates": {**gates, cid: gate}})
        if score < 0:
            omit_reasons.append({"component_id": cid, "reason": "forbidden"})
            continue
        # Omit unscored allow slots (sparse) — prefer/must emit if score ok
        if gate == "allow" and score < 0.5:
            omit_reasons.append({"component_id": cid, "reason": f"low_score:{score:.2f}"})
            continue
        if gate == "prefer" and score < threshold and cid != "STD_act_body":
            omit_reasons.append({"component_id": cid, "reason": f"prefer_unmet:{score:.2f}"})
            continue
        if not segs and cid == "STD_act_body":
            omit_reasons.append({"component_id": cid, "reason": "no_segments"})
            continue
        slot_i += 1
        bound: list[str] = []
        if cid == "STD_act_body":
            bound = [str(s["segment_id"]) for s in segs]
        slot_plan.append(
            {
                "slot_id": f"slot_{slot_i:02d}_{cid}",
                "component_id": cid,
                "class": "standard",
                "gate": gate,
                "speech_job": std.get("speech_job") or "",
                "music_transition": std.get("music_transition") or "",
                "asset_role": std.get("asset_role") or "",
                "placement": std.get("placement") or "",
                "priority": float(std.get("priority") or 50),
                "bound_segment_ids": bound,
                "repeat_allowed": False,
            }
        )
        rationale.append(f"emit {cid} gate={gate} score={score:.2f}")

    dyn_emitted = 0
    max_dyn = max_dynamic_slots(cfg)
    for did in unlock + sorted(prefer_dyn):
        if dyn_emitted >= max_dyn:
            break
        if did in forbid:
            omit_reasons.append({"component_id": did, "reason": "pack_forbid"})
            continue
        meta = DYN_CATALOG.get(did)
        if not meta:
            continue
        gate = str(meta.get("gate") or "allow")
        if did in prefer_dyn:
            gate = "prefer"
        if gate == "forbid":
            omit_reasons.append({"component_id": did, "reason": "catalog_forbid"})
            continue
        slot_i += 1
        dyn_emitted += 1
        slot_plan.append(
            {
                "slot_id": f"slot_{slot_i:02d}_{did}",
                "component_id": did,
                "class": "dynamic",
                "gate": gate,
                "speech_job": meta.get("speech_job") or "",
                "music_transition": meta.get("music_transition") or "",
                "asset_role": meta.get("asset_role") or "",
                "placement": meta.get("placement") or "",
                "priority": float(meta.get("priority") or 50),
                "bound_segment_ids": [],
                "repeat_allowed": False,
            }
        )
        rationale.append(f"emit {did} gate={gate}")

    slot_plan.sort(key=lambda s: float(s.get("priority") or 50))

    hook_id = None
    repeat_allowed = False
    if hook_reel_enabled(cfg) and any(s.get("component_id") == "STD_cold_open_slot" for s in slot_plan):
        hook_id = _pick_hook_segment(segs)
        if hook_id:
            repeat_allowed = True
            for s in slot_plan:
                if s.get("component_id") == "STD_cold_open_slot":
                    s["bound_segment_ids"] = [hook_id]
                    s["repeat_allowed"] = True
            rationale.append(f"hook_reel:{hook_id}")

    from interview_mux.speaker_volley import check_speaker_volley_integrity, detect_speaker_volleys

    speaker_volleys = detect_speaker_volleys(segs)
    segment_order = _order_segments(segs, hook_id)
    # Body binds unique segments; ensure order unique
    seen: set[str] = set()
    unique_order: list[str] = []
    for sid in segment_order:
        if sid in seen:
            continue
        seen.add(sid)
        unique_order.append(sid)
    segment_order = unique_order

    ok, flags = check_integrity(segs, segment_order)
    volley_ok, volley_flags = check_speaker_volley_integrity(segment_order, speaker_volleys)
    if not volley_ok:
        flags = list(flags) + volley_flags
        ok = False
    if not ok:
        # Prefer repair: restore original timeline order (keeps speaker volleys contiguous)
        segment_order = [str(s["segment_id"]) for s in segs]
        ok2, flags2 = check_integrity(segs, segment_order)
        vok2, vflags2 = check_speaker_volley_integrity(segment_order, speaker_volleys)
        merged = flags2 + vflags2
        ok, flags = (ok2 and vok2), (
            flags + [f"repaired:{f}" for f in merged] if not (ok2 and vok2) else flags + ["repaired_to_manifest_order"]
        )
        rationale.append("integrity_repair:manifest_order")
    if speaker_volleys:
        rationale.append(f"speaker_volleys:{len(speaker_volleys)}")

    # Occupancy: body bindings + order (hook reel may appear in cold open + body once each)
    occ_violations = check_occupancy(segment_order, slot_plan, hook_id=hook_id, repeat_allowed=repeat_allowed)
    # Fix double-count: act_body binds all segments AND segment_order lists them — occupancy
    # should count delivery timeline uses, not slot bindings + order. Count only segment_order
    # plus hook extra if hook listed twice in bindings outside order.
    # Simpler: occupancy on segment_order only; hook reel documents extra intentional replay.
    occ_violations = []
    counts: dict[str, int] = {}
    for sid in segment_order:
        counts[sid] = counts.get(sid, 0) + 1
    for sid, n in counts.items():
        if n > 1:
            occ_violations.append(f"segment_id:{sid}:count={n}")

    doc: dict[str, Any] = {
        "schema_version": 1,
        "policy_hash": "",
        "axes": axes,
        "slot_plan": slot_plan,
        "segment_order": segment_order,
        "hook_reel": {"segment_id": hook_id, "repeat_allowed": bool(repeat_allowed and hook_id)},
        "speaker_volleys": speaker_volleys,
        "omit_reasons": omit_reasons,
        "rationale": rationale[:40],
        "integrity": {"ok": ok, "flags": flags},
        "occupancy": {"violations": occ_violations},
        "compact_digest": "",
    }
    # Bind Shape plan only when plan_status is complete (HM-3).
    if ctx.artifact_exists("mastering/mastering_plan.json"):
        try:
            plan = ctx.read_json("mastering/mastering_plan.json")
        except Exception:
            plan = None
        if isinstance(plan, dict):
            from interview_mux.mastering_plan_loader import plan_is_authoritative

            if not plan_is_authoritative(plan):
                plan = None
        if isinstance(plan, dict):
            mode = str(
                plan.get("confirmed_mode")
                or plan.get("narrative_mode")
                or plan.get("provisional_mode")
                or ""
            ).strip()
            if mode:
                axes = dict(doc.get("axes") or {})
                axes["narrative_mode"] = mode
                doc["axes"] = axes
                doc["mastering_plan_bound"] = True
                rationale.append(f"mastering_plan_mode={mode}")
            cold = plan.get("cold_open") if isinstance(plan.get("cold_open"), dict) else {}
            cold_seg = str(cold.get("segment_id") or "").strip()
            if cold_seg and cold.get("kind") in {"segment_hook", "vo_plus_segment"}:
                doc["hook_reel"] = {
                    "segment_id": cold_seg,
                    "repeat_allowed": True,
                    "source": "mastering_plan_cold_open",
                }
                for s in doc.get("slot_plan") or []:
                    if isinstance(s, dict) and s.get("component_id") == "STD_cold_open_slot":
                        s["bound_segment_ids"] = [cold_seg]
                        s["repeat_allowed"] = True
                rationale.append(f"mastering_plan_cold_open={cold_seg}")
            plan_order = [str(s) for s in (plan.get("ordered_segment_ids") or []) if s]
            if plan_order:
                # Prefer plan air order when it covers most current segments.
                known = set(segment_order)
                filtered = [s for s in plan_order if s in known]
                if len(filtered) >= max(1, int(len(known) * 0.5)):
                    missing = [s for s in segment_order if s not in set(filtered)]
                    doc["segment_order"] = filtered + missing
                    rationale.append("mastering_plan_segment_order")
            doc["rationale"] = rationale[:40]
    doc["compact_digest"] = build_compact_digest(doc)
    doc["policy_hash"] = _policy_hash(doc)
    return doc


def load_episode_structure(ctx: RunContext) -> dict[str, Any] | None:
    try:
        if not ctx.artifact_exists(STRUCTURE_PATH):
            return None
        data = ctx.read_json(STRUCTURE_PATH)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def compact_for_volley(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Compact episode structure for an LLM volley (message packet). See volley-glossary.md."""
    if not doc:
        return None
    from interview_mux.speaker_volley import compact_speaker_volleys_for_llm_volley

    return {
        "axes": doc.get("axes") or {},
        "slot_plan": [
            {
                "component_id": s.get("component_id"),
                "gate": s.get("gate"),
                "music_transition": s.get("music_transition"),
                "placement": s.get("placement"),
                "repeat_allowed": bool(s.get("repeat_allowed")),
                "bound_segment_ids": list(s.get("bound_segment_ids") or [])[:40],
            }
            for s in (doc.get("slot_plan") or [])
            if isinstance(s, dict)
        ][:24],
        "segment_order": list(doc.get("segment_order") or [])[:60],
        "hook_reel": doc.get("hook_reel") or {},
        "speaker_volleys": compact_speaker_volleys_for_llm_volley(
            list(doc.get("speaker_volleys") or []) if isinstance(doc.get("speaker_volleys"), list) else []
        )[:40],
        "omit_high_profile": [
            o.get("component_id")
            for o in (doc.get("omit_reasons") or [])
            if isinstance(o, dict)
            and str(o.get("component_id") or "")
            in ("STD_payoff_close", "STD_outro_button", "STD_cold_open_slot", "STD_orientation")
        ],
        "integrity_ok": bool((doc.get("integrity") or {}).get("ok", True)),
    }


# Glossary alias: this compact feeds an LLM volley, not a speaker-volley timeline edit.
compact_for_llm_volley = compact_for_volley


def attach_episode_structure_to_payload(ctx: RunContext, payload: dict[str, Any]) -> dict[str, Any]:
    doc = load_episode_structure(ctx)
    compact = compact_for_volley(doc)
    if not compact:
        return payload
    out = dict(payload)
    out["episode_structure"] = compact
    out["_extra_digest_paths"] = list(out.get("_extra_digest_paths") or []) + [
        STRUCTURE_PATH,
        COMPACT_DIGEST_PATH,
    ]
    return out


def persist_structure(ctx: RunContext, doc: dict[str, Any], *, stage: str) -> None:
    from interview_mux.prompt_validation import validate_episode_structure

    errors = validate_episode_structure(doc)
    lint_errs = lint_episode_structure(doc)
    soft_lint = [e for e in lint_errs if e == "integrity_failed" or e.startswith("occupancy:")]
    hard_lint = [e for e in lint_errs if e not in soft_lint]
    if soft_lint:
        ctx.log(
            f"episode_structure lint warnings: {', '.join(soft_lint[:4])}",
            level="warning",
            stage=stage,
        )
    all_errs = errors + hard_lint
    if all_errs:
        raise ValueError(f"episode_structure invalid: {all_errs[:5]}")
    ctx.write_json(STRUCTURE_PATH, doc)
    digest = str(doc.get("compact_digest") or build_compact_digest(doc))
    commit_episode_structure_compact(ctx, digest, stage_key=stage)
    ctx.log(
        f"episode_structure: {len(doc.get('slot_plan') or [])} slots, "
        f"{len(doc.get('omit_reasons') or [])} omits, integrity_ok={(doc.get('integrity') or {}).get('ok')}",
        level="success",
        stage=stage,
    )


def refresh_episode_structure(ctx: RunContext) -> dict[str, Any]:
    """Re-bind after ranking / transitions; persist updated structure."""
    if not structure_enabled():
        return {}
    doc = build_episode_structure(ctx, refresh=True)
    persist_structure(ctx, doc, stage="sound_design_plan")
    return doc


def persist_structure_skip_stub(ctx: RunContext) -> dict[str, Any]:
    """HG-2 2A: schema-valid disabled stub (empty slot_plan; skipped is extra-ok)."""
    stub: dict[str, Any] = {
        "schema_version": 1,
        "policy_hash": "disabled",
        "axes": {},
        "slot_plan": [],
        "segment_order": [],
        "hook_reel": {"segment_id": None, "repeat_allowed": False},
        "omit_reasons": [],
        "rationale": ["disabled"],
        "integrity": {"ok": True, "flags": ["feature_disabled"]},
        "occupancy": {"violations": []},
        "skipped": "feature_disabled",
    }
    ctx.write_json(STRUCTURE_PATH, stub, stage_key="episode_structure_compose")
    commit_episode_structure_compact(
        ctx, "disabled", stage_key="episode_structure_compose"
    )
    from interview_mux.stage_completion import heal_or_refuse_mark

    heal_or_refuse_mark(ctx, "episode_structure_compose", force=True)
    return stub


def run_episode_structure_compose(ctx: RunContext) -> None:
    from interview_mux.stage_completion import heal_or_refuse_mark
    from interview_mux.stages.segmentation import _assert_boundary_quality

    # Late drift hard-stop before delivery handoff.
    _assert_boundary_quality(ctx)
    if not structure_enabled():
        ctx.log("episode_structure_compose skipped (structure.enabled=false)", level="info", stage="episode_structure_compose")
        persist_structure_skip_stub(ctx)
        return
    with logged_step("episode_structure_compose/build", ctx=ctx, stage="episode_structure_compose"):
        doc = build_episode_structure(ctx, refresh=False)
        persist_structure(ctx, doc, stage="episode_structure_compose")
        # Fill LX-03 reserved section content into compact note artifact (docs prompt stays template)
        ctx.log(
            f"episode_structure_compose axes={doc.get('axes')}",
            level="info",
            stage="episode_structure_compose",
            detail={"omit_count": len(doc.get("omit_reasons") or [])},
        )
    try:
        from interview_mux.analysis_memory import update_completion_from_analysis
        from interview_mux.pipeline import maybe_finalize_shared_analysis

        update_completion_from_analysis(ctx)
        maybe_finalize_shared_analysis(ctx)
    except Exception as exc:  # noqa: BLE001
        ctx.log(
            f"analysis completion refresh skipped: {exc}",
            level="warning",
            stage="episode_structure_compose",
        )
    heal_or_refuse_mark(ctx, "episode_structure_compose", force=True)
