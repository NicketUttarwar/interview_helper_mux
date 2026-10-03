"""Evidence-aware safety guard for every listener-facing synthetic line."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from typing import Any, Iterable

from interview_mux.spoken_meta_lint import is_hard_structure_violation, lint_spoken_text

_PATH_OR_FILE = re.compile(
    r"(?:^|[\s(\"'])(?:[A-Za-z]:\\|/[\w.-]+/|\.{0,2}/[\w.-]+)|"
    r"\b[\w.-]+\.(?:json|ya?ml|wav|mp3|txt|csv|py|tsx?)\b",
    re.IGNORECASE,
)
_PRODUCTION_JARGON = re.compile(
    r"\b(?:"
    r"edl|edit decision list|"
    # Bare "stage"/"timeline" are ordinary English ("life stage", "career timeline").
    # Only flag pipeline-ops compounds.
    r"pipeline\s+stage|from_stage|until_stage|stage_done|edit\s+timeline|"
    r"pipeline|artifact|schema|"
    r"quality control|qc(?:\s+pass|\s+fail)?|lint|validator|"
    r"selection order|source segment|native segment|gap report|"
    r"synthesis report|fallback backend|confidence score|"
    r"listener confusion|missing setup|missing question|"
    r"unaired\s+corpus|corpus\s+nugget"
    r")\b",
    re.IGNORECASE,
)
_PLACEHOLDER = re.compile(
    r"(?:\{\{[^{}]+\}\}|\{[A-Za-z_][^{}]*\}|<[^<>]+>|\[[A-Z][A-Z0-9_ -]+\]|"
    r"\b(?:tbd|todo|fixme|lorem ipsum|insert (?:name|topic|text) here)\b)",
    re.IGNORECASE,
)
_MALFORMED_END = re.compile(r"(?:\.\.\.|…|[—–,:;/(\[])\s*$")
_NEXT_WORD = re.compile(r"\b(?:next|then|after that|what followed)\b", re.IGNORECASE)
_OPENING_STYLE_BRIDGE = re.compile(
    r"\b(?:"
    r"meet the entrepreneur|on the show today|who is\b|co-founder and ceo|"
    r"welcome to|we(?:'|')ve got\b|joining us today"
    r")\b",
    re.IGNORECASE,
)
# Relative / stock hinges are never acceptable air copy — even with evidence.
_GENERIC_FILLER = re.compile(
    r"\b(?:"
    r"what (?:happened|changed|comes) next|"
    r"what changed after that|"
    r"what happened after that|"
    r"what follows|"
    r"what shifted from there|"
    r"next beat|"
    r"coming up|"
    r"where does this stretch lead|"
    r"broader story changing|"
    r"there is more to that story|"
    r"stepping back,? what set this part of the story in motion|"
    r"what set this part of the story in motion"
    r")\b",
    re.IGNORECASE,
)
_PROPER_NAME = re.compile(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*\b")
_TOKEN = re.compile(r"[A-Za-z0-9₹$%]+")
_STOCK = {
    "there is more to that story",
    "and then this next beat",
    "next the focus shifts",
    "meanwhile what happened next",
    "coming up where does this stretch lead",
    "what changed after that",
    "what happened next",
    "what shifted from there",
    "stepping back what set this part of the story in motion",
    "what set this part of the story in motion",
}
_ENTITY_IGNORE = {
    "And",
    "Alright",
    "Asking",
    "Away",
    "Before",
    "Beyond",
    "Building",
    "But",
    "Business",
    "Budget",
    "Capital",
    "Challenge",
    "Choosing",
    "Company",
    "Culture",
    "Customer",
    "Each",
    "Every",
    "Facing",
    "Failure",
    "Finding",
    "For",
    "Getting",
    "Growth",
    "How",
    "In",
    "Leadership",
    "Let",
    "Looking",
    "Making",
    "Margin",
    "Market",
    "Moving",
    "Next",
    "Okay",
    "Once",
    "Opportunity",
    "Outside",
    "Performance",
    "Pressure",
    "Product",
    "Revenue",
    "Right",
    "Risk",
    "So",
    "Stepping",
    "Strategy",
    "Success",
    "Taking",
    "Team",
    "That",
    "The",
    "These",
    "This",
    "Those",
    "Trust",
    "Turning",
    "Well",
    "What",
    "When",
    "Where",
    "Who",
    "Why",
    "With",
}
_IMPERATIVE_IGNORE = {
    "Hear",
    "Listen",
    "Brace",
    "Remember",
    "Those",
    "These",
    "Please",
    "Imagine",
    "Consider",
    "Notice",
    "Watch",
    "Stay",
    "Hold",
    "Keep",
}


def normalize_script(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def sentence_keys(text: str) -> list[str]:
    """Return punctuation-insensitive keys for listener-facing sentences.

    Repeating words across a native/VO seam is permitted. Repeating a complete
    sentence in synthetic speech is not: it sounds like a synthesis failure,
    regardless of its target or placement in the EDL.
    """
    sentences = re.split(r"(?<=[.!?])\s+|\n+", normalize_script(text))
    keys: list[str] = []
    for sentence in sentences:
        tokens = [token.casefold() for token in _TOKEN.findall(sentence)]
        # Ignore isolated interjections, but retain short questions such as
        # "What changed?" so they cannot recur as canned VO.
        if len(tokens) >= 2:
            keys.append(" ".join(tokens))
    return keys


#: Violations a line can be cured of by dropping the offending sentence.
REPEATED_SENTENCE_VIOLATIONS: frozenset[str] = frozenset(
    {"spoken_repeated_sentence", "spoken_repeated_sentence_in_line"}
)


def strip_repeated_sentences(text: str, seen_texts: Iterable[str] | None = None) -> str:
    """Drop sentences another line already voiced, and repeats inside the line.

    Sharded compose writes each shard without seeing the others, so two
    shards can open a context line with the same sentence. The rest of the
    line is still the model's own grounded copy; only the repeat has to go
    (ISSUES 128). Returns the remaining text, possibly empty.
    """
    seen_keys = {key for seen in (seen_texts or []) for key in sentence_keys(str(seen))}
    sentences = re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", normalize_script(text))
    local: set[str] = set()
    kept: list[str] = []
    for sentence in sentences:
        keys = sentence_keys(sentence)
        if keys and any(key in seen_keys or key in local for key in keys):
            continue
        local.update(keys)
        kept.append(sentence.strip())
    return normalize_script(" ".join(kept))


def dedupe_sentences(text: str) -> str:
    """Remove repeated complete sentences, retaining the final voiced form.

    Authoring can produce a bare question title followed by the same question
    with terminal punctuation. Keeping the final form preserves the forward
    cue while preventing the TTS from saying it twice.
    """
    sentences = re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", normalize_script(text))
    seen: set[str] = set()
    kept_reversed: list[str] = []
    for sentence in reversed(sentences):
        keys = sentence_keys(sentence)
        key = keys[0] if len(keys) == 1 else ""
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        kept_reversed.append(sentence.strip())
    return normalize_script(" ".join(reversed(kept_reversed)))


def script_hash(text: str) -> str:
    return hashlib.sha256(normalize_script(text).encode("utf-8")).hexdigest()


def context_hash(evidence: dict[str, Any] | None) -> str:
    payload = evidence if isinstance(evidence, dict) else {}
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def evidence_for_line(line: dict[str, Any] | None) -> dict[str, Any]:
    row = line if isinstance(line, dict) else {}
    prior = row.get("prior_native_context")
    prior = prior if isinstance(prior, dict) else {}
    return {
        "line_id": row.get("line_id"),
        "target_segment_id": row.get("targets_segment_id"),
        "placement": row.get("placement"),
        "line_category": row.get("line_category"),
        "after_segment_id": row.get("after_segment_id"),
        "before_segment_id": row.get("before_segment_id"),
        "before_excerpt": row.get("before_excerpt")
        or prior.get("prior_text")
        or prior.get("quote"),
        "after_excerpt": row.get("after_excerpt"),
        "target_excerpt": row.get("target_excerpt")
        or row.get("target_native_context"),
        "before_topic": row.get("before_topic"),
        "after_topic": row.get("after_topic") or row.get("target_topic"),
        "source_gap_ms": row.get("source_gap_ms"),
        "verified_person": row.get("verified_person"),
        "verified_place": row.get("verified_place"),
        "verified_time": row.get("verified_time"),
        "causal_cue": row.get("causal_cue"),
    }


def shorten_spoken_text(text: str, max_words: int) -> str:
    """Shorten at sentence/word boundaries without shipping a dangling fragment."""
    clean = normalize_script(text)
    if max_words <= 0 or len(clean.split()) <= max_words:
        return clean
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    kept: list[str] = []
    for sentence in sentences:
        proposed = normalize_script(" ".join([*kept, sentence]))
        if len(proposed.split()) > max_words:
            break
        kept.append(sentence)
    if kept:
        result = normalize_script(" ".join(kept))
    else:
        words = clean.split()[:max_words]
        result = " ".join(words).rstrip(" ,;:—–-")
        if result and result[-1] not in ".!?":
            result += "."
    return result


def _safe_context(raw: Any, *, max_words: int = 12) -> str:
    text = normalize_script(str(raw or ""))
    if not text:
        return ""
    if lint_spoken_text(text, label="context") or _PATH_OR_FILE.search(text):
        return ""
    if _PRODUCTION_JARGON.search(text) or _PLACEHOLDER.search(text):
        return ""
    # Pipeline snake_case tags (chapter_close_hitch, …) are not listener topics.
    low = text.casefold().strip()
    if re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)+", low) or (
        "_" in text and " " not in text.strip()
    ):
        return ""
    text = re.split(r"[.!?;]", text, maxsplit=1)[0].strip(" ,:—–-")
    return shorten_spoken_text(text, max_words).rstrip(".")


def _tokens(text: str) -> set[str]:
    return {
        token.casefold()
        for token in _TOKEN.findall(normalize_script(text))
        if len(token) > 2
    }


def _evidence_text(evidence: dict[str, Any]) -> str:
    parts: list[str] = []
    def collect(value: Any) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, (int, float)):
            parts.append(str(value))

    for key, value in evidence.items():
        if key not in {"strict_grounding", "required", "source_gap_ms", "chronology"}:
            collect(value)
    return " ".join(parts)


def enrich_evidence_from_run(ctx: Any, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach guest/host/company names so proper-noun grounding can pass."""
    ev = dict(evidence or {})
    name_bits: list[str] = []
    try:
        if getattr(ctx, "artifact_exists", lambda _p: False)("understanding/speakers.json"):
            speakers = ctx.read_json("understanding/speakers.json")
            for row in (speakers.get("speakers") or []) if isinstance(speakers, dict) else []:
                if not isinstance(row, dict):
                    continue
                for key in ("display_name", "name", "label", "canonical_name"):
                    val = str(row.get(key) or "").strip()
                    if val:
                        name_bits.append(val)
        if getattr(ctx, "artifact_exists", lambda _p: False)("understanding/content_brief.json"):
            brief = ctx.read_json("understanding/content_brief.json")
            if isinstance(brief, dict):
                for key in (
                    "guest_name",
                    "host_name",
                    "thesis",
                    "logline",
                    "episode_promise",
                    "company",
                    "brand",
                ):
                    val = str(brief.get(key) or "").strip()
                    if val:
                        name_bits.append(val)
                for topic in brief.get("topics") or []:
                    if isinstance(topic, str) and topic.strip():
                        name_bits.append(topic.strip())
                    elif isinstance(topic, dict):
                        label = str(topic.get("label") or topic.get("name") or "").strip()
                        if label:
                            name_bits.append(label)
    except Exception:
        pass
    blob = " ".join(dict.fromkeys(name_bits))
    if blob:
        existing = str(ev.get("target_excerpt") or "")
        ev["target_excerpt"] = (existing + " " + blob).strip()
        if not ev.get("verified_person") and name_bits:
            ev["verified_person"] = name_bits[0]
        ev["known_entities"] = blob
    return ev


