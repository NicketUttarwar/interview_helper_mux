"""Shared transcript artifact normalization (AWS + local STT)."""

from __future__ import annotations

from typing import Any


def normalize_aws_transcript(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    results = raw.get("results") or {}
    items = results.get("items") or []
    segments = (results.get("speaker_labels") or {}).get("segments") or []
    words: list[dict[str, Any]] = []
    for item in items:
        if item.get("type") != "pronunciation":
            continue
        start = float(item.get("start_time", 0))
        end = float(item.get("end_time", start))
        alt = (item.get("alternatives") or [{}])[0]
        conf_raw = alt.get("confidence")
        confidence = float(conf_raw) if conf_raw is not None else None
        words.append(
            {
                "text": alt.get("content", ""),
                "start_ms": int(start * 1000),
                "end_ms": int(end * 1000),
                "speaker_id": item.get("speaker_label"),
                "confidence": confidence,
            }
        )
    speaker_ids = sorted({w["speaker_id"] for w in words if w.get("speaker_id")})
    speakers = {
        "speakers": [{"id": sid, "role": "unknown"} for sid in speaker_ids],
    }
    full_text = (results.get("transcripts") or [{}])[0].get("transcript", "")
    return {
        "text": full_text,
        "words": words,
        "segments": segments,
    }, speakers


def _infer_turn_speakers(words: list[dict[str, Any]], *, gap_ms: int = 700) -> None:
    """When STT returns one speaker, alternate spk_0/spk_1 on interview-style pauses."""
    if len(words) < 2:
        return
    ids = {w.get("speaker_id") for w in words if w.get("speaker_id")}
    if len(ids) != 1:
        return
    current = "spk_0"
    words[0]["speaker_id"] = current
    for i in range(1, len(words)):
        prev = words[i - 1]
        gap = int(words[i].get("start_ms") or 0) - int(prev.get("end_ms") or prev.get("start_ms") or 0)
        if gap >= gap_ms:
            current = "spk_1" if current == "spk_0" else "spk_0"
        words[i]["speaker_id"] = current


def normalize_local_stt(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize mlx-audio STT tool JSON into transcript/full + speakers contract."""
    words = list(raw.get("words") or [])
    segments = list(raw.get("segments") or [])
    full_text = str(raw.get("text") or "").strip()
    if not full_text and words:
        full_text = " ".join(str(w.get("text") or "") for w in words).strip()
    speaker_ids = sorted({w.get("speaker_id") for w in words if w.get("speaker_id")})
    if not speaker_ids:
        speaker_ids = ["spk_0"]
        for w in words:
            if not w.get("speaker_id"):
                w["speaker_id"] = "spk_0"
    _infer_turn_speakers(words)
    speaker_ids = sorted({w.get("speaker_id") for w in words if w.get("speaker_id")})
    if not speaker_ids:
        speaker_ids = ["spk_0"]
    for w in words:
        if not w.get("speaker_id"):
            w["speaker_id"] = speaker_ids[0]
    speakers = {
        "speakers": [{"id": sid, "role": "unknown"} for sid in speaker_ids if sid],
    }
    return {
        "text": full_text,
        "words": words,
        "segments": segments,
    }, speakers
