"""Reject spoken show-scaffolding and edit-structure language in synthetic VO.

Chapters, clips, segments, acts, and other master-construction labels live in
business logic only. Listener-facing lines must convey grounded contextual
facts and a layup into the next native thought — never metadata or structure.
"""

from __future__ import annotations

import re
from typing import Any

# Chapter / act / part ordinals and meta labels
_CHAPTER_NUM = re.compile(
    r"\b(?:"
    r"chapter|act|part|section|episode\s+part"
    r")\s*"
    r"(?:"
    r"\d+|"
    r"[ivxlcdm]+|"
    r"one|two|three|four|five|six|seven|eight|nine|ten|"
    r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"eleven|twelve|thirteen|fourteen|fifteen"
    r")\b",
    re.IGNORECASE,
)
# Bare "chapter(s)" is never listener-facing — numbered or not.
_BARE_CHAPTER = re.compile(r"\bchapters?\b", re.IGNORECASE)
_THIS_CHAPTER = re.compile(
    r"\b(?:"
    r"(?:this|our|the)\s+chapter|"
    r"in\s+(?:this|the|our)\s+chapter|"
    r"previous\s+chapter\s+(?:we|of\s+the\s+(?:show|podcast|episode))"
    r")\b",
    re.IGNORECASE,
)
# Edit / construction units: previous clip, earlier segment, next cut, etc.
# Do not flag ordinary English such as "a segment of the market".
_EDIT_STRUCTURE_REF = re.compile(
    r"\b(?:"
    r"(?:previous|earlier|prior|last|next|upcoming|following|preceding)\s+"
    r"(?:clips?|segments?|chapters?|scenes?|cuts?|takes?|parts?|sections?|acts?)|"
    r"(?:this|that|our)\s+"
    r"(?:previous\s+|earlier\s+|prior\s+|last\s+|next\s+|upcoming\s+|following\s+)?"
    r"(?:clips?|segments?)|"
    r"(?:the)\s+"
    r"(?:previous\s+|earlier\s+|prior\s+|last\s+|next\s+|upcoming\s+|following\s+)"
    r"(?:clips?|segments?)|"
    r"(?:a|an|the|this|that|our)\s+clips?|"
    r"in\s+(?:this|the|our|that)\s+(?:clip|segment|chapter|scene|cut|part|section|act)|"
    r"(?:from|after|before|into|out\s+of)\s+(?:the\s+)?"
    r"(?:previous|earlier|prior|last|next|upcoming|following)\s+"
    r"(?:clip|segment|chapter|scene|cut|take|part)|"
    r"(?:as|like)\s+(?:in|with)\s+the\s+(?:previous|earlier|prior|last)\s+"
    r"(?:clip|segment|chapter)"
    r")\b",
    re.IGNORECASE,
)
_CONSTRUCTION_META = re.compile(
    r"\b(?:"
    r"edit\s+decision(?:\s+list)?|"
    r"master(?:ing)?\s+podcast|"
    r"construction\s+of\s+the\s+(?:master|episode|show)|"
    r"ordered\s+segment|"
    r"air(?:ing)?\s+order|"
    r"native\s+(?:segment|clip|take)|"
    r"synthetic\s+(?:vo|voice[- ]?over|line|bridge)|"
    r"voice[- ]?over\s+(?:line|bridge|script)|"
    r"gap\s+(?:report|framing|vo)|"
    r"nugget\s+lay[- ]?up|"
    r"selection\s+order|"
    r"pipeline(?:\s+stage)?|"
    r"stage_done|from_stage|until_stage|"
    r"artifact|schema\s+validation|"
    r"edl\b"
    r")\b",
    re.IGNORECASE,
)
_SCAFFOLD = re.compile(
    r"\b(?:"
    r"welcome\s+back|"
    r"in\s+today'?s\s+episode|"
    r"in\s+(?:this|the|our)\s+episode|"
    r"on\s+(?:today'?s|this|our)\s+(?:show|podcast|episode)|"
    r"as\s+(?:we|i)\s+(?:discussed|talked\s+about|mentioned|said|heard)\s+earlier|"
    r"as\s+mentioned\s+earlier|"
    r"coming\s+up(?:\s+(?:next|on\s+the\s+show))?|"
    r"after\s+the\s+break|"
    r"stay\s+tuned|"
    r"don'?t\s+forget\s+to\s+subscribe|"
    r"in\s+(?:this|the|our)\s+part\s+of\s+the\s+(?:show|podcast|episode)"
    r")\b",
    re.IGNORECASE,
)