def _restates_target(text: str, target: str) -> bool:
    a, b = _tokens(text), _tokens(target)
    if len(a) < 4 or len(b) < 4:
        return False
    return len(a & b) / max(1, min(len(a), len(b))) >= 0.72


def _repeated_proper_noun(text: str) -> bool:
    """True when the same person-name token appears more than once in one line."""
    counts: dict[str, int] = {}
    for entity in _PROPER_NAME.findall(text):
        if entity in _ENTITY_IGNORE or entity in _IMPERATIVE_IGNORE:
            continue
        for part in entity.split():
            if part in _ENTITY_IGNORE or part in _IMPERATIVE_IGNORE:
                continue
            key = part.casefold()
            counts[key] = counts.get(key, 0) + 1
            if counts[key] >= 2:
                return True
    return False


REGISTER_VIOLATION_CODES = frozenset(
    {
        "spoken_speaker_role_label",
        "spoken_name_attribution",
        "spoken_gendered_pronoun",
        "spoken_repeated_proper_noun",
    }
)


def violation_code(violation: str) -> str:
    return str(violation or "").split(":", 1)[0]


def is_register_violation(violation: str) -> bool:
    return violation_code(violation) in REGISTER_VIOLATION_CODES


def register_only_violations(violations: list[str]) -> bool:
    return bool(violations) and all(is_register_violation(v) for v in violations)


