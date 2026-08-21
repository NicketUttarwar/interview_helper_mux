"""Deterministic speaker role hints from diarized transcript samples."""

from __future__ import annotations

import re
from typing import Any

_QUESTION_RE = re.compile(r"\?\s*$")
_INTERVIEWER_CUES = (
    "tell me",
    "can you",
    "what was",
    "how did",
    "why did",
    "walk me through",
    "describe",
)


def _sample_lines(samples: Any) -> list[tuple[str | None, str]]:
    lines: list[tuple[str | None, str]] = []
    if isinstance(samples, str):
        for raw in samples.splitlines():
            text = raw.strip()
            if text:
                lines.append((None, text))
        return lines
    if isinstance(samples, list):
        for item in samples:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    lines.append((None, text))
            elif isinstance(item, dict):
                speaker = str(item.get("speaker_id") or item.get("speaker") or "") or None
                text = str(item.get("text") or item.get("content") or "").strip()
                if text:
                    lines.append((speaker, text))
    return lines


def build_speaker_role_evidence(stage_input: dict[str, Any]) -> dict[str, Any]:
    """
    Extract lightweight Q&A / turn-taking hints to help speaker_roles LLM passes.
    Does not assign roles — only surfaces observable patterns.
    """
    speakers_raw = stage_input.get("speakers")
    speaker_ids: list[str] = []
    if isinstance(speakers_raw, dict):
        for row in speakers_raw.get("speakers") or speakers_raw.get("items") or []:
            if isinstance(row, dict) and row.get("speaker_id"):
                speaker_ids.append(str(row["speaker_id"]))
    elif isinstance(speakers_raw, list):
        for row in speakers_raw:
            if isinstance(row, dict) and row.get("speaker_id"):
                speaker_ids.append(str(row["speaker_id"]))

    lines = _sample_lines(stage_input.get("transcript_samples"))
    question_turns: list[dict[str, Any]] = []
    turn_counts: dict[str, int] = {}
    for speaker, text in lines:
        sid = speaker or "unknown"
        turn_counts[sid] = turn_counts.get(sid, 0) + 1
        lower = text.lower()
        is_question = bool(_QUESTION_RE.search(text)) or any(cue in lower for cue in _INTERVIEWER_CUES)
        if is_question:
            question_turns.append({"speaker_id": speaker, "text_excerpt": text[:160]})

    hints: list[str] = []
    if question_turns:
        q_speakers = {str(q.get("speaker_id")) for q in question_turns if q.get("speaker_id")}
        if len(q_speakers) == 1:
            hints.append(
                f"Speaker {next(iter(q_speakers))} asks most interview-style questions — likely interviewer."
            )
        elif len(q_speakers) > 1:
            hints.append(f"Multiple speakers ask questions: {', '.join(sorted(q_speakers))}.")
    if speaker_ids and turn_counts:
        ranked = sorted(turn_counts.items(), key=lambda x: x[1], reverse=True)
        if len(ranked) >= 2 and ranked[0][1] > ranked[1][1] * 1.5:
            hints.append(
                f"Speaker {ranked[0][0]} has the highest talk time in samples ({ranked[0][1]} turns)."
            )

    pair_verdicts = _pair_verdicts(stage_input.get("diarization_repairs"))
    if pair_verdicts:
        same = [p for p in pair_verdicts if p.get("same_speaker") is True]
        different = [p for p in pair_verdicts if p.get("same_speaker") is False]
        if same:
            hints.append(
                f"{len(same)} Sortformer pair(s) judged the same speaker across a flip seam."
            )
        if different:
            hints.append(
                f"{len(different)} Sortformer pair(s) judged different speakers across a flip seam."
            )

    return {
        "role_evidence_hints": hints,
        "question_turns": question_turns[:12],
        "sample_turn_counts": turn_counts,
        "diarized_speaker_ids": speaker_ids,
        "diarization_pair_verdicts": pair_verdicts,
    }


def _pair_verdicts(repairs: Any) -> list[dict[str, Any]]:
    if not isinstance(repairs, dict):
        return []
    out: list[dict[str, Any]] = []
    for row in repairs.get("pairs") or []:
        if not isinstance(row, dict):
            continue
        verdict = str(row.get("verdict") or "").strip().lower()
        same: bool | None
        if verdict in {"yes_same", "yes"}:
            same = True
        elif verdict in {"no_different", "no"}:
            same = False
        else:
            same = None
        out.append(
            {
                "from_speaker_id": str(row.get("from_speaker_id") or ""),
                "to_speaker_id": str(row.get("to_speaker_id") or ""),
                "verdict": verdict,
                "same_speaker": same,
            }
        )
    return out[:40]


def _word_count(text: str) -> int:
    return len([w for w in str(text or "").split() if w])


def _is_guest_explanation(text: str) -> bool:
    if _word_count(text) < 40:
        return False
    if "?" in text:
        return False
    lower = text.lower()
    return not any(cue in lower for cue in _INTERVIEWER_CUES)


def _is_host_question(text: str) -> bool:
    if _word_count(text) > 25:
        return False
    lower = text.lower()
    return bool(_QUESTION_RE.search(text.strip())) or any(cue in lower for cue in _INTERVIEWER_CUES)


def lint_role_tape_conflicts(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """Detect interviewer_question / interviewee_answer labels that contradict tape."""
    segs = (manifest or {}).get("segments") if isinstance(manifest, dict) else None
    if not isinstance(segs, list):
        return {"blocking": False, "conflict_count": 0, "typed_qa_count": 0, "examples": []}
    typed = 0
    conflicts: list[dict[str, Any]] = []
    for row in segs:
        if not isinstance(row, dict):
            continue
        stype = str(row.get("type") or "").strip()
        text = str(row.get("text") or "")
        if stype not in {"interviewer_question", "interviewee_answer"}:
            continue
        typed += 1
        sid = str(row.get("segment_id") or "")
        if stype == "interviewer_question" and _is_guest_explanation(text):
            conflicts.append(
                {
                    "segment_id": sid,
                    "type": stype,
                    "reason": "long_explanation_labeled_question",
                }
            )
        elif stype == "interviewee_answer" and _is_host_question(text):
            conflicts.append(
                {
                    "segment_id": sid,
                    "type": stype,
                    "reason": "short_question_labeled_answer",
                }
            )
    conflict_count = len(conflicts)
    ratio = (conflict_count / typed) if typed else 0.0
    blocking = conflict_count >= 4 and ratio >= 0.15
    return {
        "blocking": blocking,
        "conflict_count": conflict_count,
        "typed_qa_count": typed,
        "conflict_ratio": round(ratio, 4),
        "examples": conflicts[:8],
    }


def stamp_role_tape_conflict(ctx: Any, lint: dict[str, Any]) -> None:
    if not ctx.artifact_exists("understanding/speakers.json"):
        return
    try:
        doc = ctx.read_json("understanding/speakers.json")
    except Exception:
        return
    if not isinstance(doc, dict):
        return
    doc["role_tape_conflict"] = lint
    ctx.write_json("understanding/speakers.json", doc, skip_handoff=True)