# Internal edit identifiers are metadata, never listener-facing copy. The second
# pattern catches old deterministic fallbacks that stripped ``seg_`` but left the
# numeric suffix in phrases such as "what happens as we get to 153?"
_INTERNAL_ID = re.compile(
    r"\b(?:seg(?:ment)?|line|clip|turn)[\s_-]*\d+[a-z]?\b",
    re.IGNORECASE,
)
_DISGUISED_SEGMENT_ID = re.compile(
    r"\b(?:"
    r"what\s+happens\s+as\s+we\s+get\s+to|"
    r"what\s+led\s+into|"
    r"where\s+does|"
    r"how\s+does"
    r")\s+\d+[a-z]?\b|"
    r"\b(?:opens?\s+on|follow\s+from)\s+\d+[a-z]?\b|"
    r"\b\d+[a-z]?\s+(?:take\s+this|follow\s+from)\b",
    re.IGNORECASE,
)

# Gap-eval / QC prose that must never be spoken as interviewer VO.
_EDITORIAL_QC = re.compile(
    r"(?:"
    r"makes\s+no\s+sense|"
    r"without\s+the\s+(?:unheard|preceding)\s+prompt|"
    r"unheard\s+prompt|"
    r"listener\s+(?:lacks|never\s+hears|confusion)|"
    r"the\s+answer\s+references|"
    r"no\s+transcript|"
    r"\bunusable\b|"
    r"blank\s+answer|"
    r"thought\s+stops\s+mid[- ]sentence|"
    r"gap\s+type|"
    r"needs?\s+a\s+prompt|"
    r"quickly\s*[—\-–]\s+.+,?\s+then\s+continue"
    r")",
    re.IGNORECASE,
)

# Planner / analysis fields that leaked into air (first-time listener would not understand).
_PLANNER_META = re.compile(
    r"\b(?:"
    r"episode(?:'s|s)?\s+intended\s+scope|"
    r"intended\s+scope|"
    r"episode\s+scope|"
    r"native\s+continuation|"
    r"native\s+(?:segment|clip|beat|take)|"
    r"listener\s+need(?:\s+entering)?|"
    r"entering\s+T\b|"
    r"talking\s+points?|"
    r"vo\s+missions?|"
    r"coverage\s+of\s+(?:this|the|our)\s+(?:conversation|episode|show)|"
    r"must[- ]keep\s+talking\s+point|"
    r"handoff\s+need|"
    r"target\s+beat|"
    r"forward\s+unlock|"
    r"setup\s+from\s+nuggets|"
    r"nugget\s+(?:corpus|lay[- ]?up|id)|"
    r"ordered\s+segment"
    r")\b",
    re.IGNORECASE,
)
_SPEAKER_ROLE_LABEL = re.compile(
    r"\b(?:"
    r"the\s+host|"
    r"the\s+guest|"
    r"the\s+interviewer|"
    r"our\s+speaker|"
    r"on\s+the\s+show\s+today"
    r")\b",
    re.IGNORECASE,
)
_NAME_ATTRIBUTION_VERB = re.compile(
    r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?\s+"
    r"(?:explains?|says?|elaborates?|describes?|notes?|adds?|closes?|traces?|discusses?)\b",
)
_NAME_ATTRIBUTION_HEAR = re.compile(
    r"\blet(?:'|')?s\s+hear\s+[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?\b",
)
_GENDERED_PRONOUN = re.compile(
    r"\b(?:he|she|him|her)\b",
    re.IGNORECASE,
)


def spoken_structure_hits(text: str, *, allow_scaffold: bool = False) -> list[str]:
    """Return list of rule ids that fire on *text*."""
    t = str(text or "").strip()
    if not t:
        return []
    hits: list[str] = []
    if _CHAPTER_NUM.search(t) or _BARE_CHAPTER.search(t):
        hits.append("spoken_chapter_or_act_number")
    if _THIS_CHAPTER.search(t):
        hits.append("spoken_chapter_meta")
    if _EDIT_STRUCTURE_REF.search(t):
        hits.append("spoken_edit_structure_ref")
    if _CONSTRUCTION_META.search(t):
        hits.append("spoken_construction_meta")
    if not allow_scaffold and _SCAFFOLD.search(t):
        hits.append("spoken_show_scaffold")
    if _INTERNAL_ID.search(t) or _DISGUISED_SEGMENT_ID.search(t):
        hits.append("spoken_internal_identifier")
    if _EDITORIAL_QC.search(t):
        hits.append("spoken_editorial_qc_prose")
    if _PLANNER_META.search(t):
        hits.append("spoken_planner_meta")
    if _SPEAKER_ROLE_LABEL.search(t):
        hits.append("spoken_speaker_role_label")
    if _NAME_ATTRIBUTION_VERB.search(t) or _NAME_ATTRIBUTION_HEAR.search(t):
        hits.append("spoken_name_attribution")
    if _GENDERED_PRONOUN.search(t):
        hits.append("spoken_gendered_pronoun")
    return list(dict.fromkeys(hits))