def _strip_name_attribution_clause(text: str) -> str:
    """Drop leading person-attribution from a setup clause."""
    stripped = re.sub(
        r"^[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?\s+"
        r"(?:explains?|says?|elaborates?|describes?|notes?|adds?|closes?|traces?|discusses?)\s+",
        "",
        normalize_script(text),
        count=1,
    )
    return normalize_script(stripped) or normalize_script(text)


def topic_forward_recovery_candidates(setup: str, unlock: str) -> list[str]:
    """Build topic-forward recovery lines from planner fields (no speaker attribution)."""
    setup_clean = _strip_name_attribution_clause(setup)
    unlock_clean = normalize_script(unlock)
    candidates: list[str] = []
    if setup_clean and unlock_clean:
        unlock_body = unlock_clean.rstrip(".!?")
        if unlock_body.casefold().startswith(("why ", "how ", "what ")):
            hinge = (
                f"Let's hear the explanation for "
                f"{unlock_body[0].lower()}{unlock_body[1:].rstrip('.!?')}?"
            )
        else:
            hinge = f"Let's hear what comes next on {unlock_body.lower()}."
        if unlock_body.casefold() not in setup_clean.casefold():
            candidates.append(f"{setup_clean.rstrip('.!?')}. {hinge}")
        candidates.append(f"{setup_clean.rstrip('.!?')}. {unlock_body}?")
    elif unlock_clean:
        unlock_body = unlock_clean.rstrip(".!?")
        if unlock_body.casefold().startswith(("why ", "how ", "what ")):
            candidates.append(
                f"Let's hear the explanation for "
                f"{unlock_body[0].lower()}{unlock_body[1:].rstrip('.!?')}?"
            )
        else:
            candidates.append(f"Let's hear what comes next on {unlock_body.lower()}.")
    elif setup_clean:
        candidates.append(setup_clean if setup_clean[-1:] in ".!?" else f"{setup_clean}.")
    return [normalize_script(c) for c in candidates if normalize_script(c)]


