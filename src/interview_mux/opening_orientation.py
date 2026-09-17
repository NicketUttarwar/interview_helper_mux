"""Early episode orientation — minted only when the native open does not already intro."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.run_context import RunContext


ORIENTATION_LINE_ID = "vo_preface_episode_orientation"
OPENING_MUSIC_AIR_KIND = "opening_music"
SEQUENCE_COLD_OPEN = "native_hook_music_intro_body"
SEQUENCE_STRAIGHT = "intro_music_body"
SEQUENCE_NATIVE_OPEN = "music_body"

_NATIVE_INTRO_RE = re.compile(
    r"\b(?:"
    r"welcome(?:\s+to|\s+back)?|"
    r"joining\s+(?:us|me)|"
    r"(?:with\s+us|our\s+guest)|"
    r"today\s+(?:we|i)\s+(?:talk|speak|sit|have)|"
    r"introduce|"
    r"on\s+the\s+(?:show|podcast|episode)|"
    r"we(?:['’]ve| have)\s+got|"
    r"who\s+is|"
    r"sit(?:ting)?\s+down\s+with|"
    r"talk(?:ing)?\s+(?:with|to)|"
    r"conversation\s+with"
    r")\b",
    flags=re.IGNORECASE,
)


def is_episode_orientation(line: dict[str, Any] | None) -> bool:
    if not isinstance(line, dict):
        return False
    line_id = str(line.get("line_id") or "").lower()
    category = str(line.get("line_category") or "").lower()
    return (
        bool(line.get("episode_orientation"))
        or bool(line.get("opening_sequence"))
        or "episode_orientation" in line_id
        or category in {"episode_preface", "episode_orientation"}
        or bool(line.get("cold_open"))
    )


def native_cold_open_segment_id(
    ctx: RunContext, ordered_segment_ids: list[str]
) -> str | None:
    """Return the explicit native hook only when it actually opens the selection."""
    if not ordered_segment_ids:
        return None
    first = str(ordered_segment_ids[0])
    selection = (
        ctx.read_json("master/selection.json")
        if ctx.artifact_exists("master/selection.json")
        else {}
    )
    candidates = [
        (selection or {}).get("native_cold_open_segment_id"),
        (selection or {}).get("hook_segment_id"),
    ]
    if ctx.artifact_exists("mastering/mastering_plan.json"):
        plan = ctx.read_json("mastering/mastering_plan.json")
        cold = plan.get("cold_open") if isinstance(plan, dict) else {}
        if isinstance(cold, dict) and str(cold.get("kind") or "none") != "none":
            candidates.extend([cold.get("segment_id"), cold.get("hook_segment_id")])
    if ctx.artifact_exists("understanding/episode_structure.json"):
        structure = ctx.read_json("understanding/episode_structure.json")
        if isinstance(structure, dict):
            candidates.append(structure.get("hook_segment_id"))
            cold = structure.get("cold_open")
            if isinstance(cold, dict):
                candidates.append(cold.get("segment_id"))
    return first if first in {str(x) for x in candidates if x} else None


def _first_text(value: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = str(value.get(key) or "").strip()
        if text:
            return " ".join(text.split())
    return ""


def _topic_label(brief: dict[str, Any]) -> str:
    topics = brief.get("topics")
    if not isinstance(topics, list):
        return ""
    for topic in topics:
        if isinstance(topic, dict):
            text = _first_text(topic, "name", "label", "title", "summary")
        else:
            text = str(topic or "").strip()
        if text:
            return text
    return ""


def _load_nugget_claims(ctx: RunContext, nugget_ids: list[str]) -> tuple[list[str], list[str]]:
    """Return (ids present in corpus, spoken claim sentences)."""
    if not nugget_ids:
        return [], []
    try:
        from interview_mux.nugget_layup import CORPUS_REL, _nugget_claim_text
    except ImportError:
        return [], []
    if not ctx.artifact_exists(CORPUS_REL):
        return [], []
    corpus = ctx.read_json(CORPUS_REL)
    if not isinstance(corpus, dict):
        return [], []
    nug_by_id = {
        str(n.get("nugget_id") or ""): n
        for n in (corpus.get("nuggets") or [])
        if isinstance(n, dict) and n.get("nugget_id")
    }
    ids: list[str] = []
    bits: list[str] = []
    for raw in nugget_ids:
        nid = str(raw or "").strip()
        if not nid or nid not in nug_by_id:
            continue
        claim = _nugget_claim_text(nug_by_id[nid]).rstrip(".")
        if not claim:
            continue
        ids.append(nid)
        bits.append(claim + ".")
        if len(bits) >= 2:
            break
    return ids, bits


def embed_orientation_nugget_recovery(
    ctx: RunContext,
    line: dict[str, Any],
    nugget_ids: list[str],
    *,
    max_nuggets: int = 2,
) -> tuple[dict[str, Any], list[str]]:
    """Buried high-salience excluded facts into the first synthetic orientation VO."""
    out = dict(line)
    notes: list[str] = []
    ids, bits = _load_nugget_claims(ctx, [str(x) for x in nugget_ids if x][:max_nuggets])
    if not ids or not bits:
        return out, notes
    core = " ".join(str(out.get("text") or "").split()).strip()
    insert = " ".join(bits)
    low = core.lower()
    if "let's hear" in low or "lets hear" in low:
        m = re.search(r"(?i)\b(let['’]?s hear\b.*)$", core)
        if m:
            prefix = core[: m.start()].rstrip(" ,;:")
            cue = m.group(1).strip()
            if prefix:
                out["text"] = f"{prefix.rstrip('.')}. {insert} {cue}".strip()
            else:
                out["text"] = f"{insert} {cue}".strip()
        else:
            out["text"] = f"{core.rstrip('.')}. {insert} Let's hear how it unfolds.".strip()
    elif core:
        out["text"] = f"{core.rstrip('.')}. {insert} Let's hear how it unfolds.".strip()
    else:
        out["text"] = f"{insert} Let's hear how it unfolds.".strip()
    merged_ids = list(
        dict.fromkeys([*(str(x) for x in (out.get("nugget_ids") or []) if x), *ids])
    )
    out["nugget_ids"] = merged_ids
    out["selected_nugget_ids"] = merged_ids
    out["recovered_open_high_salience"] = True
    out["orientation_nugget_recovery"] = True
    out["rationale"] = str(
        out.get("rationale") or "Episode orientation with recovered excluded-tape context."
    ).strip()
    notes.append("orientation_embed:" + ",".join(ids))
    return out, notes


def _fallback_orientation_text(ctx: RunContext) -> tuple[str, dict[str, Any]]:
    """Build grounded copy only from already-approved understanding artifacts."""
    brief = (
        ctx.read_json("understanding/content_brief.json")
        if ctx.artifact_exists("understanding/content_brief.json")
        else {}
    )
    brief = brief if isinstance(brief, dict) else {}
    thesis = _first_text(brief, "episode_promise", "logline", "thesis", "subtitle")
    guest = _first_text(brief, "guest_name", "interviewee_name", "subject_name")
    topic = _topic_label(brief) or _first_text(brief, "title")

    if thesis:
        core = thesis
        if not re.match(r"(?i)^(this|in this|today|we|our)\b", core):
            core = f"In this conversation, {core[0].lower() + core[1:]}"
    elif guest and topic:
        core = f"This is a conversation with {guest} about {topic}."
    elif topic:
        core = f"This conversation explores {topic}."
    elif guest:
        core = f"This is a conversation with {guest}."
    else:
        core = "This conversation follows the people, decisions, and stakes on the tape."

    if core[-1:] not in ".!?":
        core += "."
    # Never rewrite "stage" → "chapter" (chapter language is banned on air).
    # Prefer a listener-clear synonym when brief thesis uses "stage" as jargon.
    core = re.sub(r"\bstage\b", "phase", core, flags=re.IGNORECASE)
    text = f"{core} Let’s hear how it unfolded."
    words = text.split()
    if len(words) > 105:
        text = " ".join(words[:102]).rstrip(" ,;:") + ". Let’s hear how it unfolded."
    return text, {
        "artifact": "understanding/content_brief.json",
        "path": "episode_promise|logline|thesis|guest_name|topics",
    }


def orientation_copy_unusable(text: str) -> bool:
    """True when copy cannot carry guest identity, topic, and listener stakes.

    A trailing forward-cue question is fine after a factual setup. A line that
    is only a meta-question ("What should we listen for as that opens?") is not.
    """
    t = " ".join(str(text or "").split())
    if not t:
        return True
    if len(t.split()) < 6:
        return True
    low = t.lower()
    if "listen for" in low and "open" in low and "." not in t and "!" not in t[:-1]:
        return True
    # Entire copy is a question — no prior statement that could name guest/topic.
    if t.endswith("?") and "." not in t and "!" not in t[:-1]:
        return True
    if "before the science" in low or "meet the founder at the center" in low:
        return True
    return False


def _target_text(ctx: RunContext, target_segment_id: str) -> str:
    if not target_segment_id or not ctx.artifact_exists("segments/manifest.json"):
        return ""
    manifest = ctx.read_json("segments/manifest.json")
    for row in (manifest.get("segments") or []) if isinstance(manifest, dict) else []:
        if isinstance(row, dict) and str(row.get("segment_id") or "") == target_segment_id:
            return str(row.get("text") or row.get("text_excerpt") or "")
    return ""


def _role_is_frame(role: str) -> bool:
    try:
        from interview_mux.conversation_context import role_is_frame

        return role_is_frame(role)
    except Exception:
        return (role or "").lower() in {
            "interviewer",
            "moderator",
            "co_host",
            "host",
            "frame",
        }


def _segment_role(row: dict[str, Any] | None) -> str:
    if not isinstance(row, dict):
        return ""
    return str(row.get("speaker_role") or row.get("role") or "").strip().lower()


def _opening_native_text(ctx: RunContext, ordered_segment_ids: list[str]) -> str:
    """Concat consecutive opening interviewer natives (hosts may split the intro)."""
    if not ordered_segment_ids or not ctx.artifact_exists("segments/manifest.json"):
        return ""
    manifest = ctx.read_json("segments/manifest.json")
    by_id = {
        str(row.get("segment_id") or ""): row
        for row in ((manifest.get("segments") or []) if isinstance(manifest, dict) else [])
        if isinstance(row, dict) and row.get("segment_id")
    }
    parts: list[str] = []
    for i, sid in enumerate(ordered_segment_ids[:3]):
        row = by_id.get(str(sid)) or {}
        text = str(row.get("text") or row.get("text_excerpt") or "").strip()
        role = _segment_role(row)
        if i == 0:
            if text:
                parts.append(text)
            if not _role_is_frame(role):
                break
            continue
        if not _role_is_frame(role):
            break
        if text:
            parts.append(text)
    return " ".join(parts)


def _opening_is_host_framed(ctx: RunContext, ordered_segment_ids: list[str]) -> bool:
    if not ordered_segment_ids or not ctx.artifact_exists("segments/manifest.json"):
        return False
    first = str(ordered_segment_ids[0])
    manifest = ctx.read_json("segments/manifest.json")
    for row in (manifest.get("segments") or []) if isinstance(manifest, dict) else []:
        if isinstance(row, dict) and str(row.get("segment_id") or "") == first:
            role = _segment_role(row)
            seg_type = str(row.get("type") or "").lower()
            return _role_is_frame(role) or "interview" in seg_type
    return False


def native_open_already_orients(
    ctx: RunContext,
    ordered_segment_ids: list[str] | None = None,
    target_segment_id: str | None = None,
) -> bool:
    """True when native hosts already greet / introduce before any synthetic VO."""
    ordered = [str(x) for x in (ordered_segment_ids or []) if x]
    if not ordered and target_segment_id:
        ordered = [str(target_segment_id)]
    text = _opening_native_text(ctx, ordered).strip()
    if not text and target_segment_id:
        text = _target_text(ctx, target_segment_id).strip()
    if len(text.split()) < 12:
        return False
    if not _opening_is_host_framed(ctx, ordered):
        return False
    if _NATIVE_INTRO_RE.search(text):
        return True
    brief = (
        ctx.read_json("understanding/content_brief.json")
        if ctx.artifact_exists("understanding/content_brief.json")
        else {}
    )
    brief = brief if isinstance(brief, dict) else {}
    guest = _first_text(brief, "guest_name", "interviewee_name", "subject_name")
    return bool(guest and guest.casefold() in text.casefold())


def orientation_omitted(gap_report: dict[str, Any] | None) -> bool:
    """True when opening orientation is durably waived via ``opening_orientation`` meta.

    Stale line-level ``skipped_optional`` / ``air_script_omit`` alone must not count —
    ``ORIENTATION_ALWAYS`` / ``filter_gap_lines_for_air_script`` revive those. Durable
    line waives are handled by ``air_script._orientation_line_waived`` (reason codes).
    """
    if not isinstance(gap_report, dict):
        return False
    meta = gap_report.get("opening_orientation")
    if not isinstance(meta, dict):
        return False
    return bool(meta.get("omitted")) or meta.get("required") is False


def _omit_orientation_payload(
    *,
    first: str,
    hook: str | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "line_id": None,
        "sequence": SEQUENCE_NATIVE_OPEN,
        "native_cold_open_segment_id": hook,
        "target_segment_id": first,
        "required": False,
        "omitted": True,
        "omit_reason": reason,
    }


def ensure_episode_orientation(
    ctx: RunContext,
    gap_report: dict[str, Any],
    ordered_segment_ids: list[str],
    *,
    orientation_nugget_ids: list[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Ensure orientation when needed; omit when native hosts already intro."""
    if not ordered_segment_ids or not isinstance(gap_report, dict):
        return gap_report, []
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled

        if not gap_framing_enabled(ctx):
            return gap_report, []
    except Exception:
        pass

    nugget_recovery_ids = [str(x) for x in (orientation_nugget_ids or []) if x]
    if not nugget_recovery_ids and isinstance(gap_report.get("orientation_nugget_recovery"), dict):
        nugget_recovery_ids = [
            str(x)
            for x in (gap_report["orientation_nugget_recovery"].get("nugget_ids") or [])
            if x
        ]
    force_synthetic_for_nuggets = bool(nugget_recovery_ids)

    # Honor durable G1 / operator omit — never remint required=True and revive a
    # preface without WAV (exec_11130 pending_writes/edl gap_report thrash).
    if orientation_omitted(gap_report) and not force_synthetic_for_nuggets:
        return gap_report, []

    ordered = [str(x) for x in ordered_segment_ids if x]
    first = ordered[0]
    hook = native_cold_open_segment_id(ctx, ordered)
    sequence = SEQUENCE_COLD_OPEN if hook else SEQUENCE_STRAIGHT
    # Prefer omit when native hosts already greet/introduce. Operator-pinned
    # orientation still airs if the operator wrote it on purpose.
    # High-salience excluded nuggets may force the first synthetic VO to carry them.
    if native_open_already_orients(ctx, ordered, target_segment_id=first) and not force_synthetic_for_nuggets:
        existing = [
            dict(x)
            for x in (gap_report.get("interviewer_lines") or [])
            if isinstance(x, dict)
        ]
        operator_pin = next(
            (
                x
                for x in existing
                if is_episode_orientation(x) and str(x.get("origin") or "") == "operator"
            ),
            None,
        )
        if operator_pin is None:
            lines = [x for x in existing if not is_episode_orientation(x)]
            out = dict(gap_report)
            out["interviewer_lines"] = lines
            out["opening_orientation"] = _omit_orientation_payload(
                first=first, hook=hook, reason="native_open_self_orients"
            )
            return out, [
                {
                    "action": "omit_episode_orientation",
                    "reason": "native_open_self_orients",
                    "segment_id": first,
                }
            ]
    placement = "after" if hook else "before"
    target = hook or first
    lines = [dict(x) for x in (gap_report.get("interviewer_lines") or []) if isinstance(x, dict)]
    orientations = [x for x in lines if is_episode_orientation(x)]
    if not orientations:
        orientations = [
            x
            for x in lines
            if str(x.get("line_category") or "") == "episode_preface"
            and str(x.get("targets_segment_id") or "") == target
        ]
    actions: list[dict[str, Any]] = []

    if orientations:
        preferred = next(
            (x for x in orientations if str(x.get("origin") or "") == "operator"),
            orientations[0],
        )
    else:
        text, extracted_from = _fallback_orientation_text(ctx)
        delivery = "record"
        try:
            from interview_mux.gap_vo_gates import resolve_gap_vo_delivery

            delivery = (
                "synthesize"
                if resolve_gap_vo_delivery(ctx) == "chatterbox"
                else "record"
            )
        except Exception:
            if any(str(x.get("delivery") or "") == "synthesize" for x in lines):
                delivery = "synthesize"
        preferred = {
            "line_id": ORIENTATION_LINE_ID,
            "gap_type": "missing_setup",
            "line_category": "episode_preface",
            "text": text,
            "targets_segment_id": target,
            "placement": placement,
            "delivery": delivery,
            "supports_segment_ids": [target],
            "rationale": "Orient the listener to the guest, topic, and stakes before the body.",
            "extracted_from": extracted_from,
            "origin": "deterministic_orientation_guard",
        }
        actions.append({"action": "mint_episode_orientation", "line_id": preferred["line_id"]})

    chosen = dict(preferred)
    prior_contract = {
        key: chosen.get(key)
        for key in (
            "line_category",
            "episode_orientation",
            "opening_sequence",
            "targets_segment_id",
            "placement",
            "supports_segment_ids",
            "allow_music_bed_overlap",
            "orientation_missions",
        )
    }
    old_target = str(chosen.get("targets_segment_id") or "")
    chosen["line_id"] = str(chosen.get("line_id") or ORIENTATION_LINE_ID)
    chosen["line_category"] = "episode_preface"
    chosen["episode_orientation"] = True
    chosen["opening_sequence"] = sequence
    chosen["targets_segment_id"] = target
    chosen["placement"] = placement
    chosen["supports_segment_ids"] = [target]
    chosen["allow_music_bed_overlap"] = True
    chosen["orientation_missions"] = [
        "guest_identity",
        "conversation_topic",
        "listener_stakes",
    ]
    if str(chosen.get("origin") or "") != "operator" and orientation_copy_unusable(
        str(chosen.get("text") or "")
    ):
        text, extracted_from = _fallback_orientation_text(ctx)
        chosen["text"] = text
        chosen["extracted_from"] = extracted_from
        chosen["origin"] = "deterministic_orientation_guard"
        actions.append(
            {
                "action": "rewrite_episode_orientation_meta_question",
                "line_id": chosen["line_id"],
            }
        )
    # The legacy fallback ends "Let's hear how it unfolded."  That is a generic
    # origin cue, not a handoff into the actual opening native.  Always repair
    # the final sentence against the final selected first clip.
    try:
        from interview_mux.gap_vo_prior_context import (
            cold_open_layup_ok,
            repair_last_sentence_layup,
        )

        target_text = _target_text(ctx, target)
        if not cold_open_layup_ok(chosen, target_text=target_text, ordered_ids=ordered):
            prior_text = str(chosen.get("text") or "")
            repaired_text = repair_last_sentence_layup(
                prior_text,
                target_text=target_text,
                category="episode_preface",
                target_segment_id=target,
            )
            if orientation_copy_unusable(repaired_text) and not orientation_copy_unusable(
                prior_text
            ):
                repaired_text = prior_text
            if repaired_text != prior_text:
                chosen["text"] = repaired_text
                actions.append(
                    {
                        "action": "repair_episode_orientation_last_sentence",
                        "line_id": chosen["line_id"],
                        "targets_segment_id": target,
                    }
                )
        # Spoken-copy at G1 synth uses richer run evidence than cold-open alone.
        # A topic body that restates the first native still deadlocks synthesize.
        try:
            from interview_mux.spoken_copy_guard import (
                enrich_evidence_from_run,
                spoken_copy_violations,
            )

            evidence = enrich_evidence_from_run(
                ctx,
                {
                    "line_id": chosen.get("line_id"),
                    "targets_segment_id": target,
                    "line_category": "episode_preface",
                    "target_excerpt": target_text,
                },
            )
            # Orientation is grounded from the brief; the opening native often
            # illustrates that same thesis. That overlap is not restatement.
            if (
                not target_text
                or str(chosen.get("origin") or "") == "deterministic_orientation_guard"
            ):
                evidence.pop("target_excerpt", None)
                evidence.pop("after_excerpt", None)
                evidence.pop("next_clip_text", None)
            if spoken_copy_violations(
                str(chosen.get("text") or ""), evidence=evidence, seen_texts=[]
            ):
                speakable = (
                    "Before the science, meet the founder at the center of this "
                    "conversation. Let's hear why that introduction matters."
                )
                repaired = repair_last_sentence_layup(
                    "Before the science, meet the founder at the center of this conversation.",
                    target_text=target_text,
                    category="episode_preface",
                    target_segment_id=target,
                )
                # Prefer the full grounded body+cue before a cue-only repair.
                for candidate in (speakable, repaired):
                    if orientation_copy_unusable(candidate):
                        continue
                    probe = dict(chosen)
                    probe["text"] = candidate
                    if spoken_copy_violations(
                        candidate, evidence=evidence, seen_texts=[]
                    ):
                        continue
                    if not cold_open_layup_ok(
                        probe, target_text=target_text, ordered_ids=ordered
                    ):
                        continue
                    chosen["text"] = candidate
                    actions.append(
                        {
                            "action": "repair_episode_orientation_spoken_copy",
                            "line_id": chosen["line_id"],
                            "targets_segment_id": target,
                        }
                    )
                    break
        except Exception:
            pass
    except Exception:
        # Orientation remains available if a partial run lacks the source manifest.
        pass
    # Retargeting / courtesy rewrites can leave a 1–4 word hinge that fails the
    # opening contract (<6 words). Replace with grounded fallback copy.
    if orientation_copy_unusable(str(chosen.get("text") or "")):
        text, extracted_from = _fallback_orientation_text(ctx)
        if not orientation_copy_unusable(text):
            chosen["text"] = text
            if extracted_from:
                chosen["extracted_from"] = extracted_from
            actions.append(
                {
                    "action": "thicken_episode_orientation_text",
                    "line_id": chosen["line_id"],
                    "words": len(text.split()),
                }
            )
    # Required orientation must not keep hard spoken scaffolding after rewrite.
    try:
        from interview_mux.spoken_meta_lint import (
            is_hard_structure_violation,
            rewrite_speaker_role_labels,
            spoken_structure_hits,
        )

        orient_text = str(chosen.get("text") or "")
        healed = rewrite_speaker_role_labels(orient_text)
        if healed != orient_text:
            chosen["text"] = healed
            actions.append(
                {
                    "action": "rewrite_episode_orientation_speaker_role_labels",
                    "line_id": chosen["line_id"],
                }
            )
            orient_text = healed
        hits = spoken_structure_hits(orient_text)
        hard_hits = [h for h in hits if is_hard_structure_violation(h)]
        if hard_hits:
            raise RuntimeError(
                "opening orientation contract failed: spoken scaffolding remains "
                f"on required orientation ({', '.join(hard_hits)})"
            )
    except RuntimeError:
        raise
    except Exception:
        pass
    chosen["recompose_action"] = "retargeted" if old_target != target else "kept"
    if old_target != target:
        actions.append(
            {
                "action": "retarget_episode_orientation",
                "line_id": chosen["line_id"],
                "from": old_target or None,
                "to": target,
                "placement": placement,
            }
        )
    elif prior_contract != {
        key: chosen.get(key)
        for key in prior_contract
    }:
        actions.append(
            {
                "action": "normalize_episode_orientation",
                "line_id": chosen["line_id"],
                "sequence": sequence,
            }
        )
    if len(orientations) > 1:
        actions.append(
            {
                "action": "dedupe_episode_orientation",
                "kept": chosen["line_id"],
                "removed_count": len(orientations) - 1,
            }
        )

    try:
        from interview_mux.homunculus.runtime import has_homunculus_features

        if has_homunculus_features(ctx):
            chosen["vo_shape"] = str(chosen.get("vo_shape") or "third_person")
    except Exception:
        pass

    if nugget_recovery_ids:
        # Do not rewrite orientation copy when a seated WAV already exists for
        # this line_id — embed invalidates script_hash and EDL then ships
        # audible_count=0 (exec_11630: dry-run seated, live ensure+embed wiped bind).
        wav_bound = False
        try:
            lid = str(chosen.get("line_id") or ORIENTATION_LINE_ID).strip()
            pickup = ctx.final_path("vo_pickup")
            for base in (
                pickup / "matched",
                pickup / "synthesized",
                pickup / "clean",
                pickup / "normalized",
                pickup,
            ):
                cand = base / f"{lid}.wav"
                if cand.is_file() and cand.stat().st_size > 1000:
                    wav_bound = True
                    break
        except Exception:
            wav_bound = False
        if wav_bound:
            actions.append(
                {
                    "action": "skip_nugget_embed_wav_bound",
                    "line_id": chosen.get("line_id"),
                    "nugget_ids": nugget_recovery_ids[:4],
                }
            )
        else:
            chosen, embed_notes = embed_orientation_nugget_recovery(
                ctx, chosen, nugget_recovery_ids
            )
            for note in embed_notes:
                actions.append(
                    {
                        "action": "embed_orientation_nugget_recovery",
                        "line_id": chosen.get("line_id"),
                        "detail": note,
                    }
                )
            if force_synthetic_for_nuggets and not orientations:
                actions.append(
                    {
                        "action": "force_synthetic_orientation_for_nuggets",
                        "line_id": chosen.get("line_id"),
                        "nugget_ids": nugget_recovery_ids[:2],
                    }
                )

    orientation_ids = {
        str(x.get("line_id") or "") for x in orientations if x.get("line_id")
    }
    non_orientation = [
        x
        for x in lines
        if not is_episode_orientation(x)
        and str(x.get("line_id") or "") not in orientation_ids
    ]
    out = dict(gap_report)
    out["interviewer_lines"] = [chosen, *non_orientation]
    opening_payload: dict[str, Any] = {
        "line_id": chosen["line_id"],
        "sequence": sequence,
        "native_cold_open_segment_id": hook,
        "target_segment_id": target,
        "required": True,
    }
    if nugget_recovery_ids:
        opening_payload["nugget_recovery"] = True
        opening_payload["nugget_ids"] = [
            str(x) for x in (chosen.get("nugget_ids") or nugget_recovery_ids) if x
        ]
    out["opening_orientation"] = opening_payload
    if nugget_recovery_ids:
        out["orientation_nugget_recovery"] = {
            "nugget_ids": nugget_recovery_ids,
            "forced_synthetic": force_synthetic_for_nuggets,
        }
    return out, actions


