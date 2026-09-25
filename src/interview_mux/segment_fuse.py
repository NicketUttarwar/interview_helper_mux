"""Chronological seam adjudication + fuse-into-one-segment rewrite (multi-call).

Deterministic code enumerates **every** adjacent pair in manifest order and applies
verdicts. Fuse repairs unfinished thoughts only (hanging setup, mid-clause open,
island-straddle). Same-speaker complete ideas stay independent. When the LLM is
unavailable the per-pair deterministic fallback uses the same incomplete-thought
predicates so no pair is ever left without a recorded verdict.

The pass is idempotent and safe to re-run after boundary edits, vernacular sanitize,
ranking heals, or junction-driven invalidation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from interview_mux.config import merged_config
from interview_mux.gap_vo_prior_context import (
    CROSS_SPEAKER_COMPLETION_GAP_MS,
    clause_continues_after,
    ends_complete_thought,
    ends_hanging_setup,
    last_spoken_sentence,
    later_opens_nominal_complement,
    opens_with_backchannel_completion,
    opens_with_clause_continuer,
)
from interview_mux.run_context import RunContext

SEAM_PACKETS_PATH = "analysis/connector_seam_packets.json"
SEAM_VERDICTS_PATH = "analysis/connector_seam_verdicts.json"
FUSE_AUDIT_PATH = "analysis/connector_fuse_audit.json"
FUSE_ROUNDS_PATH = "analysis/connector_fuse_rounds.json"
# S1: pre_ranking owns a dedicated rounds SSOT (not shared with analysis).
FUSE_ROUNDS_PRE_RANKING_PATH = "analysis/connector_fuse_rounds_pre_ranking.json"


def fuse_writer_stage(pass_id: str) -> str:
    """Map a fuse pass_id onto the pipeline stage that owns the write.

    HS-3: ``pre_ranking`` must not stamp shared bounds/manifest as the
    analysis pass (``connector_fuse_pass``).
    """
    blob = str(pass_id or "").strip()
    if blob == "pre_ranking" or blob.startswith("pre_ranking:") or blob.startswith("pre_ranking"):
        return "connector_fuse_pass_pre_ranking"
    return "connector_fuse_pass"


def fuse_rounds_path(pass_id: str) -> str:
    """Rounds artifact for this pass (analysis vs pre_ranking SSOTs)."""
    if is_pre_ranking_pass(pass_id):
        return FUSE_ROUNDS_PRE_RANKING_PATH
    return FUSE_ROUNDS_PATH


def persist_fuse_skip(
    ctx: RunContext,
    *,
    pass_id: str,
    skip_reason: str,
    rounds_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write rounds.json plus an audit stub so skip is not a hollow done.

    HS-3: analysis skip/disabled/empty-packet must leave
    ``analysis/connector_fuse_audit.json`` (keep rounds too).
    """
    doc = dict(rounds_doc or {})
    doc.setdefault("version", 1)
    doc.setdefault("pass_id", pass_id)
    doc.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
    doc.setdefault("rounds", [])
    doc.setdefault("total_applied", 0)
    doc.setdefault("fixed_point", True)
    doc["skip_reason"] = skip_reason
    ctx.write_json(fuse_rounds_path(pass_id), doc)
    # Analysis contract is the audit. Pre-ranking skip must not mint
    # connector_fuse_audit.json (that would look like the analysis pass ran).
    if fuse_writer_stage(pass_id) == "connector_fuse_pass":
        _append_audit(
            ctx,
            {
                "applied": 0,
                "applied_fuses": [],
                "stay_independent": [],
                "skipped": [],
                "skip_reason": skip_reason,
            },
            verdicts=[],
            pass_id=pass_id,
        )
    return doc

SEAM_STAGE_KEY = "connector_seam_adjudicate"
SEAM_PROMPT_REL = "segmentation/connector-seam-adjudicate.system.txt"

_FALLBACK_SYSTEM_PROMPT = """You adjudicate segment seams for a podcast editor.

For each pair you receive the earlier close, the last/first words joined by " | "
at the cut, and deterministic_hints. Read across the cut as if listening.

- Answer "fuse" ONLY when the earlier close is an unfinished sentence or hanging
  setup, or the later words open mid-clause (and/but/because/which/...), or a
  low-confidence island straddles the cut.
- Answer "stay_independent" when the earlier close already lands a complete idea
  — even if the same speaker keeps talking about the same topic. Same-speaker
  mid-flow is not a fuse reason.
- Prefer "stay_independent" when unsure. Prefer "fuse" only when
  deterministic_hints show hanging_setup_end, later_opens_continuer (and the
  earlier idea is not complete), or island_straddle.
- Never invent missing words. Judge only from the provided seam text and hints.

Return JSON only:
{"status":"complete","artifacts":{"verdicts":[{"pair_id":"...","decision":"fuse|stay_independent",
"fuse_direction":"into_earlier|into_later|null","reason_code":"mid_sentence_continue|island_straddle|clean_turn|topic_shift|speaker_change|complete_thought_stay|other",
"rationale":"one short sentence","confidence":0.0}]}}
"""

# Finite defaults when config uses 0 ("unset"). Use -1 only for explicit unlimited
# (forensics). DEEP-FUSE-01: 0 must never mean 10_000 / 10_000_000.
_FINITE_DEFAULT_FUSES_PER_PASS = 24
_FINITE_DEFAULT_FUSE_ROUNDS = 8

_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "max_fuses_per_pass": _FINITE_DEFAULT_FUSES_PER_PASS,
    "max_fuse_rounds": _FINITE_DEFAULT_FUSE_ROUNDS,
    "allow_cross_speaker_fuse": False,
    "tail_words": 16,
    "head_words": 16,
    "llm_batch_size": 16,
    "llm_tier": "economy",
    # Pre-ranking uses standard first (H1-B); analysis stays economy via llm_tier.
    "llm_tier_by_pass": {"pre_ranking": "standard"},
    "prefer_fuse_when_hint_and_uncertain": True,
    "prefer_stay_when_uncertain": True,
    "incomplete_thought_only": True,
    "deterministic_fallback_on_llm_fail": True,
    "passes": ["post_sanitize", "pre_ranking", "junction_heal"],
    "excerpt_max_chars": 180,
    "close_excerpt_max_chars": 480,
    # Safety caps — large chronological gaps stay independent unless island-straddle.
    "max_seam_gap_ms": 8000,
    "same_topic_score_floor": 0.15,
    # Soft caps for non-incomplete editorial fuses (same-speaker run collapse).
    "max_fused_duration_ms": 25000,
    "max_fused_members": 3,
    "allow_high_value_bridge": False,
    "uncertain_confidence_floor": 0.55,
}


def is_pre_ranking_pass(pass_id: str) -> bool:
    blob = str(pass_id or "").strip()
    return blob == "pre_ranking" or blob.startswith("pre_ranking")


def connector_fuse_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolved ``analysis.connector_fuse`` block."""
    resolved = cfg if cfg is not None else merged_config()
    analysis = resolved.get("analysis") if isinstance(resolved.get("analysis"), dict) else {}
    block = analysis.get("connector_fuse") if isinstance(analysis.get("connector_fuse"), dict) else {}
    return {**_DEFAULTS, **block}


def connector_fuse_cfg_for_pass(
    pass_id: str, cfg: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Pass-aware overrides (pre_ranking tier + prefer-fuse shrink)."""
    conf = dict(connector_fuse_cfg(cfg))
    if not is_pre_ranking_pass(pass_id):
        return conf
    by_pass = conf.get("llm_tier_by_pass") if isinstance(conf.get("llm_tier_by_pass"), dict) else {}
    for key in ("pre_ranking", pass_id):
        tier = str(by_pass.get(key) or "").strip()
        if tier:
            conf["llm_tier"] = tier
            break
    else:
        conf["llm_tier"] = "standard"
    # H2-A: never prefer-fuse on uncertain clean seams for pre_ranking.
    conf["prefer_fuse_when_hint_and_uncertain"] = False
    return conf


def enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(connector_fuse_cfg(cfg).get("enabled", True))


def ensure_connector_fuse_enabled_for_full_auto(ctx: RunContext) -> bool:
    """H6-C: full-auto / production parity forces fuse on; return effective enabled."""
    conf = connector_fuse_cfg()
    if conf.get("enabled", True):
        return True
    try:
        from interview_mux.automation_run import is_full_auto_run

        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        if not isinstance(meta, dict):
            meta = {}
        production = bool(
            meta.get("production") or meta.get("full_auto_production_parity")
        )
        if not (is_full_auto_run(meta) or production):
            return False
        ctx.log(
            "full-auto forces analysis.connector_fuse.enabled=true (publishability)",
            level="info",
            stage="connector_fuse_pass",
            action_id="connector_fuse.full_auto_force_enabled",
        )
        return True
    except Exception:
        return False


def incomplete_thought_hints(hints: dict[str, Any] | None) -> bool:
    """True when the seam is a broken sentence, not a finished same-speaker beat."""
    if not isinstance(hints, dict):
        return False
    if hints.get("hanging_setup_end") or hints.get("island_straddle"):
        return True
    if hints.get("later_opens_backchannel_completion") and not hints.get(
        "earlier_lands_complete_idea"
    ):
        return True
    return bool(
        (hints.get("later_opens_continuer") or hints.get("later_opens_nominal_complement"))
        and not hints.get("earlier_lands_complete_idea")
    )


def coerce_one_neighbor_fuse_side(
    fuse_side: str,
    *,
    prev_id: str | None,
    next_id: str | None,
    by_id: dict[str, Any],
    allow_bridge: bool = False,
) -> str:
    """Map bridge / invalid sides onto a single neighbor (left or right)."""
    side = str(fuse_side or "").strip().casefold()
    if allow_bridge and side == "bridge" and prev_id and next_id:
        return "bridge"
    if side == "left" and prev_id:
        return "left"
    if side == "right" and next_id:
        return "right"

    neighbors = [n for n in (prev_id, next_id) if n and n in by_id]
    if not neighbors:
        return "left"
    richer = max(neighbors, key=lambda sid: _segment_richness(by_id[sid]))
    if (
        prev_id
        and next_id
        and prev_id in by_id
        and next_id in by_id
        and abs(_segment_richness(by_id[prev_id]) - _segment_richness(by_id[next_id])) < 1e-6
    ):
        richer = prev_id
    if richer == next_id:
        return "right"
    return "left"


def _editorial_fuse_allowed(
    verdict: dict[str, Any],
    *,
    conf: dict[str, Any],
) -> tuple[bool, str]:
    """Whether a fuse verdict may rewrite segments (incomplete / forced only)."""
    forced = str(verdict.get("forced_by") or "")
    if forced in {
        "island_straddle",
        "high_value_speech_island",
        "diarization_yes_same",
        "micro_other_absorb",
    }:
        return True, ""
    hints = verdict.get("deterministic_hints") or {}
    if incomplete_thought_hints(hints):
        return True, ""
    if not conf.get("incomplete_thought_only", True):
        return True, ""
    return False, "complete_thought_stay"