def spoken_copy_violations(
    text: str,
    *,
    evidence: dict[str, Any] | None = None,
    seen_texts: Iterable[str] | None = None,
) -> list[str]:
    clean = normalize_script(text)
    if not clean:
        return ["empty_spoken_copy"]
    errors = [
        err.rsplit("(", 1)[-1].rstrip(")")
        for err in lint_spoken_text(clean, label="spoken_copy")
    ]
    if _PATH_OR_FILE.search(clean):
        errors.append("spoken_path_or_filename")
    if _PRODUCTION_JARGON.search(clean):
        errors.append("spoken_production_jargon")
    if _PLACEHOLDER.search(clean):
        errors.append("spoken_placeholder")
    if _MALFORMED_END.search(clean) or clean.count("(") != clean.count(")"):
        errors.append("spoken_malformed_fragment")
    stock_key = re.sub(r"[^a-z0-9 ]+", "", clean.casefold()).strip()
    if stock_key in _STOCK:
        errors.append("spoken_stock_copy")
    seen = {normalize_script(x).casefold() for x in (seen_texts or []) if x}
    if clean.casefold() in seen:
        errors.append("spoken_repeated_copy")
    keys = sentence_keys(clean)
    if len(keys) != len(set(keys)):
        errors.append("spoken_repeated_sentence_in_line")
    seen_sentence_keys = {
        key for seen_text in (seen_texts or []) for key in sentence_keys(str(seen_text))
    }
    if set(keys) & seen_sentence_keys:
        errors.append("spoken_repeated_sentence")

    ev = evidence if isinstance(evidence, dict) else {}
    try:
        source_gap = (
            int(ev["source_gap_ms"]) if ev.get("source_gap_ms") is not None else None
        )
    except (TypeError, ValueError):
        source_gap = None
    if source_gap is not None and source_gap < 0 and _NEXT_WORD.search(clean):
        errors.append("spoken_chronology_mismatch")
    if source_gap is not None and source_gap < 0 and _OPENING_STYLE_BRIDGE.search(clean):
        errors.append("spoken_opening_style_bridge")
    if _OPENING_STYLE_BRIDGE.search(clean):
        try:
            from interview_mux.air_order_integrity import opening_body_start_index

            before_id = str(ev.get("before_segment_id") or "")
            air_index = ev.get("before_air_index")
            if air_index is not None and int(air_index) >= opening_body_start_index():
                errors.append("spoken_opening_style_bridge")
            elif before_id and ev.get("before_is_opening_tape"):
                errors.append("spoken_opening_style_bridge")
        except Exception:
            pass
    # Generic relative hinges are banned under every circumstance.
    if _GENERIC_FILLER.search(clean):
        errors.append("spoken_generic_filler")
    target = str(
        ev.get("after_excerpt")
        or ev.get("target_excerpt")
        or ev.get("next_clip_text")
        or ""
    )
    if target and _restates_target(clean, target):
        errors.append("spoken_next_clip_restatement")
    if _repeated_proper_noun(clean):
        errors.append("spoken_repeated_proper_noun")

    if bool(ev.get("strict_grounding")):
        corpus = _evidence_text(ev)
        corpus_fold = corpus.casefold()
        corpus_tokens = list(_tokens(corpus))
        unsupported: list[str] = []
        for entity in _PROPER_NAME.findall(clean):
            if entity in _ENTITY_IGNORE or entity in _IMPERATIVE_IGNORE:
                continue
            if entity.casefold() in corpus_fold:
                continue
            first = entity.split()[0].casefold()
            if first in corpus_fold:
                continue
            close = difflib.get_close_matches(entity.casefold(), corpus_tokens, n=1, cutoff=0.8)
            if close:
                continue
            unsupported.append(entity)
        if unsupported:
            errors.append("spoken_unsupported_entity:" + ",".join(unsupported[:3]))
    return list(dict.fromkeys(errors))