def retarget_orientation_to_open(ctx: RunContext) -> list[str]:
    """Point episode orientation at the current selection open; sync EDL + pickups."""
    written: list[str] = []
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return written
    if not ctx.artifact_exists("master/selection.json"):
        return written
    gap = ctx.read_json("understanding/gap_report.json")
    sel = ctx.read_json("master/selection.json")
    if not isinstance(gap, dict) or not isinstance(sel, dict):
        return written
    ordered = [str(x) for x in (sel.get("ordered_segment_ids") or []) if x]
    if not ordered:
        return written
    updated, actions = ensure_episode_orientation(ctx, gap, ordered)
    target = str(
        ((updated.get("opening_orientation") or {}) if isinstance(updated, dict) else {}).get(
            "target_segment_id"
        )
        or ordered[0]
    )
    line_id = ORIENTATION_LINE_ID
    for line in (updated.get("interviewer_lines") or []) if isinstance(updated, dict) else []:
        if isinstance(line, dict) and is_episode_orientation(line):
            line_id = str(line.get("line_id") or ORIENTATION_LINE_ID)
            target = str(line.get("targets_segment_id") or target)
            break
    # Orientation retarget runs from consumers too (edl). Once gap_report is
    # frozen by its owner, keep the retarget in memory instead of rewriting the
    # sealed body — the caller still reads the updated doc from disk owner state.
    try:
        from interview_mux.artifact_ownership import write_permitted
        from interview_mux.write_staging import active_stage_id

        stage_now = str(active_stage_id() or "")
        allowed, deny_reason = write_permitted(
            ctx,
            "understanding/gap_report.json",
            stage_now,
            role="producer",
            verb="persist",
        )
    except Exception:
        allowed, deny_reason, stage_now = True, "", ""
    if not allowed:
        ctx.log(
            "orientation retarget: gap_report frozen — skipping rewrite "
            f"(stage={stage_now or 'unknown'}, {deny_reason})",
            level="info",
            stage=stage_now or None,
        )
        return written
    ctx.write_json("understanding/gap_report.json", updated)
    written.append("understanding/gap_report.json")

    if ctx.artifact_exists("vo_pickup/synthesis_report.json"):
        report = ctx.read_json("vo_pickup/synthesis_report.json")
        if isinstance(report, dict):
            changed = False
            for entry in report.get("entries") or []:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("line_id") or "") != line_id:
                    continue
                if str(entry.get("targets_segment_id") or "") != target:
                    entry["targets_segment_id"] = target
                    changed = True
            if changed:
                ctx.write_json("vo_pickup/synthesis_report.json", report)
                written.append("vo_pickup/synthesis_report.json")

    if ctx.artifact_exists("master/edl.json"):
        edl = ctx.read_json("master/edl.json")
        if isinstance(edl, dict):
            changed = False
            for clip in edl.get("clips") or []:
                if not isinstance(clip, dict):
                    continue
                if str(clip.get("line_id") or "") != line_id:
                    continue
                if str(clip.get("targets_segment_id") or "") != target:
                    clip["targets_segment_id"] = target
                    changed = True
            if changed:
                from interview_mux.air_order import write_live_edl

                write_live_edl(ctx, edl, source="opening_orientation")
                written.append("master/edl.json")
    _ = actions
    return written


