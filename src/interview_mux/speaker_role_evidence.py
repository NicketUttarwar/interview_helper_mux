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

    return {
        "role_evidence_hints": hints,
        "question_turns": question_turns[:12],
        "sample_turn_counts": turn_counts,
        "diarized_speaker_ids": speaker_ids,
    }