def _grounded_fallback(evidence: dict[str, Any]) -> str:
    """Evidence-only fallback. Never emit relative filler questions."""
    before_topic = _safe_context(evidence.get("before_topic"))
    after_topic = _safe_context(evidence.get("after_topic"))
    if before_topic and after_topic and before_topic.casefold() != after_topic.casefold():
        return f"Moving from {before_topic} to {after_topic}, what changed?"
    if after_topic:
        return f"Turning to {after_topic}, what changed?"
    if before_topic:
        return f"With {before_topic} established, what changed?"

    person = _safe_context(evidence.get("verified_person"))
    place = _safe_context(evidence.get("verified_place"))
    time = _safe_context(evidence.get("verified_time"))
    cause = _safe_context(evidence.get("causal_cue"))
    if cause:
        return f"With {cause} in place, what changed?"
    if person and _person_name_like(person):
        return f"How did {person} shape what happened?"
    if place:
        return f"What changed in {place}?"
    if time:
        return f"What changed around {time}?"
    # Excerpts alone are not enough for a speakable contextual hinge — omit.
    return ""


def _soften_mid_sentence_fallback(text: str) -> str:
    """Capitalize or prefix mid-sentence fragments into listener-facing openers.

    Mirrors ``edl_narrative_remutate._repair_mid_sentence_transition_openers``.
    """
    fb = normalize_script(text)
    if not fb:
        return ""
    if fb[:1].islower():
        return f"That {fb}"
    if _MALFORMED_END.search(fb):
        return fb.rstrip("—,;:") + "."
    return fb[:1].upper() + fb[1:] if fb else ""