def validate_opening_orientation(
    *,
    gap_report: dict[str, Any] | None,
    edl: dict[str, Any] | None,
    max_non_silence_index: int = 3,
) -> list[str]:
    """Validate opening grammar: one early orientation, or none when native already intros."""
    errors: list[str] = []
    meta = (
        (gap_report or {}).get("opening_orientation")
        if isinstance(gap_report, dict)
        else None
    )
    meta_line_id = (
        str(meta.get("line_id") or "").strip() if isinstance(meta, dict) else ""
    )
    report_lines = [
        x
        for x in ((gap_report or {}).get("interviewer_lines") or [])
        if isinstance(x, dict) and is_episode_orientation(x) and not x.get("skipped_optional")
    ]
    # When meta names the required orientation, ignore sibling episode_preface
    # act/chapter prefaces (exec_11630: vo_preface_act1 + episode_orientation → count=2).
    if meta_line_id:
        report_lines = [
            x
            for x in report_lines
            if str(x.get("line_id") or "") == meta_line_id
            or bool(x.get("episode_orientation"))
        ]
        # Prefer the meta id exclusively when present among candidates.
        named = [x for x in report_lines if str(x.get("line_id") or "") == meta_line_id]
        if named:
            report_lines = named
    omitted = orientation_omitted(gap_report if isinstance(gap_report, dict) else None)
    if omitted:
        if report_lines:
            return [f"opening_orientation_count={len(report_lines)} expected=0"]
        clips = [x for x in ((edl or {}).get("clips") or []) if isinstance(x, dict)]
        music_markers = [
            i
            for i, clip in enumerate(clips)
            if clip.get("type") == "silence"
            and str(clip.get("air_kind") or "") == OPENING_MUSIC_AIR_KIND
        ]
        first_speech_index = next(
            (i for i, clip in enumerate(clips) if clip.get("type") == "speech"),
            None,
        )
        if music_markers and first_speech_index is not None and not (
            music_markers[0] < first_speech_index
        ):
            errors.append("opening_sequence must be music→body")
        return errors
    if len(report_lines) != 1:
        return [f"opening_orientation_count={len(report_lines)} expected=1"]
    line = report_lines[0]
    line_id = str(line.get("line_id") or "")
    missions = {str(x) for x in (line.get("orientation_missions") or []) if x}
    required_missions = {
        "guest_identity",
        "conversation_topic",
        "listener_stakes",
    }
    if not required_missions.issubset(missions):
        errors.append(
            "opening_orientation_missions_missing="
            + ",".join(sorted(required_missions - missions))
        )
    if orientation_copy_unusable(str(line.get("text") or "")):
        errors.append("opening_orientation_text_too_thin")
    clips = [x for x in ((edl or {}).get("clips") or []) if isinstance(x, dict)]
    audible = [
        x
        for x in clips
        if x.get("type") == "vo_pickup" and str(x.get("line_id") or "") == line_id
    ]
    if len(audible) != 1:
        errors.append(f"opening_orientation_audible_count={len(audible)} expected=1")
        return errors
    non_silence = [x for x in clips if x.get("type") != "silence"]
    intro_index = non_silence.index(audible[0])
    if intro_index > max_non_silence_index:
        errors.append(f"opening_orientation_too_late index={intro_index}")
    sequence = str(line.get("opening_sequence") or SEQUENCE_STRAIGHT)
    music_markers = [
        i
        for i, clip in enumerate(clips)
        if clip.get("type") == "silence"
        and str(clip.get("air_kind") or "") == OPENING_MUSIC_AIR_KIND
    ]
    if len(music_markers) != 1:
        errors.append(f"opening_music_marker_count={len(music_markers)} expected=1")
        return errors
    marker_index = music_markers[0]
    intro_clip_index = clips.index(audible[0])
    first_speech_index = next(
        (i for i, clip in enumerate(clips) if clip.get("type") == "speech"),
        None,
    )
    if sequence == SEQUENCE_COLD_OPEN:
        body_after_intro = any(
            i > intro_clip_index and clip.get("type") == "speech"
            for i, clip in enumerate(clips)
        )
        if first_speech_index is None or not (
            first_speech_index < marker_index < intro_clip_index
        ) or not body_after_intro:
            errors.append("opening_sequence must be native_hook→music→intro→body")
    elif first_speech_index is None or not (
        intro_clip_index < marker_index < first_speech_index
    ):
        errors.append("opening_sequence must be intro→music→body")
    return errors