def _ms(row: dict[str, Any], key: str) -> int:
    try:
        return int(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _word_text(w: dict[str, Any]) -> str:
    return str(w.get("text") or w.get("word") or "").strip()


def _conf(w: dict[str, Any]) -> float | None:
    value = w.get("confidence")
    if value is None:
        value = w.get("conf")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_words(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("transcript/full.json"):
        return []
    try:
        transcript = ctx.read_json("transcript/full.json")
    except Exception:
        return []
    rows = (transcript.get("words") or []) if isinstance(transcript, dict) else []
    words = [
        w
        for w in rows
        if isinstance(w, dict) and _word_text(w)
    ]
    words.sort(key=lambda w: (_ms(w, "start_ms"), _ms(w, "end_ms")))
    return words


def _load_segments(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return []
    try:
        manifest = ctx.read_json("segments/manifest.json")
    except Exception:
        return []
    segs = [
        s
        for s in ((manifest.get("segments") or []) if isinstance(manifest, dict) else [])
        if isinstance(s, dict) and s.get("segment_id")
    ]
    segs.sort(key=lambda s: (_ms(s, "start_ms"), str(s.get("segment_id"))))
    return segs


def words_in_span(words: list[dict[str, Any]], start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    return [w for w in words if _ms(w, "start_ms") < int(end_ms) and _ms(w, "end_ms") > int(start_ms)]


def _speaker_of(seg: dict[str, Any]) -> str:
    return str(seg.get("speaker_id") or seg.get("speaker") or "") or "spk_unknown"


def _word_row(w: dict[str, Any]) -> dict[str, Any]:
    return {
        "text": _word_text(w),
        "start_ms": _ms(w, "start_ms"),
        "end_ms": _ms(w, "end_ms"),
        "confidence": _conf(w),
    }


def _text_tail(text: str, n_words: int) -> str:
    parts = str(text or "").split()
    return " ".join(parts[-n_words:]) if parts else ""


def _text_head(text: str, n_words: int) -> str:
    parts = str(text or "").split()
    return " ".join(parts[:n_words]) if parts else ""


def _seam_hash(pair_id: str, combined_seam_text: str) -> str:
    payload = f"{pair_id}::{combined_seam_text}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:16]


def _topic_overlap_score(earlier: dict[str, Any], later: dict[str, Any]) -> float:
    """Cheap bag-of-tags overlap in [0,1]; 0 when either side lacks topics."""
    a = {str(t).casefold() for t in (earlier.get("topic_tags") or []) if t}
    b = {str(t).casefold() for t in (later.get("topic_tags") or []) if t}
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def _island_hints(
    islands: list[dict[str, Any]],
    *,
    earlier_end_ms: int,
    later_start_ms: int,
) -> tuple[bool, bool]:
    """(island_straddle, loose_cluster_on_seam) for the cut between two segments."""
    straddle = False
    loose = False
    lo = min(earlier_end_ms, later_start_ms)
    hi = max(earlier_end_ms, later_start_ms)
    for isl in islands:
        if not isinstance(isl, dict) or isl.get("failure_mode") == "noise":
            continue
        s, e = _ms(isl, "start_ms"), _ms(isl, "end_ms")
        if s <= lo and e >= hi:
            straddle = True
        elif e > lo - 400 and s < hi + 400:
            # Adjacent to the cut counts as a seam risk, not a straddle.
            loose = loose or str(isl.get("cluster_kind")) in ("loose", "window")
        if straddle and str(isl.get("cluster_kind")) in ("loose", "window"):
            loose = True
    return straddle, loose


def enumerate_seam_packets(ctx: RunContext, *, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a packet for EVERY chronological adjacent pair; writes the packets artifact."""
    conf = connector_fuse_cfg(cfg)
    tail_n = int(conf.get("tail_words") or 16)
    head_n = int(conf.get("head_words") or 16)
    excerpt_max = int(conf.get("excerpt_max_chars") or 180)
    close_max = int(conf.get("close_excerpt_max_chars") or 480)

    segments = _load_segments(ctx)
    words = _load_words(ctx)
    islands: list[dict[str, Any]] = []
    try:
        from interview_mux.low_conf_islands import load_islands

        islands = [i for i in (load_islands(ctx).get("islands") or []) if isinstance(i, dict)]
    except Exception:
        islands = []

    packets: list[dict[str, Any]] = []
    for earlier, later in zip(segments, segments[1:]):
        a_id = str(earlier["segment_id"])
        b_id = str(later["segment_id"])
        a_start, a_end = _ms(earlier, "start_ms"), _ms(earlier, "end_ms")
        b_start, b_end = _ms(later, "start_ms"), _ms(later, "end_ms")

        a_words = words_in_span(words, a_start, a_end)[-tail_n:] if words else []
        b_words = words_in_span(words, b_start, b_end)[:head_n] if words else []
        tail_text = (
            " ".join(_word_text(w) for w in a_words)
            if a_words
            else _text_tail(str(earlier.get("text") or ""), tail_n)
        )
        head_text = (
            " ".join(_word_text(w) for w in b_words)
            if b_words
            else _text_head(str(later.get("text") or ""), head_n)
        )
        combined = f"{tail_text} | {head_text}".strip()

        hanging = ends_hanging_setup(tail_text)
        continues = bool(words) and clause_continues_after(words, a_end)
        later_continuer = opens_with_clause_continuer(head_text) or opens_with_clause_continuer(
            str(later.get("text") or "")
        )
        later_nominal = later_opens_nominal_complement(head_text) or later_opens_nominal_complement(
            str(later.get("text") or "")
        )
        later_backchannel = opens_with_backchannel_completion(head_text) or (
            opens_with_backchannel_completion(str(later.get("text") or ""))
        )
        straddle, loose_on_seam = _island_hints(
            islands, earlier_end_ms=a_end, later_start_ms=b_start
        )
        same_speaker = _speaker_of(earlier) == _speaker_of(later)
        gap_ms = max(0, b_start - a_end)
        earlier_full = str(earlier.get("text") or "")
        earlier_close = last_spoken_sentence(earlier_full) or earlier_full[-close_max:]
        if len(earlier_close) < min(80, close_max) and earlier_full:
            earlier_close = earlier_full[-close_max:]
        hanging = hanging or ends_hanging_setup(earlier_close) or ends_hanging_setup(earlier_full)
        lands_complete = bool(
            ends_complete_thought(earlier_full or tail_text, next_pause_ms=gap_ms)
            and not hanging
        )
        topic_score = _topic_overlap_score(earlier, later)
        pair_id = f"{a_id}__{b_id}"
        hints = {
            "hanging_setup_end": bool(hanging),
            "clause_continues_after": bool(continues),
            "later_opens_continuer": bool(later_continuer),
            "later_opens_nominal_complement": bool(later_nominal and hanging),
            "later_opens_backchannel_completion": bool(
                later_backchannel and gap_ms <= CROSS_SPEAKER_COMPLETION_GAP_MS
            ),
            "earlier_lands_complete_idea": lands_complete,
            "island_straddle": bool(straddle),
            "loose_cluster_on_seam": bool(loose_on_seam),
            "gap_over_cap": bool(
                gap_ms > int(conf.get("max_seam_gap_ms") or 8000) and not straddle
            ),
            "same_topic_below_floor": bool(
                topic_score < float(conf.get("same_topic_score_floor") or 0.15)
                and topic_score > 0
            ),
        }
        hint_fired = incomplete_thought_hints(hints)
        packets.append(
            {
                "pair_id": pair_id,
                "earlier_segment_id": a_id,
                "later_segment_id": b_id,
                "earlier_tail_words": [_word_row(w) for w in a_words],
                "later_head_words": [_word_row(w) for w in b_words],
                "combined_seam_text": combined,
                "earlier_end_excerpt": earlier_full[-excerpt_max:],
                "earlier_close_text": earlier_close[-close_max:],
                "later_start_excerpt": str(later.get("text") or "")[:excerpt_max],
                "earlier_start_ms": a_start,
                "earlier_end_ms": a_end,
                "later_start_ms": b_start,
                "later_end_ms": b_end,
                "source_gap_ms": gap_ms,
                "same_speaker": same_speaker,
                "topic_overlap_score": topic_score,
                "earlier_speaker_id": _speaker_of(earlier),
                "later_speaker_id": _speaker_of(later),
                "deterministic_hints": hints,
                "priority": "high" if hint_fired else "normal",
                "seam_hash": _seam_hash(pair_id, combined),
            }
        )

    doc = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "segment_count": len(segments),
        "pair_count": len(packets),
        "tail_words": tail_n,
        "head_words": head_n,
        "packets": packets,
    }
    ctx.write_json(SEAM_PACKETS_PATH, doc)
    return doc


def deterministic_fallback_verdict(packet: dict[str, Any]) -> dict[str, Any]:
    """Per-pair verdict when the LLM cannot answer: incomplete-thought only."""
    hints = packet.get("deterministic_hints") or {}
    if incomplete_thought_hints(hints):
        hanging = bool(hints.get("hanging_setup_end"))
        straddle = bool(hints.get("island_straddle"))
        cross = not packet.get("same_speaker")
        if straddle and not hanging:
            reason = "island_straddle"
        elif cross:
            reason = "cross_speaker_completion"
        else:
            reason = "mid_sentence_continue"
        rationale = "Deterministic fallback: " + ", ".join(
            [
                label
                for label, fired in (
                    ("hanging setup", hanging),
                    ("later opens continuer", bool(hints.get("later_opens_continuer"))),
                    (
                        "later opens backchannel completion",
                        bool(hints.get("later_opens_backchannel_completion")),
                    ),
                    ("island straddles the cut", straddle),
                    ("cross-speaker completion", cross),
                )
                if fired
            ]
        )
        return {
            "pair_id": packet.get("pair_id"),
            "decision": "fuse",
            "fuse_direction": "into_earlier",
            "reason_code": reason,
            "rationale": rationale,
            "confidence": 0.5,
            "adjudication_fallback": "deterministic",
        }
    return {
        "pair_id": packet.get("pair_id"),
        "decision": "stay_independent",
        "fuse_direction": None,
        "reason_code": "complete_thought_stay"
        if hints.get("earlier_lands_complete_idea")
        else "clean_turn",
        "rationale": "Deterministic fallback: earlier segment lands on a complete idea.",
        "confidence": 0.5,
        "adjudication_fallback": "deterministic",
    }


def _cross_speaker_verdict(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "pair_id": packet.get("pair_id"),
        "decision": "stay_independent",
        "fuse_direction": None,
        "reason_code": "speaker_change",
        "rationale": "Cross-speaker seam — fuse disabled by allow_cross_speaker_fuse=false.",
        "confidence": 1.0,
        "adjudication_fallback": "cross_speaker_short_circuit",
    }


def _gap_cap_verdict(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "pair_id": packet.get("pair_id"),
        "decision": "stay_independent",
        "fuse_direction": None,
        "reason_code": "topic_shift",
        "rationale": "Seam gap exceeds max_seam_gap_ms without an island straddle.",
        "confidence": 1.0,
        "adjudication_fallback": "seam_gap_cap",
    }


def _slim_packet_for_llm(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "pair_id": packet.get("pair_id"),
        "combined_seam_text": packet.get("combined_seam_text"),
        "earlier_close_text": packet.get("earlier_close_text"),
        "earlier_end_excerpt": packet.get("earlier_end_excerpt"),
        "later_start_excerpt": packet.get("later_start_excerpt"),
        "source_gap_ms": packet.get("source_gap_ms"),
        "same_speaker": packet.get("same_speaker"),
        "deterministic_hints": packet.get("deterministic_hints") or {},
    }


def _llm_adjudicate_batch(
    ctx: RunContext,
    batch: list[dict[str, Any]],
    *,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]] | None:
    """One economy-tier structured call for a batch; ``None`` when unavailable."""
    if not batch:
        return []
    conf = connector_fuse_cfg(cfg)
    try:
        from interview_mux.homunculus.budget import (
            LimitExhausted,
            identity_exhausted,
            mark_identity_exhausted,
        )
        from interview_mux.stages.llm_runner import load_system_prompt, run_prompt_envelope
    except Exception:
        return None
    if identity_exhausted(ctx, SEAM_STAGE_KEY):
        return None

    system: str
    try:
        system = load_system_prompt(SEAM_PROMPT_REL, include_preamble=False)
    except Exception:
        system = _FALLBACK_SYSTEM_PROMPT

    payload = {
        "task": (
            "Decide fuse vs stay_independent for each chronological seam. "
            "Fuse only unfinished thoughts. Return one verdict per pair_id."
        ),
        "policy": {
            "incomplete_thought_only": bool(conf.get("incomplete_thought_only", True)),
            "prefer_stay_when_uncertain": bool(conf.get("prefer_stay_when_uncertain", True)),
            "prefer_fuse_when_hint_and_uncertain": bool(
                conf.get("prefer_fuse_when_hint_and_uncertain", True)
            ),
            "never_invent_words": True,
            "same_speaker_complete_stay": True,
        },
        "pairs": [_slim_packet_for_llm(p) for p in batch],
    }
    user = json.dumps(payload, indent=2, ensure_ascii=False)
    tiers = [str(conf.get("llm_tier") or "economy"), "standard", "flagship"]
    seen: set[str] = set()
    ladder = [t for t in tiers if not (t in seen or seen.add(t))]
    last_exc: Exception | None = None
    envelope: dict[str, Any] | None = None
    work = list(batch)
    for bump, tier in enumerate(ladder):
        try:
            envelope = run_prompt_envelope(
                SEAM_STAGE_KEY,
                SEAM_PROMPT_REL,
                user,
                ctx=ctx,
                include_preamble=False,
                task_kind="advisory",
                explicit_tier=tier,
                bump_tier=bool(bump),
                response_format={"type": "json_object"},
                system_override=system,
            )
            last_exc = None
            break
        except LimitExhausted as exc:
            mark_identity_exhausted(ctx, SEAM_STAGE_KEY)
            last_exc = exc
            envelope = None
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            err = str(exc).lower()
            if "context_length" in err and len(work) > 1:
                work = work[: max(1, len(work) // 2)]
                payload["pairs"] = [_slim_packet_for_llm(p) for p in work]
                user = json.dumps(payload, indent=2, ensure_ascii=False)
                continue
            continue
    else:
        envelope = None
    if envelope is None:
        ctx.log(
            f"Seam adjudication LLM unavailable for {len(batch)} pair(s): {last_exc}",
            level="warning",
            stage=SEAM_STAGE_KEY,
            action_id="connector_fuse.llm.fallback",
            detail={"error": str(last_exc)[:300] if last_exc else "", "pairs": len(batch)},
        )
        return None

    artifacts = envelope.get("artifacts") if isinstance(envelope, dict) else None
    rows = (artifacts or {}).get("verdicts") if isinstance(artifacts, dict) else None
    if not isinstance(rows, list):
        return None
    by_pair = {str(p.get("pair_id")): p for p in batch}
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("pair_id") or "")
        if pid not in by_pair:
            continue
        decision = str(row.get("decision") or "").strip().lower()
        if decision not in ("fuse", "stay_independent"):
            continue
        out.append(
            {
                "pair_id": pid,
                "decision": decision,
                "fuse_direction": row.get("fuse_direction") or ("into_earlier" if decision == "fuse" else None),
                "reason_code": str(row.get("reason_code") or "other"),
                "rationale": str(row.get("rationale") or "")[:300],
                "confidence": float(row.get("confidence") or 0.0),
                "adjudication_fallback": None,
            }
        )
    return out or None


def adjudicate_seams_llm(
    ctx: RunContext,
    packets: list[dict[str, Any]],
    *,
    batch_size: int = 16,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Economy LLM verdict per pair, batched; deterministic fallback fills every gap."""
    conf = connector_fuse_cfg(cfg)
    allow_cross = bool(conf.get("allow_cross_speaker_fuse", False))
    size = max(1, int(batch_size or conf.get("llm_batch_size") or 16))

    verdicts: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    try:
        from interview_mux.island_cluster_structure import load_locked_seams

        locked = load_locked_seams(ctx)
    except Exception:
        locked = set()
    for packet in packets:
        if not isinstance(packet, dict):
            continue
        pid = str(packet.get("pair_id") or "")
        if pid and pid in locked:
            verdicts.append(
                {
                    "pair_id": pid,
                    "earlier_segment_id": packet.get("earlier_segment_id"),
                    "later_segment_id": packet.get("later_segment_id"),
                    "decision": "stay_independent",
                    "fuse_direction": None,
                    "reason_code": "locked_seam",
                    "rationale": "Seam locked by high-value island cluster H-edge cuts.",
                    "confidence": 1.0,
                    "forced_by": "locked_seam",
                    "seam_hash": packet.get("seam_hash"),
                    "deterministic_hints": packet.get("deterministic_hints") or {},
                }
            )
            continue
        if not allow_cross and not packet.get("same_speaker"):
            hints = packet.get("deterministic_hints") or {}
            gap_ms = int(packet.get("source_gap_ms") or 0)
            max_gap = int(conf.get("max_seam_gap_ms") or 8000)
            if incomplete_thought_hints(hints) and gap_ms <= max_gap:
                pending.append(packet)
                continue
            verdicts.append(_cross_speaker_verdict(packet))
            continue
        hints = packet.get("deterministic_hints") or {}
        # Large chronological gaps stay independent unless an island straddles the cut.
        if hints.get("gap_over_cap") and not hints.get("island_straddle"):
            verdicts.append(_gap_cap_verdict(packet))
            continue
        pending.append(packet)

    use_fallback = bool(conf.get("deterministic_fallback_on_llm_fail", True))
    for start in range(0, len(pending), size):
        batch = pending[start : start + size]
        rows = _llm_adjudicate_batch(ctx, batch, cfg=conf)
        answered = {str(r.get("pair_id")) for r in (rows or [])}
        if rows:
            verdicts.extend(rows)
        for packet in batch:
            pid = str(packet.get("pair_id"))
            if pid in answered:
                continue
            if not use_fallback and rows is not None:
                continue
            verdicts.append(deterministic_fallback_verdict(packet))

    by_pair = {str(p.get("pair_id")): p for p in packets if isinstance(p, dict)}
    for verdict in verdicts:
        packet = by_pair.get(str(verdict.get("pair_id"))) or {}
        hints = packet.get("deterministic_hints") or verdict.get("deterministic_hints") or {}
        verdict["seam_hash"] = packet.get("seam_hash") or verdict.get("seam_hash")
        verdict["earlier_segment_id"] = packet.get("earlier_segment_id") or verdict.get(
            "earlier_segment_id"
        )
        verdict["later_segment_id"] = packet.get("later_segment_id") or verdict.get(
            "later_segment_id"
        )
        verdict["deterministic_hints"] = hints
    return verdicts


def adjudicate_seams(
    ctx: RunContext,
    packets: list[dict[str, Any]],
    *,
    batch_size: int | None = None,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Public adjudication entry point (LLM first, deterministic fallback second)."""
    conf = connector_fuse_cfg(cfg)
    size = int(batch_size or conf.get("llm_batch_size") or 16)
    verdicts = adjudicate_seams_llm(ctx, packets, batch_size=size, cfg=conf)
    by_pair = {str(p.get("pair_id")): p for p in packets if isinstance(p, dict)}
    uncertain_floor = float(conf.get("uncertain_confidence_floor") or 0.55)
    for verdict in verdicts:
        packet = by_pair.get(str(verdict.get("pair_id"))) or {}
        hints = packet.get("deterministic_hints") or verdict.get("deterministic_hints") or {}
        verdict["deterministic_hints"] = hints
        # Same-speaker complete ideas stay independent. Island-straddle still wins below.
        if str(verdict.get("decision")) == "fuse":
            allowed, refuse_reason = _editorial_fuse_allowed(verdict, conf=conf)
            low_conf = False
            try:
                low_conf = float(verdict.get("confidence") or 0.0) < uncertain_floor
            except (TypeError, ValueError):
                low_conf = False
            if not allowed or (
                conf.get("prefer_stay_when_uncertain", True)
                and low_conf
                and not incomplete_thought_hints(hints)
            ):
                verdict["decision"] = "stay_independent"
                verdict["fuse_direction"] = None
                verdict["reason_code"] = refuse_reason or "complete_thought_stay"
                verdict["rationale"] = (
                    "Complete idea already landed — same-speaker continuation stays independent."
                )
                verdict["forced_by"] = "complete_thought_guard"
        if (
            str(verdict.get("decision")) == "stay_independent"
            and incomplete_thought_hints(hints)
        ):
            gap_ms = int(packet.get("source_gap_ms") or 0)
            max_gap = int(conf.get("max_seam_gap_ms") or 8000)
            if gap_ms <= max_gap:
                forced = deterministic_fallback_verdict(packet)
                verdict["decision"] = "fuse"
                verdict["fuse_direction"] = forced.get("fuse_direction") or "into_earlier"
                verdict["reason_code"] = forced.get("reason_code") or "mid_sentence_continue"
                verdict["rationale"] = (
                    "Forced fuse: incomplete thought / hanging setup at the seam."
                )
                verdict["forced_by"] = "incomplete_thought_hint"
        # Fail-catch: non-noise islands that straddle the cut force fuse even if the
        # LLM preferred stay_independent (recall-first at lexicon seams).
        if (
            str(verdict.get("decision")) == "stay_independent"
            and bool(hints.get("island_straddle"))
            and packet.get("same_speaker", True)
        ):
            verdict["decision"] = "fuse"
            verdict["fuse_direction"] = verdict.get("fuse_direction") or "into_earlier"
            verdict["reason_code"] = "island_straddle"
            verdict["rationale"] = (
                "Forced fuse: non-noise low-conf island straddles the cut."
            )
            verdict["forced_by"] = "island_straddle"
    doc = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pair_count": len(packets),
        "verdict_count": len(verdicts),
        "fuse_count": len([v for v in verdicts if v.get("decision") == "fuse"]),
        "fallback_count": len([v for v in verdicts if v.get("adjudication_fallback")]),
        "verdicts": verdicts,
    }
    ctx.write_json(SEAM_VERDICTS_PATH, doc)
    return verdicts


def _rebuild_text(words: list[dict[str, Any]], start_ms: int, end_ms: int, *, fallback: str) -> str:
    span = words_in_span(words, start_ms, end_ms)
    if span:
        return " ".join(_word_text(w) for w in span).strip()
    return fallback.strip()


def _read_audit(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(FUSE_AUDIT_PATH):
        return {"version": 1, "passes": [], "applied_fuses": [], "stay_independent": []}
    try:
        doc = ctx.read_json(FUSE_AUDIT_PATH)
    except Exception:
        doc = None
    if not isinstance(doc, dict):
        return {"version": 1, "passes": [], "applied_fuses": [], "stay_independent": []}
    doc.setdefault("passes", [])
    doc.setdefault("applied_fuses", [])
    doc.setdefault("stay_independent", [])
    return doc


def apply_connector_fuses(
    ctx: RunContext,
    verdicts: list[dict[str, Any]],
    *,
    max_fuses: int = 24,
    pass_id: str = "",
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rewrite boundaries + manifest so each fused pair becomes one complete thought."""
    conf = connector_fuse_cfg(cfg)
    raw_cap = max_fuses if max_fuses is not None else conf.get("max_fuses_per_pass")
    try:
        cap = int(raw_cap)
    except (TypeError, ValueError):
        cap = _FINITE_DEFAULT_FUSES_PER_PASS
    if cap == 0:
        cap = _FINITE_DEFAULT_FUSES_PER_PASS
    elif cap < 0:
        cap = 10_000_000  # explicit unlimited (-1)
    segments = _load_segments(ctx)
    by_id = {str(s["segment_id"]): dict(s) for s in segments}
    order = [str(s["segment_id"]) for s in segments]
    words = _load_words(ctx)

    fuse_rows = [
        v
        for v in verdicts
        if isinstance(v, dict) and str(v.get("decision")) == "fuse" and v.get("pair_id")
    ]
    # Apply in chronological order so chains (A+B then +C) collapse into one slab.
    position = {sid: i for i, sid in enumerate(order)}
    fuse_rows.sort(key=lambda v: position.get(str(v.get("earlier_segment_id")), 1 << 30))

    representative: dict[str, str] = {sid: sid for sid in order}
    consumed: set[str] = set()
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for verdict in fuse_rows:
        if len(applied) >= cap:
            skipped.append({"pair_id": verdict.get("pair_id"), "reason": "max_fuses_per_pass"})
            continue
        a_id = str(verdict.get("earlier_segment_id") or "")
        b_id = str(verdict.get("later_segment_id") or "")
        if not a_id or not b_id:
            pair = str(verdict.get("pair_id") or "")
            if "__" not in pair:
                continue
            a_id, b_id = pair.split("__", 1)
        target_id = representative.get(a_id, a_id)
        target = by_id.get(target_id)
        later = by_id.get(b_id)
        if target is None or later is None or b_id in consumed or target_id == b_id:
            skipped.append({"pair_id": verdict.get("pair_id"), "reason": "pair_unavailable"})
            continue
        gap_ms = max(0, _ms(later, "start_ms") - _ms(target, "end_ms"))
        max_gap = int(conf.get("max_seam_gap_ms") or 8000)
        hints = verdict.get("deterministic_hints") or {}
        forced = str(verdict.get("forced_by") or "")
        if not bool(conf.get("allow_cross_speaker_fuse", False)) and _speaker_of(target) != _speaker_of(later):
            if not incomplete_thought_hints(hints) and forced not in {
                "diarization_yes_same",
                "micro_other_absorb",
            }:
                skipped.append({"pair_id": verdict.get("pair_id"), "reason": "cross_speaker"})
                continue
        force_bypass = forced in {
            "island_straddle",
            "high_value_speech_island",
            "diarization_yes_same",
            "micro_other_absorb",
        }
        if gap_ms > max_gap and not hints.get("island_straddle") and not force_bypass:
            skipped.append({"pair_id": verdict.get("pair_id"), "reason": "seam_gap_cap"})
            continue
        topic_floor = float(conf.get("same_topic_score_floor") or 0.15)
        topic_score = _topic_overlap_score(target, later)
        # When both sides declare topics and overlap is below floor, refuse fuse
        # unless island-straddle / hanging-setup / high-value forced the merge.
        if (
            topic_score > 0
            and topic_score < topic_floor
            and not incomplete_thought_hints(hints)
            and not force_bypass
        ):
            skipped.append({"pair_id": verdict.get("pair_id"), "reason": "same_topic_floor"})
            continue
        allowed, refuse_reason = _editorial_fuse_allowed(verdict, conf=conf)
        if not allowed:
            skipped.append({"pair_id": verdict.get("pair_id"), "reason": refuse_reason})
            continue

        start_ms = min(_ms(target, "start_ms"), _ms(later, "start_ms"))
        end_ms = max(_ms(target, "end_ms"), _ms(later, "end_ms"))
        fused_from = list(dict.fromkeys([*(target.get("fused_from") or [target_id]), b_id]))
        new_dur = max(0, end_ms - start_ms)
        max_dur = int(conf.get("max_fused_duration_ms") or 0)
        max_members = int(conf.get("max_fused_members") or 0)
        # Incomplete / forced repairs may grow; editorial mid-flow glue may not.
        if not force_bypass and not incomplete_thought_hints(hints):
            if max_dur > 0 and new_dur > max_dur:
                skipped.append({"pair_id": verdict.get("pair_id"), "reason": "fused_duration_cap"})
                continue
            if max_members > 0 and len(fused_from) > max_members:
                skipped.append({"pair_id": verdict.get("pair_id"), "reason": "fused_member_cap"})
                continue

        joined_text = " ".join(
            t for t in (str(target.get("text") or ""), str(later.get("text") or "")) if t
        )
        target["start_ms"] = start_ms
        target["end_ms"] = end_ms
        target["duration_ms"] = new_dur
        target["text"] = _rebuild_text(words, start_ms, end_ms, fallback=joined_text)
        target["fused_from"] = fused_from
        target["fuse_reason"] = str(verdict.get("reason_code") or "mid_sentence_continue")
        target["fuse_pass_id"] = pass_id or None
        topics = [
            *(target.get("topic_tags") or []),
            *(later.get("topic_tags") or []),
        ]
        if topics:
            target["topic_tags"] = list(dict.fromkeys(str(t) for t in topics))
        if (
            str(later.get("retention") or "") == "must_keep"
            or str(target.get("retention") or "") == "must_keep"
            or forced == "high_value_speech_island"
            or later.get("high_value_speech")
            or target.get("high_value_speech")
        ):
            target["retention"] = "must_keep"
        if forced == "high_value_speech_island" or later.get("high_value_speech") or target.get(
            "high_value_speech"
        ):
            target["high_value_speech"] = True

        by_id[target_id] = target
        consumed.add(b_id)
        representative[b_id] = target_id
        for sid, rep in list(representative.items()):
            if rep == b_id:
                representative[sid] = target_id
        applied.append(
            {
                "pair_id": verdict.get("pair_id"),
                "fused_into": target_id,
                "absorbed_segment_id": b_id,
                "fused_from": fused_from,
                "reason_code": target["fuse_reason"],
                "rationale": str(verdict.get("rationale") or "")[:300],
                "confidence": verdict.get("confidence"),
                "adjudication_fallback": verdict.get("adjudication_fallback"),
                "start_ms": start_ms,
                "end_ms": end_ms,
                "pass_id": pass_id or None,
            }
        )

    id_remap = {sid: rep for sid, rep in representative.items() if sid != rep}
    result: dict[str, Any] = {
        "version": 1,
        "pass_id": pass_id or None,
        "applied": len(applied),
        "applied_fuses": applied,
        "skipped": skipped,
        "id_remap": id_remap,
        "stay_independent": [
            {
                "pair_id": v.get("pair_id"),
                "seam_hash": v.get("seam_hash"),
                "reason_code": v.get("reason_code"),
                "rationale": str(v.get("rationale") or "")[:300],
                "adjudication_fallback": v.get("adjudication_fallback"),
            }
            for v in verdicts
            if isinstance(v, dict) and str(v.get("decision")) == "stay_independent"
        ],
    }

    if applied:
        surviving = [by_id[sid] for sid in order if sid not in consumed and sid in by_id]
        surviving.sort(key=lambda s: _ms(s, "start_ms"))
        _write_manifest(ctx, surviving, pass_id=pass_id)
        _write_boundaries(ctx, surviving, consumed=consumed, pass_id=pass_id)

    _append_audit(ctx, result, verdicts=verdicts, pass_id=pass_id)
    if applied:
        _remap_downstream_ids(ctx, result.get("id_remap") or {}, pass_id=pass_id)
        ctx.log(
            f"Connector fuse ({pass_id or 'pass'}): merged {len(applied)} seam(s) into "
            f"{len({row['fused_into'] for row in applied})} segment(s)",
            level="info",
            stage="connector_fuse_pass",
            action_id="connector_fuse.applied",
            detail={"applied": [row["pair_id"] for row in applied][:20], "pass_id": pass_id},
        )
    return result


def _rewrite_id_list(ids: list[Any], remap: dict[str, str]) -> list[str]:
    return remap_fused_ids(ids, remap)


def _remap_downstream_ids(
    ctx: RunContext, remap: dict[str, str], *, pass_id: str = ""
) -> None:
    """Rewrite every known ``seg_*`` consumer onto surviving fused ids."""
    if not remap:
        return
    from interview_mux.diarization_suspicion import stamp_fused_segment_ids
    from interview_mux.segment_id_remap import apply_full_segment_id_remap

    apply_full_segment_id_remap(
        ctx, remap, stage_key=fuse_writer_stage(pass_id), skip_handoff=True
    )
    stamp_fused_segment_ids(ctx, remap)


def rerun_air_bounds_on_fused(
    ctx: RunContext, *, fused_ids: list[str] | None = None, pass_id: str = ""
) -> dict[str, Any]:
    """Re-run keeper air-bound trims on fused slabs (legal hinge snap)."""
    audit = _read_audit(ctx)
    ids = list(fused_ids or [])
    if not ids:
        ids = sorted(
            {
                str(row.get("fused_into"))
                for row in (audit.get("applied_fuses") or [])
                if isinstance(row, dict) and row.get("fused_into")
            }
        )
    if not ids or not ctx.artifact_exists("segments/manifest.json"):
        return {"trimmed": 0, "segment_ids": []}
    try:
        from interview_mux.ideal_cuts import resolve_keeper_air_bounds
    except Exception:
        return {"trimmed": 0, "segment_ids": [], "skip_reason": "air_bounds_unavailable"}

    try:
        manifest = ctx.read_json("segments/manifest.json")
    except Exception:
        return {"trimmed": 0, "segment_ids": [], "skip_reason": "manifest_unreadable"}
    if not isinstance(manifest, dict):
        return {"trimmed": 0, "segment_ids": []}
    words = _load_words(ctx)
    cuts_doc = None
    if ctx.artifact_exists("understanding/ideal_cuts.json"):
        try:
            cuts_doc = ctx.read_json("understanding/ideal_cuts.json")
        except Exception:
            cuts_doc = None
    changed = 0
    for seg in manifest.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        sid = str(seg.get("segment_id") or "")
        if sid not in ids:
            continue
        meta: dict[str, Any] = {}
        try:
            wav_path = None
            try:
                wav_path = ctx.read_path("ingest", "normalized.wav")
            except Exception:
                wav_path = None
            start_ms, end_ms = resolve_keeper_air_bounds(
                source_start_ms=int(seg.get("start_ms") or 0),
                source_end_ms=int(seg.get("end_ms") or 0),
                cuts_doc=cuts_doc if isinstance(cuts_doc, dict) else None,
                words=words,
                segment_id=sid,
                meta_out=meta,
                wav_path=wav_path,
            )
        except Exception:
            continue
        if int(start_ms) != int(seg.get("start_ms") or 0) or int(end_ms) != int(seg.get("end_ms") or 0):
            seg["start_ms"] = int(start_ms)
            seg["end_ms"] = int(end_ms)
            seg["duration_ms"] = max(0, int(end_ms) - int(start_ms))
            if meta:
                seg["air_bound_meta"] = meta
            changed += 1
    if changed:
        writer = fuse_writer_stage(pass_id)
        ctx.write_json("segments/manifest.json", manifest, stage_key=writer)
        try:
            from interview_mux.asset_transcripts import sync_speech_sidecars

            sync_speech_sidecars(ctx)
        except Exception as exc:
            ctx.log(
                f"speech sidecar sync after air-bound trim skipped: {exc}",
                level="warning",
                stage=writer,
            )
        _write_boundaries(
            ctx,
            [s for s in (manifest.get("segments") or []) if isinstance(s, dict)],
            consumed=set(),
            pass_id=pass_id or "air_bounds_after_fuse",
        )
    return {"trimmed": changed, "segment_ids": ids}


def _write_manifest(
    ctx: RunContext, segments: list[dict[str, Any]], *, pass_id: str = ""
) -> None:
    manifest = ctx.read_json("segments/manifest.json") if ctx.artifact_exists("segments/manifest.json") else {}
    out = dict(manifest) if isinstance(manifest, dict) else {}
    out["segments"] = segments
    writer = fuse_writer_stage(pass_id)
    ctx.write_json("segments/manifest.json", out, stage_key=writer)
    try:
        from interview_mux.asset_transcripts import sync_speech_sidecars

        sync_speech_sidecars(ctx)
    except Exception as exc:
        ctx.log(
            f"speech sidecar sync after fuse skipped: {exc}",
            level="warning",
            stage=writer,
        )


def _write_boundaries(
    ctx: RunContext,
    segments: list[dict[str, Any]],
    *,
    consumed: set[str],
    pass_id: str,
) -> None:
    if not ctx.artifact_exists("segments/boundaries.json"):
        return
    try:
        doc = ctx.read_json("segments/boundaries.json")
    except Exception:
        return
    if not isinstance(doc, dict):
        return
    times = {str(s["segment_id"]): s for s in segments if s.get("segment_id")}
    rows: list[dict[str, Any]] = []
    for row in doc.get("boundaries") or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("segment_id") or "")
        if sid in consumed:
            continue
        merged = dict(row)
        seg = times.get(sid)
        if seg is not None:
            merged["start_ms"] = _ms(seg, "start_ms")
            merged["end_ms"] = _ms(seg, "end_ms")
            if seg.get("fused_from"):
                merged["fused_from"] = list(seg["fused_from"])
                merged["fuse_pass_id"] = pass_id or None
        rows.append(merged)
    rows.sort(key=lambda r: _ms(r, "start_ms"))
    out = dict(doc)
    out["boundaries"] = rows
    try:
        from interview_mux.stage_coupling import publish_boundary_contract

        out = publish_boundary_contract(out, publisher_stage=fuse_writer_stage(pass_id))
    except Exception:
        pass
    from interview_mux.shared_path_commit import commit_boundaries_doc

    fuse_stage = fuse_writer_stage(pass_id)
    commit_boundaries_doc(
        ctx,
        out,
        stage_key=fuse_stage,
        claim_producer=True,
    )


def _append_audit(
    ctx: RunContext,
    result: dict[str, Any],
    *,
    verdicts: list[dict[str, Any]],
    pass_id: str,
) -> None:
    audit = _read_audit(ctx)
    audit["passes"] = [
        *audit.get("passes", []),
        {
            "pass_id": pass_id or None,
            "at": datetime.now(timezone.utc).isoformat(),
            "verdict_count": len(verdicts),
            "applied": result.get("applied"),
            "skipped": len(result.get("skipped") or []),
            **(
                {"skip_reason": result.get("skip_reason")}
                if result.get("skip_reason")
                else {}
            ),
        },
    ][-40:]
    audit["applied_fuses"] = [*audit.get("applied_fuses", []), *(result.get("applied_fuses") or [])]
    audit["stay_independent"] = [
        *audit.get("stay_independent", []),
        *[{**row, "pass_id": pass_id or None} for row in (result.get("stay_independent") or [])],
    ][-500:]
    remap = dict(audit.get("id_remap") or {})
    for old, new in (result.get("id_remap") or {}).items():
        remap[old] = new
    # Collapse chains so a twice-fused id resolves in one hop.
    for old in list(remap):
        seen = {old}
        target = remap[old]
        while target in remap and target not in seen:
            seen.add(target)
            target = remap[target]
        remap[old] = target
    audit["id_remap"] = remap
    audit["version"] = 1
    ctx.write_json(
        FUSE_AUDIT_PATH,
        audit,
        stage_key=fuse_writer_stage(pass_id),
    )


def fused_id_remap(ctx: RunContext) -> dict[str, str]:
    """Absorbed segment_id → surviving fused segment_id (chains collapsed)."""
    audit = _read_audit(ctx)
    remap = audit.get("id_remap")
    return {str(k): str(v) for k, v in remap.items()} if isinstance(remap, dict) else {}


def remap_fused_ids(ids: list[Any], remap: dict[str, str]) -> list[str]:
    """Rewrite segment id references onto surviving fused ids (order-preserving dedupe)."""
    out: list[str] = []
    for raw in ids or []:
        sid = str(raw)
        seen = {sid}
        while sid in remap and remap[sid] not in seen:
            sid = remap[sid]
            seen.add(sid)
        if sid and sid not in out:
            out.append(sid)
    return out


def _segment_richness(seg: dict[str, Any]) -> float:
    dur = max(0, _ms(seg, "end_ms") - _ms(seg, "start_ms"))
    topics = len(seg.get("topic_tags") or [])
    text_n = len(str(seg.get("text") or "").split())
    return float(dur) + 500.0 * topics + 50.0 * text_n


def plan_high_value_fuses(
    ctx: RunContext,
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build forced fuse verdicts so high-value islands never stay standalone keepers.

    Prefer :func:`run_high_value_cluster_fuse_rounds` for production. This remains
    for simple / single-island deterministic planning and tests.
    """
    conf = connector_fuse_cfg(cfg)
    topic_floor = float(conf.get("same_topic_score_floor") or 0.15)
    try:
        from interview_mux.high_value_speech_islands import load_high_value_islands

        hv = load_high_value_islands(ctx)
    except Exception:
        return {"verdicts": [], "interior_segment_ids": [], "applied_plans": 0}

    islands = [i for i in (hv.get("islands") or []) if isinstance(i, dict)]
    if not islands:
        return {"verdicts": [], "interior_segment_ids": [], "applied_plans": 0}

    segments = _load_segments(ctx)
    if len(segments) < 1:
        return {"verdicts": [], "interior_segment_ids": [], "applied_plans": 0}

    verdicts: list[dict[str, Any]] = []
    interior: list[str] = []
    plans: list[dict[str, Any]] = []
    for island in islands:
        cluster = {
            "cluster_id": f"legacy_{island.get('island_id')}",
            "density": "simple",
            "member_island_ids": [island.get("island_id")],
            "islands": [island],
            "start_ms": _ms(island, "start_ms"),
            "end_ms": _ms(island, "end_ms"),
            "segment_ids_touched": list(island.get("segment_ids_touched") or []),
        }
        planned = plan_cluster_fuses(
            ctx, cluster, structure=None, cfg=conf, topic_floor=topic_floor
        )
        verdicts.extend(planned.get("verdicts") or [])
        interior.extend(planned.get("interior_segment_ids") or [])
        plans.extend(planned.get("plans") or [])

    if interior:
        try:
            from interview_mux.high_value_speech_islands import mark_segments_high_value

            mark_segments_high_value(ctx, set(interior))
        except Exception:
            pass

    return {
        "verdicts": verdicts,
        "interior_segment_ids": list(dict.fromkeys(interior)),
        "applied_plans": len(plans),
        "plans": plans,
    }


def plan_cluster_fuses(
    ctx: RunContext,
    cluster: dict[str, Any],
    *,
    structure: dict[str, Any] | None = None,
    cfg: dict[str, Any] | None = None,
    topic_floor: float | None = None,
) -> dict[str, Any]:
    """Plan forced fuse verdicts for one cluster using structure + H-edge cuts."""
    conf = connector_fuse_cfg(cfg)
    allow_bridge = bool(conf.get("allow_high_value_bridge", False))
    floor = float(
        topic_floor
        if topic_floor is not None
        else (conf.get("same_topic_score_floor") or 0.15)
    )
    segments = _load_segments(ctx)
    by_id = {str(s["segment_id"]): s for s in segments}
    order = [str(s["segment_id"]) for s in segments]
    index_of = {sid: i for i, sid in enumerate(order)}

    islands = [i for i in (cluster.get("islands") or []) if isinstance(i, dict)]
    if not islands:
        return {"verdicts": [], "interior_segment_ids": [], "plans": [], "locked_pair_ids": []}

    assign_by = {
        str(a.get("island_id")): a
        for a in ((structure or {}).get("assignments") or [])
        if isinstance(a, dict) and a.get("island_id")
    }
    topic_unity = str((structure or {}).get("topic_unity") or "same_conversation")
    hinge_attach = (structure or {}).get("hinge_attach")

    try:
        from interview_mux.island_cluster_structure import high_conf_flank_cuts
    except Exception:
        high_conf_flank_cuts = None  # type: ignore[assignment]

    verdicts: list[dict[str, Any]] = []
    interior: list[str] = []
    plans: list[dict[str, Any]] = []
    locked: list[str] = []
    stay_pairs: list[str] = []

    if len(islands) == 1 and not assign_by:
        island = islands[0]
        i0, i1 = _ms(island, "start_ms"), _ms(island, "end_ms")
        touched = [
            sid
            for sid in (island.get("segment_ids_touched") or cluster.get("segment_ids_touched") or [])
            if sid in by_id
        ]
        if not touched:
            touched = [
                sid
                for sid, seg in by_id.items()
                if not (_ms(seg, "end_ms") <= i0 or _ms(seg, "start_ms") >= i1)
            ]
            touched.sort(key=lambda sid: index_of.get(sid, 1 << 30))
        if len(touched) == 1:
            sid = touched[0]
            seg = by_id[sid]
            seg_dur = max(0, _ms(seg, "end_ms") - _ms(seg, "start_ms"))
            island_dur = max(0, i1 - i0)
            fully_inside = _ms(seg, "start_ms") <= i0 and _ms(seg, "end_ms") >= i1
            if fully_inside and seg_dur >= max(island_dur * 2, island_dur + 2500):
                interior.append(sid)
                plans.append(
                    {
                        "island_id": island.get("island_id"),
                        "mode": "interior",
                        "segment_id": sid,
                        "cluster_id": cluster.get("cluster_id"),
                    }
                )
                return {
                    "verdicts": [],
                    "interior_segment_ids": interior,
                    "plans": plans,
                    "locked_pair_ids": [],
                }

    for island in islands:
        i0, i1 = _ms(island, "start_ms"), _ms(island, "end_ms")
        iid = str(island.get("island_id") or "")
        assign = assign_by.get(iid) or {}
        fuse_side = str(assign.get("fuse_side") or "").casefold()
        touched = [
            sid
            for sid in (island.get("segment_ids_touched") or [])
            if sid in by_id
        ]
        if not touched:
            touched = [
                sid
                for sid, seg in by_id.items()
                if not (_ms(seg, "end_ms") <= i0 or _ms(seg, "start_ms") >= i1)
            ]
            touched.sort(key=lambda sid: index_of.get(sid, 1 << 30))
        if not touched:
            continue
        first_i = min(index_of[s] for s in touched if s in index_of)
        last_i = max(index_of[s] for s in touched if s in index_of)
        prev_id = order[first_i - 1] if first_i > 0 else None
        next_id = order[last_i + 1] if last_i + 1 < len(order) else None
        if fuse_side not in {"left", "right", "bridge"}:
            fuse_side = coerce_one_neighbor_fuse_side(
                "",
                prev_id=prev_id,
                next_id=next_id,
                by_id=by_id,
                allow_bridge=False,
            )
            if (
                allow_bridge
                and topic_unity == "same_conversation"
                and prev_id
                and next_id
                and _topic_overlap_score(by_id[prev_id], by_id[next_id]) >= floor
            ):
                fuse_side = "bridge"
        fuse_side = coerce_one_neighbor_fuse_side(
            fuse_side,
            prev_id=prev_id,
            next_id=next_id,
            by_id=by_id,
            allow_bridge=allow_bridge,
        )

        if high_conf_flank_cuts is not None:
            cuts = high_conf_flank_cuts(
                ctx, island_start_ms=i0, island_end_ms=i1, fuse_side=fuse_side
            )
        else:
            cuts = {
                "absorb_start_ms": i0,
                "absorb_end_ms": i1,
                "cut_ms": i0 if fuse_side != "right" else i1,
            }

        absorb0 = int(cuts.get("absorb_start_ms") or i0)
        absorb1 = int(cuts.get("absorb_end_ms") or i1)

        core_ids = [
            sid
            for sid, seg in by_id.items()
            if not (_ms(seg, "end_ms") <= absorb0 or _ms(seg, "start_ms") >= absorb1)
        ]
        core_ids.sort(key=lambda sid: index_of.get(sid, 1 << 30))
        if not core_ids:
            continue

        first_i = min(index_of[s] for s in core_ids if s in index_of)
        last_i = max(index_of[s] for s in core_ids if s in index_of)
        prev_id = order[first_i - 1] if first_i > 0 else None
        next_id = order[last_i + 1] if last_i + 1 < len(order) else None
        core_ids = order[first_i : last_i + 1]

        mode = "richer_neighbor"
        if fuse_side == "bridge" and prev_id and next_id:
            chain = [prev_id, *core_ids, next_id]
            mode = "bridge"
        elif fuse_side == "left" and prev_id:
            chain = [prev_id, *core_ids]
            mode = "richer_neighbor" if not assign else "left"
        elif fuse_side == "right" and next_id:
            chain = [*core_ids, next_id]
            mode = "richer_neighbor" if not assign else "right"
        else:
            chain = list(core_ids)
            if prev_id:
                chain = [prev_id, *core_ids]
                mode = "richer_neighbor"
            elif next_id:
                chain = [*core_ids, next_id]
                mode = "richer_neighbor"

        unique_chain = list(dict.fromkeys(chain))
        for a, b in zip(unique_chain, unique_chain[1:]):
            if a not in by_id or b not in by_id:
                continue
            if index_of.get(a, -1) > index_of.get(b, -1):
                a, b = b, a
            if topic_unity == "split_topics" and hinge_attach in {"left", "right"}:
                hinge_sids = set(str(x) for x in (cluster.get("hinge_segment_ids") or []) if x)
                if hinge_sids and (
                    (a in hinge_sids and hinge_attach == "right" and b not in hinge_sids)
                    or (b in hinge_sids and hinge_attach == "left" and a not in hinge_sids)
                ):
                    stay_pairs.append(f"{a}__{b}")
                    continue
            pair_id = f"{a}__{b}"
            verdicts.append(
                {
                    "pair_id": pair_id,
                    "earlier_segment_id": a,
                    "later_segment_id": b,
                    "decision": "fuse",
                    "fuse_direction": "into_earlier",
                    "reason_code": (
                        "high_value_speech_bridge"
                        if mode == "bridge"
                        else "high_value_speech_neighbor"
                    ),
                    "rationale": (
                        str(assign.get("rationale") or "")
                        or "High-value low-conf/STT-skip speech must stay with narrative neighbors."
                    )[:300],
                    "confidence": 1.0,
                    "forced_by": "high_value_speech_island",
                    "cut_source": "high_conf_flank",
                    "deterministic_hints": {
                        "high_value_speech_island": True,
                        "island_id": iid,
                        "cluster_id": cluster.get("cluster_id"),
                        "fuse_mode": mode,
                        "fuse_side": fuse_side,
                        "h_edge_absorb_start_ms": absorb0,
                        "h_edge_absorb_end_ms": absorb1,
                    },
                }
            )
            locked.append(pair_id)
        plans.append(
            {
                "island_id": iid,
                "mode": mode,
                "fuse_side": fuse_side,
                "chain": unique_chain,
                "cluster_id": cluster.get("cluster_id"),
                "h_edge": cuts,
            }
        )

    for pair_id in stay_pairs:
        if "__" not in pair_id:
            continue
        a, b = pair_id.split("__", 1)
        verdicts.append(
            {
                "pair_id": pair_id,
                "earlier_segment_id": a,
                "later_segment_id": b,
                "decision": "stay_independent",
                "fuse_direction": None,
                "reason_code": "topic_shift",
                "rationale": "Hinge high-conf segment kept independent across topic/subtopic change.",
                "confidence": 1.0,
                "forced_by": "island_cluster_hinge",
                "cut_source": "high_conf_flank",
            }
        )
        locked.append(pair_id)

    return {
        "verdicts": verdicts,
        "interior_segment_ids": list(dict.fromkeys(interior)),
        "plans": plans,
        "locked_pair_ids": list(dict.fromkeys(locked)),
    }


def run_high_value_cluster_fuse_rounds(
    ctx: RunContext,
    *,
    pass_id: str,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Group HV islands → per-cluster structure → H-edge cuts → apply until fixed point."""
    try:
        from interview_mux.high_value_speech_islands import (
            cluster_is_fuse_eligible,
            group_high_value_island_clusters,
            high_value_speech_cfg,
            mark_segments_high_value,
            refresh_cluster_segment_touches,
        )
    except Exception as exc:
        return {"skip_reason": f"hv_import:{exc}", "total_applied": 0, "rounds": []}

    hv_conf = high_value_speech_cfg(cfg)
    if not hv_conf.get("per_cluster_fuse", True):
        plan = plan_high_value_fuses(ctx, cfg=cfg)
        applied = 0
        if plan.get("verdicts"):
            result = apply_connector_fuses(
                ctx,
                list(plan["verdicts"]),
                max_fuses=0,
                pass_id=f"{pass_id}:high_value",
                cfg=cfg,
            )
            applied = int(result.get("applied") or 0)
        return {
            "mode": "legacy_batch",
            "total_applied": applied,
            "rounds": [],
            "plans": plan.get("plans") or [],
        }

    max_rounds = int(hv_conf.get("max_island_cluster_rounds") or 32)
    try:
        from interview_mux.island_cluster_structure import (
            adjudicate_island_cluster_structure,
            lock_seams,
            structure_cfg,
        )
    except Exception:
        adjudicate_island_cluster_structure = None  # type: ignore[assignment]
        lock_seams = None  # type: ignore[assignment]

        def structure_cfg(_c=None):  # type: ignore[misc]
            return {"lock_forced_seams": True}

    s_cfg = structure_cfg(cfg)
    lock_forced = bool(s_cfg.get("lock_forced_seams", True))

    rounds: list[dict[str, Any]] = []
    total_applied = 0
    last_sig = ""

    for round_index in range(max_rounds):
        grouped = group_high_value_island_clusters(
            ctx, cfg=cfg, write=True, pass_id=pass_id
        )
        segments = _load_segments(ctx)
        pending: list[dict[str, Any]] = []
        for raw in grouped.get("clusters") or []:
            if not isinstance(raw, dict):
                continue
            cluster = refresh_cluster_segment_touches(raw, segments)
            if cluster_is_fuse_eligible(cluster, segments):
                pending.append(cluster)
        if not pending:
            rounds.append(
                {
                    "round": round_index,
                    "pending": 0,
                    "applied": 0,
                    "reason": "no_fuse_eligible_clusters",
                }
            )
            break

        round_applied = 0
        covered_spans: list[tuple[int, int]] = []
        round_plans: list[dict[str, Any]] = []
        for cluster in pending:
            c0, c1 = _ms(cluster, "start_ms"), _ms(cluster, "end_ms")
            if any(not (c1 <= a or c0 >= b) for a, b in covered_spans):
                continue
            segments = _load_segments(ctx)
            cluster = refresh_cluster_segment_touches(cluster, segments)
            if not cluster_is_fuse_eligible(cluster, segments):
                if cluster.get("segment_ids_touched"):
                    try:
                        mark_segments_high_value(ctx, set(cluster["segment_ids_touched"]))
                    except Exception:
                        pass
                continue

            structure = None
            if adjudicate_island_cluster_structure:
                structure = adjudicate_island_cluster_structure(ctx, cluster, cfg=cfg)

            planned = plan_cluster_fuses(ctx, cluster, structure=structure, cfg=cfg)
            if planned.get("interior_segment_ids"):
                try:
                    mark_segments_high_value(ctx, set(planned["interior_segment_ids"]))
                except Exception:
                    pass
            fuse_verdicts = [
                v
                for v in (planned.get("verdicts") or [])
                if str(v.get("decision")) == "fuse"
            ]
            applied_n = 0
            if fuse_verdicts:
                result = apply_connector_fuses(
                    ctx,
                    list(planned["verdicts"]),
                    max_fuses=0,
                    pass_id=f"{pass_id}:hv_cluster:{cluster.get('cluster_id')}",
                    cfg=cfg,
                )
                applied_n = int(result.get("applied") or 0)
                round_applied += applied_n
                total_applied += applied_n
            if lock_forced and lock_seams and planned.get("locked_pair_ids"):
                lock_seams(
                    ctx,
                    list(planned["locked_pair_ids"]),
                    pass_id=f"{pass_id}:{cluster.get('cluster_id')}",
                )
            covered_spans.append((c0, c1))
            round_plans.extend(planned.get("plans") or [])

        sig = "|".join(
            sorted(
                f"{p.get('cluster_id')}:{p.get('island_id')}:{p.get('mode')}"
                for p in round_plans
            )
        )
        rounds.append(
            {
                "round": round_index,
                "pending": len(pending),
                "applied": round_applied,
                "plans": len(round_plans),
            }
        )
        if round_applied == 0:
            break
        if sig and sig == last_sig:
            rounds[-1]["oscillation_halt"] = True
            try:
                from interview_mux.delivery_guardrails import record_delivery_residual

                record_delivery_residual(
                    ctx,
                    kind="fuse_oscillation",
                    severity="critical",
                    stage=fuse_writer_stage(pass_id),
                    detail={
                        "pass_id": pass_id,
                        "sig": sig[:200],
                        "round": round_index,
                        "mode": "per_cluster",
                    },
                )
            except Exception:
                pass
            break
        last_sig = sig

    return {
        "mode": "per_cluster",
        "total_applied": total_applied,
        "rounds": rounds,
        "fixed_point": bool(rounds) and int(rounds[-1].get("applied") or 0) == 0,
    }


def already_adjudicated(audit: dict[str, Any]) -> dict[str, str]:
    """pair_id → seam_hash for pairs recorded as stay_independent in prior passes."""
    out: dict[str, str] = {}
    for row in audit.get("stay_independent") or []:
        if isinstance(row, dict) and row.get("pair_id"):
            out[str(row["pair_id"])] = str(row.get("seam_hash") or "")
    return out


def _prior_stay_decision(audit: dict[str, Any], pair_id: str) -> str:
    for row in audit.get("stay_independent") or []:
        if isinstance(row, dict) and str(row.get("pair_id") or "") == pair_id:
            return str(row.get("decision") or row.get("reason_code") or "stay_independent")
    return "stay_independent"


def _seam_chapter_membership_changed(ctx: RunContext, packet: dict[str, Any]) -> bool:
    """True when narrative chapters place endpoints in different chapters (H3 reopen)."""
    try:
        from interview_mux.high_value_speech_islands import _narrative_chapter_change

        return bool(
            _narrative_chapter_change(
                ctx,
                left_end_ms=int(packet.get("earlier_end_ms") or 0),
                right_start_ms=int(packet.get("later_start_ms") or 0),
                left_segment_id=str(packet.get("earlier_segment_id") or "") or None,
                right_segment_id=str(packet.get("later_segment_id") or "") or None,
            )
        )
    except Exception:
        return False


def select_pending_seam_packets(
    ctx: RunContext,
    packets: list[dict[str, Any]],
    *,
    pass_id: str,
    force_readjudicate: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Return (pending, reopened_seams, settled_skipped).

    Pre-ranking settles prior stay_independent unless seam_hash or narrative
    chapter membership changed (G3 / H3-A/D).
    """
    if force_readjudicate or not packets:
        return list(packets), [], 0
    audit = _read_audit(ctx)
    settled = already_adjudicated(audit)
    pending: list[dict[str, Any]] = []
    reopened: list[dict[str, Any]] = []
    skipped = 0
    pre = is_pre_ranking_pass(pass_id)
    for packet in packets:
        if not isinstance(packet, dict):
            continue
        pid = str(packet.get("pair_id") or "")
        seam_hash = str(packet.get("seam_hash") or "")
        prior_hash = settled.get(pid)
        if prior_hash is None:
            pending.append(packet)
            continue
        if prior_hash != seam_hash:
            pending.append(packet)
            if pre:
                reopened.append(
                    {
                        "pair_id": pid,
                        "reason": "seam_hash_changed",
                        "prior_decision": _prior_stay_decision(audit, pid),
                    }
                )
            continue
        if pre and _seam_chapter_membership_changed(ctx, packet):
            pending.append(packet)
            reopened.append(
                {
                    "pair_id": pid,
                    "reason": "chapter_membership_changed",
                    "prior_decision": _prior_stay_decision(audit, pid),
                }
            )
            continue
        skipped += 1
    return pending, reopened, skipped


def _empty_adjudication_stats() -> dict[str, Any]:
    return {
        "llm_ok": 0,
        "llm_fail": 0,
        "fallback_fuse": 0,
        "fallback_stay": 0,
        "fuse_applied": 0,
        "stay": 0,
        "mean_confidence": None,
    }


def _rollup_adjudication_stats(
    verdicts: list[dict[str, Any]], *, applied: int = 0
) -> dict[str, Any]:
    stats = _empty_adjudication_stats()
    confs: list[float] = []
    for v in verdicts:
        if not isinstance(v, dict):
            continue
        fb = str(v.get("adjudication_fallback") or "")
        decision = str(v.get("decision") or "")
        if fb:
            stats["llm_fail"] += 1
            if decision == "fuse":
                stats["fallback_fuse"] += 1
            else:
                stats["fallback_stay"] += 1
        else:
            stats["llm_ok"] += 1
        if decision == "stay_independent":
            stats["stay"] += 1
        try:
            confs.append(float(v.get("confidence")))
        except (TypeError, ValueError):
            pass
    stats["fuse_applied"] = int(applied)
    if confs:
        stats["mean_confidence"] = round(sum(confs) / len(confs), 4)
    return stats


def resolve_fuse_round_caps(conf: dict[str, Any] | None = None) -> tuple[int, int]:
    """Map config 0 → finite defaults; negative → explicit unlimited (CFP-B3 / DEEP-FUSE-01).

    Returns ``(max_rounds, max_fuses_per_pass)``.
    """
    cfg = conf if isinstance(conf, dict) else connector_fuse_cfg()
    try:
        raw_rounds = int(cfg.get("max_fuse_rounds") or 0)
    except (TypeError, ValueError):
        raw_rounds = 0
    if raw_rounds == 0:
        max_rounds = _FINITE_DEFAULT_FUSE_ROUNDS
    elif raw_rounds < 0:
        max_rounds = 10_000
    else:
        max_rounds = raw_rounds
    try:
        cap = int(cfg.get("max_fuses_per_pass") or 0)
    except (TypeError, ValueError):
        cap = _FINITE_DEFAULT_FUSES_PER_PASS
    if cap == 0:
        cap = _FINITE_DEFAULT_FUSES_PER_PASS
    elif cap < 0:
        cap = 10_000_000
    return max_rounds, cap


def run_connector_fuse_pass(
    ctx: RunContext,
    *,
    pass_id: str,
    cfg: dict[str, Any] | None = None,
    force_readjudicate: bool = False,
) -> dict[str, Any]:
    """Enumerate → adjudicate → apply until fixed point (analysis may prepend HV/diar)."""
    conf = connector_fuse_cfg_for_pass(pass_id, cfg)
    writer = fuse_writer_stage(pass_id)
    pre = is_pre_ranking_pass(pass_id)
    rounds_rel = fuse_rounds_path(pass_id)
    rounds_doc: dict[str, Any] = {
        "version": 1,
        "pass_id": pass_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rounds": [],
        "total_applied": 0,
        "fixed_point": False,
        "reopened_seams": [],
        "settled_skipped": 0,
        "adjudication_stats": _empty_adjudication_stats(),
    }
    effective_enabled = bool(conf.get("enabled", True))
    if not effective_enabled:
        if ensure_connector_fuse_enabled_for_full_auto(ctx):
            conf = {**conf, "enabled": True}
            effective_enabled = True
        else:
            skip = persist_fuse_skip(
                ctx, pass_id=pass_id, skip_reason="disabled", rounds_doc=rounds_doc
            )
            skip["adjudication_stats"] = _empty_adjudication_stats()
            return skip
    if not ctx.artifact_exists("segments/manifest.json"):
        return persist_fuse_skip(
            ctx, pass_id=pass_id, skip_reason="missing_manifest", rounds_doc=rounds_doc
        )

    # S2: HV cluster + diarization forced fuse stay analysis-only.
    max_rounds, cap = resolve_fuse_round_caps(conf)
    hv_applied = 0
    diar_applied = 0
    if pre:
        rounds_doc["high_value_cluster_fuse"] = {
            "skipped": "pre_ranking_peel",
            "total_applied": 0,
        }
        rounds_doc["diarization_forced_fuse"] = {
            "skipped": "pre_ranking_peel",
            "pairs": 0,
            "applied": 0,
        }
    else:
        hv_rounds = run_high_value_cluster_fuse_rounds(ctx, pass_id=pass_id, cfg=conf)
        hv_applied = int(hv_rounds.get("total_applied") or 0)
        rounds_doc["high_value_cluster_fuse"] = hv_rounds

        from interview_mux.diarization_suspicion import forced_diarization_fuse_verdicts

        diar_verdicts = forced_diarization_fuse_verdicts(ctx)
        if diar_verdicts:
            diar_result = apply_connector_fuses(
                ctx, diar_verdicts, max_fuses=cap, pass_id=pass_id, cfg=conf
            )
            diar_applied = int(diar_result.get("applied") or 0)
            rounds_doc["diarization_forced_fuse"] = {
                "pairs": len(diar_verdicts),
                "applied": diar_applied,
            }

    batch_size = int(conf.get("llm_batch_size") or 16)
    total_applied = hv_applied + diar_applied
    last_sig = ""
    all_verdicts: list[dict[str, Any]] = []
    all_reopened: list[dict[str, Any]] = []
    settled_skipped_total = 0

    for round_index in range(max_rounds):
        packets_doc = enumerate_seam_packets(ctx, cfg=conf)
        packets = [p for p in (packets_doc.get("packets") or []) if isinstance(p, dict)]
        if not packets:
            rounds_doc["fixed_point"] = True
            break

        pending, reopened, skipped = select_pending_seam_packets(
            ctx,
            packets,
            pass_id=pass_id,
            force_readjudicate=force_readjudicate,
        )
        settled_skipped_total += skipped
        if reopened:
            all_reopened.extend(reopened)
        if not pending:
            rounds_doc["fixed_point"] = True
            rounds_doc["rounds"].append(
                {
                    "round": round_index,
                    "pairs": len(packets),
                    "adjudicated": 0,
                    "applied": 0,
                    "reason": "all_pairs_settled",
                    "settled_skipped": skipped,
                }
            )
            break

        remaining = max(0, cap - total_applied)
        verdicts = adjudicate_seams(ctx, pending, batch_size=batch_size, cfg=conf)
        all_verdicts.extend(verdicts)
        result = apply_connector_fuses(
            ctx, verdicts, max_fuses=remaining, pass_id=pass_id, cfg=conf
        )
        applied = int(result.get("applied") or 0)
        total_applied += applied
        sig = "|".join(
            sorted(str(v.get("pair_id") or "") for v in verdicts if v.get("decision") == "fuse")
        )
        rounds_doc["rounds"].append(
            {
                "round": round_index,
                "pairs": len(packets),
                "adjudicated": len(pending),
                "applied": applied,
                "fuse_verdicts": len([v for v in verdicts if v.get("decision") == "fuse"]),
                "fallback_verdicts": len([v for v in verdicts if v.get("adjudication_fallback")]),
                "settled_skipped": skipped,
                "reopened": len(reopened),
            }
        )
        if applied == 0:
            rounds_doc["fixed_point"] = True
            break
        if sig and sig == last_sig:
            rounds_doc["oscillation_halt"] = True
            rounds_doc["fixed_point"] = False
            try:
                from interview_mux.delivery_guardrails import record_delivery_residual

                record_delivery_residual(
                    ctx,
                    kind="fuse_oscillation",
                    severity="critical",
                    stage=writer,
                    detail={
                        "pass_id": pass_id,
                        "sig": sig[:200],
                        "round": round_index,
                        "mode": "connector_fuse",
                    },
                )
            except Exception:
                pass
            break
        last_sig = sig
        if total_applied >= cap:
            rounds_doc["fixed_point"] = False
            break

    rounds_doc["total_applied"] = total_applied
    rounds_doc["reopened_seams"] = all_reopened[:100]
    rounds_doc["settled_skipped"] = settled_skipped_total
    rounds_doc["adjudication_stats"] = _rollup_adjudication_stats(
        all_verdicts, applied=total_applied
    )
    # S3: air bounds / encompass / split-island QC stay analysis-only.
    if not pre:
        if total_applied:
            air = rerun_air_bounds_on_fused(ctx, pass_id=pass_id)
            rounds_doc["air_bounds"] = air
        encompass = encompass_straddling_islands(ctx, pass_id=pass_id, cfg=conf)
        rounds_doc["encompassed"] = encompass.get("applied") or 0
        split_qc = assert_no_split_suspect_islands(ctx)
        rounds_doc["split_island_qc"] = split_qc
    else:
        rounds_doc["air_bounds"] = {"skipped": "pre_ranking_peel"}
        rounds_doc["encompassed"] = 0
        rounds_doc["split_island_qc"] = {"skipped": "pre_ranking_peel"}
    ctx.write_json(rounds_rel, rounds_doc)
    if (
        fuse_writer_stage(pass_id) == "connector_fuse_pass"
        and not ctx.artifact_exists(FUSE_AUDIT_PATH)
    ):
        persist_fuse_skip(
            ctx,
            pass_id=pass_id,
            skip_reason=str(rounds_doc.get("skip_reason") or "empty_packets"),
            rounds_doc=rounds_doc,
        )
    ctx.log(
        f"Connector fuse pass '{pass_id}': {total_applied} fuse(s) over "
        f"{len(rounds_doc['rounds'])} round(s) (fixed_point={rounds_doc['fixed_point']})",
        level="info",
        stage=writer,
        action_id="connector_fuse.pass",
        detail={
            "pass_id": pass_id,
            "total_applied": total_applied,
            "hv_cluster_applied": hv_applied,
            "fixed_point": rounds_doc["fixed_point"],
            "settled_skipped": settled_skipped_total,
            "reopened": len(all_reopened),
            "rounds_path": rounds_rel,
        },
    )
    return rounds_doc


def encompass_straddling_islands(
    ctx: RunContext,
    *,
    pass_id: str = "",
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Grow the earlier segment to cover non-noise islands still split across a cut."""
    conf = connector_fuse_cfg(cfg)
    segments = _load_segments(ctx)
    if len(segments) < 2:
        return {"applied": 0}
    islands: list[dict[str, Any]] = []
    try:
        from interview_mux.low_conf_islands import load_islands

        islands = [
            i
            for i in (load_islands(ctx).get("islands") or [])
            if isinstance(i, dict) and i.get("failure_mode") != "noise"
        ]
    except Exception:
        return {"applied": 0}
    if not islands:
        return {"applied": 0}

    words = _load_words(ctx)
    by_id = {str(s["segment_id"]): dict(s) for s in segments}
    order = [str(s["segment_id"]) for s in segments]
    applied: list[dict[str, Any]] = []
    consumed: set[str] = set()

    for earlier_id, later_id in zip(order, order[1:]):
        if earlier_id in consumed or later_id in consumed:
            continue
        earlier, later = by_id.get(earlier_id), by_id.get(later_id)
        if earlier is None or later is None:
            continue
        if not bool(conf.get("allow_cross_speaker_fuse", False)) and _speaker_of(earlier) != _speaker_of(
            later
        ):
            continue
        a_end, b_start = _ms(earlier, "end_ms"), _ms(later, "start_ms")
        straddle, _ = _island_hints(islands, earlier_end_ms=a_end, later_start_ms=b_start)
        if not straddle:
            continue
        # Prefer fuse rewrite into earlier when island still straddles.
        start_ms = min(_ms(earlier, "start_ms"), _ms(later, "start_ms"))
        end_ms = max(_ms(earlier, "end_ms"), _ms(later, "end_ms"))
        joined = " ".join(
            t for t in (str(earlier.get("text") or ""), str(later.get("text") or "")) if t
        )
        earlier["start_ms"] = start_ms
        earlier["end_ms"] = end_ms
        earlier["duration_ms"] = max(0, end_ms - start_ms)
        earlier["text"] = _rebuild_text(words, start_ms, end_ms, fallback=joined)
        earlier["fused_from"] = list(
            dict.fromkeys([*(earlier.get("fused_from") or [earlier_id]), later_id])
        )
        earlier["fuse_reason"] = "island_encompass"
        earlier["fuse_pass_id"] = pass_id or None
        by_id[earlier_id] = earlier
        consumed.add(later_id)
        applied.append(
            {
                "pair_id": f"{earlier_id}__{later_id}",
                "fused_into": earlier_id,
                "absorbed_segment_id": later_id,
                "reason_code": "island_encompass",
                "pass_id": pass_id or None,
            }
        )

    if not applied:
        return {"applied": 0, "applied_fuses": []}
    surviving = [by_id[sid] for sid in order if sid not in consumed and sid in by_id]
    surviving.sort(key=lambda s: _ms(s, "start_ms"))
    _write_manifest(ctx, surviving, pass_id=pass_id)
    _write_boundaries(ctx, surviving, consumed=consumed, pass_id=pass_id or "island_encompass")
    remap = {row["absorbed_segment_id"]: row["fused_into"] for row in applied}
    _remap_downstream_ids(ctx, remap, pass_id=pass_id)
    result = {
        "applied": len(applied),
        "applied_fuses": applied,
        "id_remap": remap,
        "stay_independent": [],
        "skipped": [],
        "pass_id": pass_id or None,
    }
    _append_audit(ctx, result, verdicts=[], pass_id=pass_id or "island_encompass")
    return result


def assert_no_split_suspect_islands(ctx: RunContext) -> dict[str, Any]:
    """QC: non-noise islands must not remain split across two surviving segment edges."""
    segments = _load_segments(ctx)
    try:
        from interview_mux.low_conf_islands import load_islands

        islands = [
            i
            for i in (load_islands(ctx).get("islands") or [])
            if isinstance(i, dict) and i.get("failure_mode") != "noise" and not i.get("soft")
        ]
    except Exception:
        return {"ok": True, "split_islands": []}
    splits: list[dict[str, Any]] = []
    for isl in islands:
        s, e = _ms(isl, "start_ms"), _ms(isl, "end_ms")
        hits = [
            str(seg.get("segment_id"))
            for seg in segments
            if _ms(seg, "end_ms") > s and _ms(seg, "start_ms") < e
        ]
        if len(hits) >= 2:
            splits.append(
                {
                    "island_id": isl.get("island_id"),
                    "segment_ids": hits,
                    "start_ms": s,
                    "end_ms": e,
                }
            )
    doc = {
        "version": 1,
        "ok": not splits,
        "split_islands": splits,
    }
    ctx.write_json("analysis/connector_fuse_split_island_qc.json", doc)
    return doc


def analyze_connector_fuses(ctx: RunContext, *, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Public analyze entry: enumerate packets + adjudicate without applying."""
    packets_doc = enumerate_seam_packets(ctx, cfg=cfg)
    packets = [p for p in (packets_doc.get("packets") or []) if isinstance(p, dict)]
    verdicts = adjudicate_seams(ctx, packets, cfg=cfg)
    return {
        "version": 1,
        "packets": packets_doc,
        "verdicts": verdicts,
        "pair_count": len(packets),
        "fuse_count": len([v for v in verdicts if v.get("decision") == "fuse"]),
    }


__all__ = [
    "FUSE_AUDIT_PATH",
    "FUSE_ROUNDS_PATH",
    "FUSE_ROUNDS_PRE_RANKING_PATH",
    "SEAM_PACKETS_PATH",
    "SEAM_VERDICTS_PATH",
    "adjudicate_seams",
    "adjudicate_seams_llm",
    "analyze_connector_fuses",
    "already_adjudicated",
    "apply_connector_fuses",
    "assert_no_split_suspect_islands",
    "connector_fuse_cfg",
    "connector_fuse_cfg_for_pass",
    "deterministic_fallback_verdict",
    "enabled",
    "encompass_straddling_islands",
    "ensure_connector_fuse_enabled_for_full_auto",
    "enumerate_seam_packets",
    "fuse_rounds_path",
    "fuse_writer_stage",
    "fused_id_remap",
    "is_pre_ranking_pass",
    "persist_fuse_skip",
    "plan_cluster_fuses",
    "plan_high_value_fuses",
    "remap_fused_ids",
    "resolve_fuse_round_caps",
    "rerun_air_bounds_on_fused",
    "run_connector_fuse_pass",
    "run_high_value_cluster_fuse_rounds",
    "select_pending_seam_packets",
    "words_in_span",
]