def _person_name_like(person: str) -> bool:
    """True when ``person`` is a short name, not a clause stuffed into verified_person."""
    words = [w for w in str(person or "").split() if w]
    if not words or len(words) > 4:
        return False
    if any(ch in person for ch in ",;:"):
        return False
    banned = {"explains", "how", "because", "commitment", "growth", "insight"}
    if any(w.casefold() in banned for w in words):
        return False
    return True


def _is_orientation_purpose(purpose: str, evidence: dict[str, Any] | None = None) -> bool:
    blob = " ".join(
        [
            str(purpose or ""),
            str((evidence or {}).get("line_category") or ""),
            str((evidence or {}).get("line_id") or ""),
        ]
    ).lower()
    return any(
        key in blob
        for key in (
            "episode_orientation",
            "episode_preface",
            "vo_preface_episode",
            "opening_orientation",
        )
    )


def grounded_fallback_for_evidence(evidence: dict[str, Any] | None) -> str:
    """Return listener-safe grounded glue, or empty when evidence is insufficient."""
    return _grounded_fallback(dict(evidence or {}))


def load_persisted_spoken_texts(
    ctx: Any,
    *,
    exclude_line_id: str | None = None,
    exclude_text: str | None = None,
) -> list[str]:
    """Collect listener-facing VO already persisted for this run."""
    seen: list[str] = []
    exclude_norm = normalize_script(exclude_text or "").casefold()
    exclude_lid = str(exclude_line_id or "").strip()

    def _maybe_add(text: str, line_id: str = "") -> None:
        clean = normalize_script(text)
        if not clean:
            return
        if exclude_lid and line_id and line_id == exclude_lid:
            return
        if exclude_norm and clean.casefold() == exclude_norm:
            return
        seen.append(clean)

    try:
        if getattr(ctx, "artifact_exists", lambda _p: False)("understanding/gap_report.json"):
            report = ctx.read_json("understanding/gap_report.json")
            if isinstance(report, dict):
                for row in report.get("interviewer_lines") or []:
                    if not isinstance(row, dict) or row.get("skipped_optional"):
                        continue
                    _maybe_add(
                        str(row.get("text") or ""),
                        str(row.get("line_id") or ""),
                    )
        if getattr(ctx, "artifact_exists", lambda _p: False)("master/transitions.json"):
            transitions = ctx.read_json("master/transitions.json")
            if isinstance(transitions, dict):
                for row in transitions.get("transitions") or []:
                    if not isinstance(row, dict):
                        continue
                    _maybe_add(str(row.get("text") or ""))
        if getattr(ctx, "artifact_exists", lambda _p: False)(
            "understanding/synthetic_framing_plan.json"
        ):
            plan = ctx.read_json("understanding/synthetic_framing_plan.json")
            if isinstance(plan, dict):
                for row in plan.get("lines") or []:
                    if not isinstance(row, dict):
                        continue
                    _maybe_add(
                        str(row.get("text") or ""),
                        str(row.get("line_id") or ""),
                    )
    except Exception:
        pass
    return seen


