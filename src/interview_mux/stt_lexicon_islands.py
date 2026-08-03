"""STT lexicon-island group scanner + soft prefer-include priors (boost-only).

Systematically evaluates segment groups for mid-run STT weakness caused by
domain lexicon, code-switch/Spanglish, or passionate delivery. Fitting groups
get a soft prefer-include prior; non-fitting groups stay neutral (no demotion).
"""

from __future__ import annotations

import re
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

ISLANDS_PATH = "analysis/stt_lexicon_islands.json"
BOOSTS_PATH = "analysis/stt_lexicon_island_boosts.json"

_NON_ASCII = re.compile(r"[^\x00-\x7f]")
_COMMON_EN = frozenset(
    """
    the a an and or but if then so to of in on at for with from by as is was are were be been being
    i you he she it we they me him her us them my your his its our their this that these those
    not no yes yeah um uh like just really very also can could would should will shall may might
    what when where who why how which about into over after before up down out all any some more
    most other new only own same such than too both few many much under again further once
    """.split()
)

_STT_NOISE_EXCLUDE_RE = re.compile(
    r"low[_\s-]?quality|stt|transcript|unintelligib|asr|speech.?to.?text|confidence",
    re.I,
)


def stt_lexicon_islands_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = cfg if cfg is not None else merged_config()
    analysis = resolved.get("analysis") or {}
    block = analysis.get("stt_lexicon_islands") if isinstance(analysis.get("stt_lexicon_islands"), dict) else {}
    probes = resolved.get("audio_probes") or {}
    low_default = float(probes.get("low_confidence_threshold") or 0.85)
    return {
        "enabled": True,
        "low_confidence_threshold": low_default,
        "high_confidence_threshold": 0.90,
        "min_pad_words": 3,
        "min_pad_words_passion": 2,
        "max_pad_gap_ms": 600,
        "max_island_words": 12,
        "max_island_ms": 8000,
        "max_candidates_for_llm": 40,
        "verify_importance_min": 0.65,
        "soft_boost_strength": 0.15,
        "auto_pack_protect_min_boost": 0.65,
        "passion_boost_multiplier": 1.25,
        "vernacular_boost_multiplier": 1.25,
        "sibling_cohesion_enabled": True,
        **block,
    }


def enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(stt_lexicon_islands_cfg(cfg).get("enabled", True))


def _word_conf(w: dict[str, Any]) -> float:
    try:
        if w.get("confidence") is None:
            return 1.0
        return float(w["confidence"])
    except (TypeError, ValueError):
        return 1.0


