"""Reject spoken show-scaffolding in synthetic VO/transition text.

Chapters/acts live in business logic only. Spoken lines must not say
\"Chapter Four\", \"Act 2\", \"in today's episode\", etc.
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
_THIS_CHAPTER = re.compile(
    r"\b(?:"
    r"(?:this|our)\s+chapter|"
    r"in\s+(?:this|the|our)\s+chapter|"
    r"previous\s+chapter\s+(?:we|of\s+the\s+(?:show|podcast|episode))"
    r")\b",
    re.IGNORECASE,
)
_SCAFFOLD = re.compile(
    r"\b(?:"
    r"welcome\s+back|"
    r"in\s+today'?s\s+episode|"
    r"on\s+(?:today'?s|this)\s+(?:show|podcast|episode)|"
    r"as\s+we\s+(?:discussed|talked\s+about)\s+earlier|"
    r"coming\s+up\s+(?:next|on\s+the\s+show)|"
    r"stay\s+tuned|"
    r"don'?t\s+forget\s+to\s+subscribe"
    r")\b",
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


def spoken_structure_hits(text: str, *, allow_scaffold: bool = False) -> list[str]:
    """Return list of rule ids that fire on *text*."""
    t = str(text or "").strip()
    if not t:
        return []
    hits: list[str] = []
    if _CHAPTER_NUM.search(t):
        hits.append("spoken_chapter_or_act_number")
    if _THIS_CHAPTER.search(t):
        hits.append("spoken_chapter_meta")
    if not allow_scaffold and _SCAFFOLD.search(t):
        hits.append("spoken_show_scaffold")
    if _EDITORIAL_QC.search(t):
        hits.append("spoken_editorial_qc_prose")
    return hits


def is_editorial_qc_prose(text: str) -> bool:
    """True when text looks like gap-eval diagnostics rather than on-air VO."""
    return "spoken_editorial_qc_prose" in spoken_structure_hits(text)


def lint_spoken_text(
    text: str,
    *,
    allow_scaffold: bool = False,
    label: str = "text",
) -> list[str]:
    hits = spoken_structure_hits(text, allow_scaffold=allow_scaffold)
    return [f"{label}: forbidden spoken scaffolding ({h})" for h in hits]


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