def guard_spoken_copy(
    text: str,
    *,
    evidence: dict[str, Any] | None = None,
    required: bool,
    purpose: str = "synthetic_vo",
    seen_texts: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Allow safe copy, substitute grounded copy, omit optional, or block required."""
    ev = dict(evidence or {})
    original = normalize_script(text)
    violations = spoken_copy_violations(
        original, evidence=ev, seen_texts=seen_texts
    )
    if not violations:
        return {
            "action": "allow",
            "text": original,
            "violations": [],
            "script_hash": script_hash(original),
            "context_hash": context_hash(ev),
            "purpose": purpose,
        }
    entity_only = bool(violations) and all(
        v.startswith("spoken_unsupported_entity") for v in violations
    )
    fallback = _grounded_fallback(ev)
    if entity_only and original:
        stripped = original
        for raw in violations:
            names = raw.split(":", 1)[-1]
            for name in names.split(","):
                token = name.strip()
                if token:
                    stripped = re.sub(rf"\b{re.escape(token)}\b", "", stripped)
        stripped = normalize_script(stripped)
        if stripped and not spoken_copy_violations(stripped, evidence=ev, seen_texts=seen_texts):
            fallback = stripped
    if original and set(violations) & REPEATED_SENTENCE_VIOLATIONS:
        # The line's own copy minus the repeated sentence beats a generic
        # hinge, and beats blocking a required line outright (ISSUES 128).
        # A remnant under six words is a hinge, not a line ("What broke
        # next?"), and is not kept.
        stripped = strip_repeated_sentences(original, seen_texts)
        if (
            stripped
            and stripped != original
            and len(stripped.split()) >= 6
            and not spoken_copy_violations(stripped, evidence=ev, seen_texts=seen_texts)
        ):
            fallback = stripped
    fallback_errors = (
        spoken_copy_violations(fallback, evidence=ev, seen_texts=seen_texts)
        if fallback
        else ["no_grounded_fallback"]
    )
    hard = any(is_hard_structure_violation(v.split(":", 1)[0]) for v in violations)
    orientation_tolerated = {
        v
        for v in violations
        if v.startswith("spoken_unsupported_entity") or is_register_violation(v)
    }
    keep_orientation = (
        required
        and len(original.split()) >= 6
        and _is_orientation_purpose(purpose, ev)
        and not hard
        and orientation_tolerated == set(violations)
    )
    if keep_orientation:
        return {
            "action": "allow",
            "text": original,
            "violations": violations,
            "kept_orientation": True,
            "script_hash": script_hash(original),
            "context_hash": context_hash(ev),
            "purpose": purpose,
        }
    if fallback and not fallback_errors:
        # Mid-sentence fragments are not listener-facing bridges (exec_13167:
        # fallback "alone does not settle…" → selected_continuity_broken).
        # Soften instead of hard-blocking (exec_13177: entity-stripped
        # "Performance …" → lowercase fragment thrash).
        fb = str(fallback or "").strip()
        if fb[:1].islower() or _MALFORMED_END.search(fb):
            softened = _soften_mid_sentence_fallback(fb)
            if softened and not spoken_copy_violations(
                softened, evidence=ev, seen_texts=seen_texts
            ):
                fallback = softened
            else:
                fallback_errors = ["spoken_mid_sentence_fallback"]
    if fallback and not fallback_errors:
        return {
            "action": "fallback",
            "text": fallback,
            "violations": violations,
            "script_hash": script_hash(fallback),
            "context_hash": context_hash(ev),
            "purpose": purpose,
        }
    return {
        "action": "block" if required else "omit",
        "text": "",
        "violations": [*violations, *fallback_errors],
        "script_hash": script_hash(""),
        "context_hash": context_hash(ev),
        "purpose": purpose,
    }


def assert_guarded_spoken_copy(
    text: str,
    *,
    evidence: dict[str, Any] | None = None,
    purpose: str,
    seen_texts: Iterable[str] | None = None,
    ctx: Any = None,
    exclude_line_id: str | None = None,
) -> dict[str, Any]:
    corpus: list[str] = []
    if seen_texts is not None:
        corpus.extend(str(x) for x in seen_texts if x)
    if ctx is not None:
        persisted = load_persisted_spoken_texts(
            ctx,
            exclude_line_id=exclude_line_id,
            exclude_text=text,
        )
        for item in persisted:
            if item and item not in corpus:
                corpus.append(item)
    decision = guard_spoken_copy(
        text,
        evidence=evidence,
        required=True,
        purpose=purpose,
        seen_texts=corpus or None,
    )
    if decision["action"] == "block":
        raise ValueError(
            f"{purpose} blocked by spoken_copy_guard: "
            + ", ".join(decision["violations"])
        )
    return decision


def artifact_spoken_copy_errors(
    *,
    gap_report: dict[str, Any] | None,
    transitions: dict[str, Any] | None,
    segments_by_id: dict[str, dict[str, Any]] | None = None,
    grounding_context: Any = None,
    synthetic_framing: dict[str, Any] | None = None,
    ctx: Any = None,
) -> list[str]:
    """Validate all persisted listener-facing copy with target-aware evidence."""
    errors: list[str] = []
    by_id = segments_by_id or {}
    seen: list[str] = []
    for row in ((gap_report or {}).get("interviewer_lines") or []):
        if not isinstance(row, dict) or row.get("skipped_optional") or row.get(
            "air_script_omit"
        ):
            continue
        target = str(row.get("targets_segment_id") or "")
        evidence = {
            **evidence_for_line(row),
            "target_excerpt": (by_id.get(target) or {}).get("text")
            or evidence_for_line(row).get("target_excerpt"),
            "grounding_context": grounding_context,
            "strict_grounding": bool(grounding_context or by_id.get(target)),
        }
        if ctx is not None:
            try:
                evidence = enrich_evidence_from_run(ctx, evidence)
            except Exception:
                pass
        violations = spoken_copy_violations(
            str(row.get("text") or ""), evidence=evidence, seen_texts=seen
        )
        if violations:
            errors.append(
                f"gap[{row.get('line_id') or target}]:" + ",".join(violations)
            )
        seen.append(str(row.get("text") or ""))
    for row in ((synthetic_framing or {}).get("lines") or []):
        if not isinstance(row, dict) or not str(row.get("text") or "").strip():
            continue
        evidence = {
            "before_excerpt": row.get("before_excerpt"),
            "after_excerpt": row.get("after_excerpt"),
            "target_excerpt": row.get("target_excerpt")
            or (by_id.get(str(row.get("anchor_segment_id") or "")) or {}).get("text"),
            "source_gap_ms": row.get("source_gap_ms"),
            "strict_grounding": True,
        }
        if ctx is not None:
            try:
                evidence = enrich_evidence_from_run(ctx, evidence)
            except Exception:
                pass
        violations = spoken_copy_violations(
            str(row.get("text") or ""), evidence=evidence, seen_texts=seen
        )
        if violations:
            errors.append(
                f"synthetic[{row.get('line_id') or row.get('anchor_segment_id')}]:"
                + ",".join(violations)
            )
        seen.append(str(row.get("text") or ""))
    syn_pair_text: dict[tuple[str, str], str] = {}
    syn_line_ids: dict[str, str] = {}
    for row in ((synthetic_framing or {}).get("lines") or []):
        if not isinstance(row, dict):
            continue
        txt = str(row.get("text") or "").strip()
        if not txt:
            continue
        lid = str(row.get("line_id") or "")
        if lid:
            syn_line_ids[lid] = txt
        sa = str(row.get("after_segment_id") or "")
        sb = str(row.get("before_segment_id") or "")
        if sa and sb:
            syn_pair_text[(sa, sb)] = txt
    for row in ((transitions or {}).get("transitions") or []):
        if not isinstance(row, dict) or not str(row.get("text") or "").strip():
            continue
        a = str(row.get("after_segment_id") or "")
        b = str(row.get("before_segment_id") or "")
        if a and a == b:
            errors.append(f"transition[{a}->{b}]:spoken_self_loop_seam")
            continue
        text = str(row.get("text") or "")
        # Same seam materialized from synthetic plan is one air owner, not a dup.
        plan_lid = str(row.get("synthetic_plan_line_id") or "")
        same_seam_echo = False
        if plan_lid and syn_line_ids.get(plan_lid, "").casefold() == text.strip().casefold():
            same_seam_echo = True
        elif (a, b) in syn_pair_text and syn_pair_text[(a, b)].casefold() == text.strip().casefold():
            same_seam_echo = True
        evidence = {
            "before_excerpt": (by_id.get(a) or {}).get("text"),
            "after_excerpt": (by_id.get(b) or {}).get("text"),
            "before_topic": (by_id.get(a) or {}).get("topic"),
            "after_topic": (by_id.get(b) or {}).get("topic"),
            "source_gap_ms": row.get("source_gap_ms"),
            "strict_grounding": True,
        }
        if ctx is not None:
            try:
                evidence = enrich_evidence_from_run(ctx, evidence)
            except Exception:
                pass
        seen_for_row = (
            [s for s in seen if s.strip().casefold() != text.strip().casefold()]
            if same_seam_echo
            else seen
        )
        violations = spoken_copy_violations(
            text, evidence=evidence, seen_texts=seen_for_row
        )
        if violations:
            errors.append(f"transition[{a}->{b}]:" + ",".join(violations))
        if not same_seam_echo:
            seen.append(text)
    return errors