def _word_ms(w: dict[str, Any], key: str) -> int:
    try:
        return int(w.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _norm_token(text: str) -> str:
    return str(text or "").strip(".,!?;:\"'()[]").lower()


def _has_non_ascii(text: str) -> bool:
    return bool(_NON_ASCII.search(text or ""))


def _lexicon_hint(island_words: list[dict[str, Any]]) -> str:
    texts = [str(w.get("text") or "") for w in island_words]
    joined = " ".join(texts)
    if any(_has_non_ascii(t) for t in texts):
        return "non_ascii"
    toks = [_norm_token(t) for t in texts]
    toks = [t for t in toks if t.isalpha() and len(t) > 2]
    if not toks:
        return "none"
    uncommon = sum(1 for t in toks if t not in _COMMON_EN and t.isascii())
    if uncommon / max(len(toks), 1) >= 0.5:
        return "uncommon_english"
    return "none"


def _is_one_off_common(island_words: list[dict[str, Any]]) -> bool:
    if len(island_words) != 1:
        return False
    hint = _lexicon_hint(island_words)
    if hint != "none":
        return False
    tok = _norm_token(str(island_words[0].get("text") or ""))
    return bool(tok) and (tok in _COMMON_EN or len(tok) <= 4)


def _find_islands(
    words: list[dict[str, Any]],
    *,
    low_conf: float,
    max_island_words: int,
    max_island_ms: int,
) -> list[tuple[int, int]]:
    """Return inclusive index ranges (start, end) of low-conf contiguous runs."""
    islands: list[tuple[int, int]] = []
    i = 0
    n = len(words)
    while i < n:
        if _word_conf(words[i]) >= low_conf:
            i += 1
            continue
        j = i
        while j + 1 < n and _word_conf(words[j + 1]) < low_conf:
            j += 1
        island = words[i : j + 1]
        dur = _word_ms(island[-1], "end_ms") - _word_ms(island[0], "start_ms")
        if len(island) <= max_island_words and dur <= max_island_ms:
            islands.append((i, j))
        i = j + 1
    return islands


def _pad_ok(
    words: list[dict[str, Any]],
    start: int,
    end: int,
    *,
    high_conf: float,
    min_pad: int,
    max_gap_ms: int,
) -> tuple[bool, list[dict[str, Any]], list[dict[str, Any]]]:
    left: list[dict[str, Any]] = []
    right: list[dict[str, Any]] = []
    # left pad walking backward
    k = start - 1
    while k >= 0 and len(left) < min_pad:
        w = words[k]
        if _word_conf(w) < high_conf:
            break
        if left:
            gap = _word_ms(left[0], "start_ms") - _word_ms(w, "end_ms")
            if gap > max_gap_ms:
                break
        left.insert(0, w)
        k -= 1
    # right pad walking forward
    k = end + 1
    while k < len(words) and len(right) < min_pad:
        w = words[k]
        if _word_conf(w) < high_conf:
            break
        if right:
            gap = _word_ms(w, "start_ms") - _word_ms(right[-1], "end_ms")
            if gap > max_gap_ms:
                break
        right.append(w)
        k += 1
    return len(left) >= min_pad and len(right) >= min_pad, left, right


def _segments_for_window(
    segments: list[dict[str, Any]],
    start_ms: int,
    end_ms: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        try:
            s = int(seg.get("start_ms") or 0)
            e = int(seg.get("end_ms") or s)
        except (TypeError, ValueError):
            continue
        if e < start_ms or s > end_ms:
            continue
        out.append(seg)
    return out


def _probe_flags_for_window(ctx: RunContext, start_ms: int, end_ms: int) -> dict[str, Any]:
    flags: dict[str, Any] = {
        "is_special": False,
        "non_english": False,
        "uncommon_english": False,
        "passion_level": None,
        "affect_burst": False,
        "pull_quote": False,
        "keywords": [],
        "listen_text": None,
        "acoustic_stress": 0.0,
    }
    if ctx.artifact_exists("vernacular/audio_tags_by_flow.json"):
        try:
            doc = ctx.read_json("vernacular/audio_tags_by_flow.json")
            by_flow = doc.get("by_flow") if isinstance(doc, dict) else {}
            if isinstance(by_flow, dict):
                for tags in by_flow.values():
                    if not isinstance(tags, dict):
                        continue
                    # flow tags may include timing
                    fs = int(tags.get("start_ms") or 0)
                    fe = int(tags.get("end_ms") or fs)
                    if fe and (fe < start_ms or fs > end_ms):
                        continue
                    if tags.get("is_special") or tags.get("vernacular"):
                        flags["is_special"] = True
                    if tags.get("non_english"):
                        flags["non_english"] = True
                    if tags.get("uncommon_english"):
                        flags["uncommon_english"] = True
                    pl = tags.get("passion_level")
                    if pl:
                        flags["passion_level"] = pl
                    if tags.get("affect_burst"):
                        flags["affect_burst"] = True
                    if tags.get("pull_quote"):
                        flags["pull_quote"] = True
                    kws = tags.get("keywords") or []
                    if isinstance(kws, list):
                        flags["keywords"] = list(dict.fromkeys([*flags["keywords"], *[str(k) for k in kws[:8]]]))[:12]
                    listen = tags.get("listen_text") or tags.get("fused_text")
                    if listen and not flags["listen_text"]:
                        flags["listen_text"] = str(listen)[:400]
        except Exception:
            pass
    if ctx.artifact_exists("analysis/run_golden_facts.json"):
        try:
            gf = ctx.read_json("analysis/run_golden_facts.json")
            run = gf.get("run") if isinstance(gf, dict) else {}
            if isinstance(run, dict):
                if run.get("has_non_english_spans"):
                    flags["non_english"] = True
                if run.get("has_uncommon_english"):
                    flags["uncommon_english"] = True
                if run.get("has_high_passion"):
                    flags["passion_level"] = flags["passion_level"] or "high"
                if run.get("has_affect_burst"):
                    flags["affect_burst"] = True
                if run.get("has_pull_quote"):
                    flags["pull_quote"] = True
                if run.get("has_in_flow_vernacular"):
                    flags["is_special"] = True
        except Exception:
            pass
    if ctx.artifact_exists("transcript/review_queue.json"):
        try:
            queue = ctx.read_json("transcript/review_queue.json")
            for chunk in queue.get("chunks") or []:
                if not isinstance(chunk, dict):
                    continue
                cs = int(chunk.get("start_ms") or 0)
                ce = int(chunk.get("end_ms") or cs)
                if ce < start_ms or cs > end_ms:
                    continue
                flags["acoustic_stress"] = max(
                    float(flags["acoustic_stress"] or 0),
                    float(chunk.get("acoustic_stress_score") or 0),
                )
        except Exception:
            pass
    return flags


def _passion_corroborated(flags: dict[str, Any]) -> bool:
    if str(flags.get("passion_level") or "").lower() == "high":
        return True
    if flags.get("affect_burst") or flags.get("pull_quote"):
        return True
    return float(flags.get("acoustic_stress") or 0) >= 0.35


def _build_parent_sibling_groups(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        parent = str(seg.get("parent_segment_id") or "")
        if not parent:
            continue
        by_parent.setdefault(parent, []).append(seg)
    groups: list[dict[str, Any]] = []
    for parent, kids in by_parent.items():
        specials = [k for k in kids if (k.get("audio_tags") or {}).get("is_special") or k.get("retention") == "must_keep"]
        if len(specials) < 1 or len(kids) < 2:
            continue
        sids = [str(k.get("segment_id")) for k in kids if k.get("segment_id")]
        start_ms = min(int(k.get("start_ms") or 0) for k in kids)
        end_ms = max(int(k.get("end_ms") or 0) for k in kids)
        groups.append(
            {
                "group_kind": "parent_siblings",
                "parent_segment_id": parent,
                "segment_ids": sids,
                "sibling_segment_ids": [str(k.get("segment_id")) for k in specials if k.get("segment_id")],
                "start_ms": start_ms,
                "end_ms": end_ms,
            }
        )
    return groups


def _evidence_strength(group: dict[str, Any]) -> float:
    ev = group.get("evidence") or {}
    mean_c = float(ev.get("mean_island_conf") if ev.get("mean_island_conf") is not None else 0.5)
    words = float(ev.get("island_word_count") or 1)
    class_bonus = {
        "passion_burst": 0.2,
        "code_switch_run": 0.25,
        "padded_lexicon": 0.15,
    }.get(str(group.get("island_class") or ""), 0.0)
    return (1.0 - mean_c) * min(words, 8.0) + class_bonus * 2.0


def scan_stt_lexicon_groups(ctx: RunContext, *, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Full-sweep group evaluation; writes ISLANDS_PATH. Boost-only (no demotion)."""
    conf = stt_lexicon_islands_cfg(cfg)
    empty = {
        "version": 1,
        "mode": "evaluate_all_groups_soft_boost_only",
        "enabled": bool(conf.get("enabled", True)),
        "low_confidence_threshold": float(conf["low_confidence_threshold"]),
        "high_confidence_threshold": float(conf["high_confidence_threshold"]),
        "groups": [],
        "candidate_count": 0,
    }
    if not conf.get("enabled", True):
        empty["skip_reason"] = "disabled"
        ctx.write_json(ISLANDS_PATH, empty)
        return empty
    if not ctx.artifact_exists("transcript/full.json") or not ctx.artifact_exists("segments/manifest.json"):
        empty["skip_reason"] = "missing_transcript_or_manifest"
        ctx.write_json(ISLANDS_PATH, empty)
        return empty

    transcript = ctx.read_json("transcript/full.json")
    manifest = ctx.read_json("segments/manifest.json")
    words_raw = [w for w in (transcript.get("words") or []) if isinstance(w, dict) and str(w.get("text") or "").strip()]
    segments = [s for s in (manifest.get("segments") or []) if isinstance(s, dict) and s.get("segment_id")]

    low = float(conf["low_confidence_threshold"])
    high = float(conf["high_confidence_threshold"])
    min_pad = int(conf["min_pad_words"])
    min_pad_passion = int(conf["min_pad_words_passion"])
    max_gap = int(conf["max_pad_gap_ms"])
    max_iw = int(conf["max_island_words"])
    max_ims = int(conf["max_island_ms"])

    # Partition words into speaker turns (flows)
    flows: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    cur_spk: str | None = None
    for w in words_raw:
        spk = str(w.get("speaker_id") or w.get("speaker") or "spk_unknown")
        if cur and spk != cur_spk:
            flows.append(cur)
            cur = []
        cur_spk = spk
        cur.append(w)
    if cur:
        flows.append(cur)

    groups: list[dict[str, Any]] = []
    gid = 0

    for flow in flows:
        islands = _find_islands(flow, low_conf=low, max_island_words=max_iw, max_island_ms=max_ims)
        flow_start = _word_ms(flow[0], "start_ms")
        flow_end = _word_ms(flow[-1], "end_ms")
        segs = _segments_for_window(segments, flow_start, flow_end)
        sids = [str(s.get("segment_id")) for s in segs if s.get("segment_id")]
        if not islands:
            gid += 1
            groups.append(
                {
                    "group_id": f"grp_{gid:03d}",
                    "group_kind": "turn_window",
                    "segment_ids": sids,
                    "candidate_fit": False,
                    "island_class": None,
                    "skip_reason": "no_low_conf_island",
                    "evidence": {"start_ms": flow_start, "end_ms": flow_end},
                }
            )
            continue

        # One evaluation row per island inside the turn (still systematic)
        for start_i, end_i in islands:
            gid += 1
            island_words = flow[start_i : end_i + 1]
            isl_start = _word_ms(island_words[0], "start_ms")
            isl_end = _word_ms(island_words[-1], "end_ms")
            flags = _probe_flags_for_window(ctx, isl_start, isl_end)
            passion = _passion_corroborated(flags)
            pad_words = min_pad_passion if passion else min_pad
            ok, left, right = _pad_ok(
                flow, start_i, end_i, high_conf=high, min_pad=pad_words, max_gap_ms=max_gap
            )
            hint = _lexicon_hint(island_words)
            overlapping = _segments_for_window(segments, isl_start, isl_end)
            # Prefer special children when present
            special_overlap = [
                s
                for s in overlapping
                if (s.get("audio_tags") or {}).get("is_special") or s.get("retention") == "must_keep"
            ]
            use_segs = special_overlap or overlapping or segs
            use_ids = [str(s.get("segment_id")) for s in use_segs if s.get("segment_id")]

            island_class: str | None = None
            skip: str | None = None
            if _is_one_off_common(island_words) and not passion and not flags.get("is_special"):
                skip = "one_off_common_brick"
            elif flags.get("is_special") or flags.get("non_english") or hint == "non_ascii":
                island_class = "code_switch_run" if ok or flags.get("is_special") else None
                if island_class is None and not ok:
                    skip = "one_sided_pad"
            elif passion and (ok or len(left) >= 1 and len(right) >= 1):
                # passion_burst may use looser pads; require at least one high-conf neighbor each side
                weak_ok, left2, right2 = _pad_ok(
                    flow, start_i, end_i, high_conf=high, min_pad=1, max_gap_ms=max_gap
                )
                if weak_ok or ok:
                    island_class = "passion_burst"
                    left, right = (left if ok else left2), (right if ok else right2)
                    ok = True
                else:
                    skip = "one_sided_pad"
            elif ok and (hint in {"uncommon_english", "non_ascii"} or len(island_words) >= 2):
                island_class = "padded_lexicon"
            elif ok:
                island_class = "padded_lexicon"
            else:
                skip = "one_sided_pad" if (left or right) else "no_corroboration"

            if island_class and ok:
                skip = None
            elif island_class is None and skip is None:
                skip = "no_corroboration"

            confs = [_word_conf(w) for w in island_words]
            mean_c = sum(confs) / max(len(confs), 1)
            groups.append(
                {
                    "group_id": f"grp_{gid:03d}",
                    "group_kind": "turn_window",
                    "segment_ids": use_ids,
                    "candidate_fit": bool(island_class and skip is None),
                    "island_class": island_class,
                    "skip_reason": skip,
                    "evidence": {
                        "start_ms": isl_start,
                        "end_ms": isl_end,
                        "mean_island_conf": round(mean_c, 4),
                        "island_word_count": len(island_words),
                        "island_text": " ".join(str(w.get("text") or "") for w in island_words)[:200],
                        "left_pad_text": " ".join(str(w.get("text") or "") for w in left)[:200],
                        "right_pad_text": " ".join(str(w.get("text") or "") for w in right)[:200],
                        "pad_ok": ok,
                        "lexicon_hint": hint,
                        "probes": {
                            "is_special": flags.get("is_special"),
                            "non_english": flags.get("non_english"),
                            "uncommon_english": flags.get("uncommon_english"),
                            "passion_level": flags.get("passion_level"),
                            "affect_burst": flags.get("affect_burst"),
                            "pull_quote": flags.get("pull_quote"),
                            "acoustic_stress": flags.get("acoustic_stress"),
                            "keywords": flags.get("keywords") or [],
                        },
                        "listen_available": bool(flags.get("listen_text")),
                        "listen_text": flags.get("listen_text"),
                    },
                }
            )

    # parent_siblings groups (code-switch cohesion units)
    for sib in _build_parent_sibling_groups(segments):
        gid += 1
        flags = _probe_flags_for_window(ctx, int(sib["start_ms"]), int(sib["end_ms"]))
        groups.append(
            {
                "group_id": f"grp_{gid:03d}",
                "group_kind": "parent_siblings",
                "segment_ids": sib["segment_ids"],
                "sibling_segment_ids": sib.get("sibling_segment_ids") or [],
                "parent_segment_id": sib.get("parent_segment_id"),
                "candidate_fit": True,
                "island_class": "code_switch_run",
                "skip_reason": None,
                "evidence": {
                    "start_ms": sib["start_ms"],
                    "end_ms": sib["end_ms"],
                    "mean_island_conf": None,
                    "island_word_count": 0,
                    "island_text": "",
                    "left_pad_text": "",
                    "right_pad_text": "",
                    "pad_ok": True,
                    "lexicon_hint": "non_ascii" if flags.get("non_english") else "uncommon_english",
                    "probes": {
                        "is_special": True,
                        "non_english": flags.get("non_english"),
                        "uncommon_english": flags.get("uncommon_english"),
                        "passion_level": flags.get("passion_level"),
                        "affect_burst": flags.get("affect_burst"),
                        "pull_quote": flags.get("pull_quote"),
                        "acoustic_stress": flags.get("acoustic_stress"),
                        "keywords": flags.get("keywords") or [],
                    },
                    "listen_available": bool(flags.get("listen_text")),
                    "listen_text": flags.get("listen_text"),
                },
            }
        )

    candidates = [g for g in groups if g.get("candidate_fit")]
    candidates.sort(key=_evidence_strength, reverse=True)
    cap = int(conf.get("max_candidates_for_llm") or 40)
    selected_ids = {g["group_id"] for g in candidates[:cap]}
    for g in groups:
        if g.get("candidate_fit") and g["group_id"] not in selected_ids:
            g["candidate_fit"] = False
            g["skip_reason"] = "over_llm_cap"
            g["was_structural_fit"] = True

    out = {
        "version": 1,
        "mode": "evaluate_all_groups_soft_boost_only",
        "enabled": True,
        "low_confidence_threshold": low,
        "high_confidence_threshold": high,
        "groups": groups,
        "candidate_count": len([g for g in groups if g.get("candidate_fit")]),
        "group_count": len(groups),
    }
    ctx.write_json(ISLANDS_PATH, out)
    return out


def candidate_groups_for_llm(islands_doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [g for g in (islands_doc.get("groups") or []) if isinstance(g, dict) and g.get("candidate_fit")]


def specialist_input_from_ctx(ctx: RunContext) -> dict[str, Any]:
    islands = ctx.read_json(ISLANDS_PATH) if ctx.artifact_exists(ISLANDS_PATH) else scan_stt_lexicon_groups(ctx)
    cands = candidate_groups_for_llm(islands if isinstance(islands, dict) else {})
    thesis = ""
    if ctx.artifact_exists("understanding/content_brief.json"):
        try:
            brief = ctx.read_json("understanding/content_brief.json")
            if isinstance(brief, dict):
                thesis = str(brief.get("thesis") or brief.get("working_thesis") or "")[:400]
        except Exception:
            thesis = ""
    slim = []
    for g in cands:
        ev = g.get("evidence") or {}
        slim.append(
            {
                "group_id": g.get("group_id"),
                "group_kind": g.get("group_kind"),
                "segment_ids": g.get("segment_ids") or [],
                "sibling_segment_ids": g.get("sibling_segment_ids") or [],
                "island_class": g.get("island_class"),
                "left_pad_text": ev.get("left_pad_text"),
                "island_text": ev.get("island_text"),
                "right_pad_text": ev.get("right_pad_text"),
                "mean_island_conf": ev.get("mean_island_conf"),
                "lexicon_hint": ev.get("lexicon_hint"),
                "probes": ev.get("probes") or {},
                "listen_text": ev.get("listen_text"),
            }
        )
    return {
        "task": "For each candidate group, decide whether STT-weak mid-run speech still carries important meaning. Soft-boost only; never exclude or demote other segments.",
        "thesis": thesis,
        "candidate_groups": slim,
    }


def load_group_verdicts(ctx: RunContext, parent_stage: str = "full_master_ranking") -> list[dict[str, Any]]:
    rel = f"understanding/stage_runs/{parent_stage}/specialist_stt_lexicon_island_verify.json"
    if not ctx.artifact_exists(rel):
        return []
    try:
        env = ctx.read_json(rel)
    except Exception:
        return []
    arts = env.get("artifacts") if isinstance(env, dict) else {}
    rows = (arts or {}).get("group_verdicts") or []
    return [r for r in rows if isinstance(r, dict)]


def build_stt_trust_priors(
    ctx: RunContext,
    *,
    cfg: dict[str, Any] | None = None,
    verdicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fuse LLM verdicts + probe multipliers into boost-only priors."""
    conf = stt_lexicon_islands_cfg(cfg)
    min_imp = float(conf.get("verify_importance_min") or 0.65)
    strength = float(conf.get("soft_boost_strength") or 0.15)
    passion_m = float(conf.get("passion_boost_multiplier") or 1.25)
    vern_m = float(conf.get("vernacular_boost_multiplier") or 1.25)
    cohesion = bool(conf.get("sibling_cohesion_enabled", True))

    islands = ctx.read_json(ISLANDS_PATH) if ctx.artifact_exists(ISLANDS_PATH) else {"groups": []}
    by_gid = {
        str(g.get("group_id")): g
        for g in (islands.get("groups") or [])
        if isinstance(g, dict) and g.get("group_id")
    }
    rows = verdicts if verdicts is not None else load_group_verdicts(ctx)
    priors_by_sid: dict[str, dict[str, Any]] = {}
    boost_rows: list[dict[str, Any]] = []

    for v in rows:
        if not v.get("boost_recommended") and not v.get("fits_case"):
            continue
        score = float(v.get("importance_score") or 0)
        if score < min_imp:
            continue
        failure = str(v.get("failure_mode") or "uncertain")
        if failure == "noise":
            continue
        gid = str(v.get("group_id") or "")
        g = by_gid.get(gid) or {}
        ev = g.get("evidence") or {}
        probes = ev.get("probes") if isinstance(ev.get("probes"), dict) else {}
        mult = 1.0
        reasons = [failure or str(g.get("island_class") or "padded_lexicon")]
        if failure == "passion" or g.get("island_class") == "passion_burst" or str(probes.get("passion_level") or "").lower() == "high":
            mult *= passion_m
            reasons.append("passion")
        if (
            failure == "code_switch"
            or g.get("island_class") == "code_switch_run"
            or probes.get("is_special")
            or probes.get("non_english")
        ):
            mult *= vern_m
            reasons.append("vernacular")
        if failure == "domain_lexicon" or g.get("island_class") == "padded_lexicon":
            reasons.append("domain_lexicon")

        soft = min(0.5, max(0.0, score * strength * mult))
        sids = [str(s) for s in (v.get("segment_ids") or g.get("segment_ids") or []) if s]
        siblings = [str(s) for s in (g.get("sibling_segment_ids") or []) if s]
        if cohesion:
            for s in siblings:
                if s not in sids:
                    sids.append(s)
        boost_rows.append(
            {
                "group_id": gid,
                "segment_ids": sids,
                "sibling_segment_ids": siblings,
                "importance_score": score,
                "soft_boost": round(soft, 4),
                "failure_mode": failure,
                "rationale": str(v.get("rationale") or "")[:300],
                "reasons": list(dict.fromkeys(reasons)),
            }
        )
        for sid in sids:
            prev = priors_by_sid.get(sid)
            if prev is None or soft > float(prev.get("soft_boost") or 0):
                priors_by_sid[sid] = {
                    "segment_id": sid,
                    "soft_boost": round(soft, 4),
                    "reasons": list(dict.fromkeys(reasons)),
                    "group_ids": [gid] if gid else [],
                    "importance_score": score,
                }
            else:
                prev["group_ids"] = list(dict.fromkeys([*(prev.get("group_ids") or []), gid]))
                prev["reasons"] = list(dict.fromkeys([*(prev.get("reasons") or []), *reasons]))

    doc = {
        "version": 1,
        "mode": "soft_prefer_include_only",
        "priors": sorted(priors_by_sid.values(), key=lambda r: float(r.get("soft_boost") or 0), reverse=True),
        "boosts": boost_rows,
        "verify_importance_min": min_imp,
    }
    ctx.write_json(BOOSTS_PATH, doc)
    return doc


def load_stt_trust_priors(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists(BOOSTS_PATH):
        return []
    try:
        doc = ctx.read_json(BOOSTS_PATH)
    except Exception:
        return []
    rows = doc.get("priors") if isinstance(doc, dict) else None
    return [r for r in (rows or []) if isinstance(r, dict) and r.get("segment_id")]


def soft_protect_segment_ids(ctx: RunContext, *, cfg: dict[str, Any] | None = None) -> set[str]:
    conf = stt_lexicon_islands_cfg(cfg)
    floor = float(conf.get("auto_pack_protect_min_boost") or 0.65)
    # soft_boost is scaled (importance * strength * mult); also accept importance_score
    ids: set[str] = set()
    for row in load_stt_trust_priors(ctx):
        soft = float(row.get("soft_boost") or 0)
        imp = float(row.get("importance_score") or 0)
        # Protect when importance cleared threshold OR soft_boost is material
        if imp >= floor or soft >= float(conf.get("soft_boost_strength") or 0.15) * 0.8:
            ids.add(str(row["segment_id"]))
    return ids


def sibling_map_from_boosts(ctx: RunContext) -> dict[str, list[str]]:
    if not ctx.artifact_exists(BOOSTS_PATH):
        return {}
    try:
        doc = ctx.read_json(BOOSTS_PATH)
    except Exception:
        return {}
    out: dict[str, list[str]] = {}
    for row in doc.get("boosts") or []:
        if not isinstance(row, dict):
            continue
        sids = [str(s) for s in (row.get("segment_ids") or []) if s]
        siblings = [str(s) for s in (row.get("sibling_segment_ids") or []) if s]
        members = list(dict.fromkeys([*sids, *siblings]))
        for sid in members:
            out[sid] = [x for x in members if x != sid]
    return out


def enforce_stt_island_selection_guards(
    ctx: RunContext,
    selection: dict[str, Any],
    *,
    stage: str = "full_master_ranking",
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Anti-false-exclude + sibling cohesion for boosted groups only."""
    if not enabled(cfg):
        return selection
    conf = stt_lexicon_islands_cfg(cfg)
    protected = soft_protect_segment_ids(ctx, cfg=cfg)
    if not protected and not (conf.get("sibling_cohesion_enabled", True)):
        return selection

    out = dict(selection)
    ordered = [str(x) for x in (out.get("ordered_segment_ids") or []) if x]
    ordered_set = set(ordered)
    excluded_raw = list(out.get("excluded_segment_ids") or [])
    kept_excluded: list[Any] = []
    restored: list[str] = []

    def _exclude_sid_reason(row: Any) -> tuple[str, str]:
        if isinstance(row, dict):
            return str(row.get("segment_id") or ""), str(row.get("reason") or "")
        if isinstance(row, str):
            return row, ""
        return "", ""

    for row in excluded_raw:
        sid, reason = _exclude_sid_reason(row)
        if sid and sid in protected and _STT_NOISE_EXCLUDE_RE.search(reason or "low_quality"):
            # Only restore STT-noise style excludes; allow aside/duplicate
            if re.search(r"\b(aside|duplicate|covered_by_framing|operator)\b", reason or "", re.I):
                kept_excluded.append(row)
                continue
            if sid not in ordered_set:
                ordered.append(sid)
                ordered_set.add(sid)
                restored.append(sid)
            continue
        kept_excluded.append(row)

    # Sibling cohesion: if one boosted sibling is kept, soft-include other specials
    if conf.get("sibling_cohesion_enabled", True):
        sib_map = sibling_map_from_boosts(ctx)
        added_sibs: list[str] = []
        for sid in list(ordered):
            for sib in sib_map.get(sid) or []:
                if sib in ordered_set:
                    continue
                if sib not in protected and sib not in (sib_map.get(sid) or []):
                    continue
                # Only pull siblings that are in the boost set
                if sib not in protected and sid not in protected:
                    continue
                # Remove from excluded if present as STT-noise
                new_excl = []
                removed = False
                for row in kept_excluded:
                    esid, ereason = _exclude_sid_reason(row)
                    if esid == sib and (
                        not ereason
                        or _STT_NOISE_EXCLUDE_RE.search(ereason)
                        or not re.search(r"\b(aside|duplicate)\b", ereason, re.I)
                    ):
                        if re.search(r"\b(aside|duplicate)\b", ereason or "", re.I):
                            new_excl.append(row)
                        else:
                            removed = True
                        continue
                    new_excl.append(row)
                if removed or sib not in { _exclude_sid_reason(r)[0] for r in kept_excluded }:
                    # insert near sibling
                    try:
                        idx = ordered.index(sid) + 1
                    except ValueError:
                        idx = len(ordered)
                    ordered.insert(idx, sib)
                    ordered_set.add(sib)
                    added_sibs.append(sib)
                    kept_excluded = new_excl

        if added_sibs:
            ctx.log(
                f"STT island sibling cohesion: added {len(added_sibs)} segment(s)",
                level="info",
                stage=stage,
                action_id="stt_island.sibling_cohesion",
                detail={"added": added_sibs[:20]},
            )

    # Coverage safety: if a topic's only segments are protected and all excluded, restore one
    if ctx.artifact_exists("master/coverage_audit.json"):
        try:
            audit = ctx.read_json("master/coverage_audit.json")
            topic_maps = audit.get("topic_segment_map") or audit.get("topics") or []
            excl_ids = {_exclude_sid_reason(r)[0] for r in kept_excluded}
            for row in topic_maps if isinstance(topic_maps, list) else []:
                if not isinstance(row, dict):
                    continue
                segs = [str(s) for s in (row.get("segment_ids") or row.get("segments") or []) if s]
                if not segs:
                    continue
                if not all(s in protected for s in segs):
                    continue
                if any(s in ordered_set for s in segs):
                    continue
                # restore first protected segment for the topic
                pick = segs[0]
                ordered.append(pick)
                ordered_set.add(pick)
                kept_excluded = [r for r in kept_excluded if _exclude_sid_reason(r)[0] != pick]
                restored.append(pick)
                ctx.log(
                    f"STT island coverage safety: restored {pick} for topic-only boosted set",
                    level="info",
                    stage=stage,
                    action_id="stt_island.coverage_safety",
                    detail={"segment_id": pick},
                )
        except Exception:
            pass

    if restored:
        ctx.log(
            f"STT island exclude guard: restored {len(restored)} segment(s)",
            level="info",
            stage=stage,
            action_id="stt_island.exclude_guard",
            detail={"restored": restored[:20]},
        )

    out["ordered_segment_ids"] = ordered
    out["excluded_segment_ids"] = kept_excluded
    meta = dict(out.get("_meta") or {})
    meta["stt_lexicon_islands"] = {
        "restored": restored,
        "protected_count": len(protected),
    }
    out["_meta"] = meta
    return out