def is_editorial_qc_prose(text: str) -> bool:
    """True when text looks like gap-eval diagnostics rather than on-air VO."""
    return "spoken_editorial_qc_prose" in spoken_structure_hits(text)


def is_hard_structure_violation(code: str) -> bool:
    """True when a spoken_copy / meta lint code must never be kept or spoken."""
    c = str(code or "")
    if c.startswith("spoken_repeated_"):
        return True
    return c in {
        "spoken_chapter_or_act_number",
        "spoken_chapter_meta",
        "spoken_edit_structure_ref",
        "spoken_construction_meta",
        "spoken_show_scaffold",
        "spoken_internal_identifier",
        "spoken_editorial_qc_prose",
        "spoken_planner_meta",
        "spoken_production_jargon",
        "spoken_path_or_filename",
        "spoken_placeholder",
        "spoken_stock_copy",
        "spoken_generic_filler",
    }


def lint_spoken_text(
    text: str,
    *,
    allow_scaffold: bool = False,
    label: str = "text",
) -> list[str]:
    hits = spoken_structure_hits(text, allow_scaffold=allow_scaffold)
    return [f"{label}: forbidden spoken scaffolding ({h})" for h in hits]


def rewrite_speaker_role_labels(text: str) -> str:
    """Replace on-air host/guest/speaker labels with topic-forward wording.

    exec_11630: ``The guest frames…`` failed post-commit as
    ``spoken_speaker_role_label`` while the rest of the preface was fine.
    """
    t = str(text or "").strip()
    if not t:
        return t
    # Order matters: longer phrases first.
    replacements = (
        (r"\bour\s+speaker\b", "this conversation"),
        (r"\bon\s+the\s+show\s+today\b", "in this conversation"),
        (r"\bthe\s+interviewer\b", "this conversation"),
        (r"\bthe\s+speaker\b", "this conversation"),
        (r"\bthe\s+guest\b", "this conversation"),
        (r"\bthe\s+host\b", "this conversation"),
    )
    out = t
    for pattern, repl in replacements:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    # Capitalize sentence start after rewrite when we lowercased mid-sentence leads.
    if out and out[0].islower() and (not t or t[0].isupper()):
        out = out[0].upper() + out[1:]
    return " ".join(out.split()).strip()


def lint_gap_report_lines(
    gap_report: dict[str, Any] | None,
    *,
    allow_scaffold: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(gap_report, dict):
        return errors
    for ln in gap_report.get("interviewer_lines") or []:
        if not isinstance(ln, dict):
            continue
        if ln.get("skipped_optional") or ln.get("omit"):
            continue
        lid = str(ln.get("line_id") or "line")
        errors.extend(
            lint_spoken_text(
                str(ln.get("text") or ""),
                allow_scaffold=allow_scaffold,
                label=f"gap_report[{lid}]",
            )
        )
    return errors


def lint_transitions_doc(
    transitions: dict[str, Any] | list[Any] | None,
    *,
    allow_scaffold: bool = False,
) -> list[str]:
    errors: list[str] = []
    rows: list[Any]
    if isinstance(transitions, dict):
        rows = list(transitions.get("transitions") or [])
    elif isinstance(transitions, list):
        rows = transitions
    else:
        return errors
    for i, tr in enumerate(rows):
        if not isinstance(tr, dict):
            continue
        label = (
            f"transition[{tr.get('after_segment_id')}->{tr.get('before_segment_id')}]"
            if tr.get("after_segment_id")
            else f"transition[{i}]"
        )
        errors.extend(
            lint_spoken_text(
                str(tr.get("text") or ""),
                allow_scaffold=allow_scaffold,
                label=label,
            )
        )
    return errors


def assert_speakable_or_raise(text: str, *, context: str = "synthetic_vo") -> None:
    errs = lint_spoken_text(text, label=context)
    if errs:
        raise ValueError("; ".join(errs))
