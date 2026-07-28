"""Listen-and-answer data architecture for audio probes.

Certified path (v1): clip → local MLX STT (listen) → contract answer text.

Warm-up TTS of the system prompt remains optional context for a future
end-to-end audio L&A model; STT-listen does not require it.

Evidence bus
------------
clip_wav
  → tools/s2s_interrogate.py mode=classify (speech venv)
  → {stt_text, words[], model_id, source: stt_listen}
  → answer_from_listen_evidence(probe_id, evidence, flow?)
  → parse_by_contract → golden facts
"""

from __future__ import annotations

from typing import Any

from interview_mux.audio_probe_heuristics import heuristic_answer


def listen_flow_from_evidence(
    evidence: dict[str, Any],
    *,
    speaker_id: str | None = None,
    start_ms: int = 0,
    end_ms: int | None = None,
) -> dict[str, Any]:
    """Build a synthetic speaker-flow dict from STT listen evidence."""
    words_in = evidence.get("words") if isinstance(evidence.get("words"), list) else []
    words: list[dict[str, Any]] = []
    for w in words_in:
        if not isinstance(w, dict):
            continue
        token = str(w.get("text") or "").strip()
        if not token:
            continue
        try:
            ws = int(w.get("start_ms") if w.get("start_ms") is not None else start_ms)
            we = int(w.get("end_ms") if w.get("end_ms") is not None else ws)
        except (TypeError, ValueError):
            ws, we = start_ms, start_ms
        words.append(
            {
                "text": token,
                "start_ms": start_ms + max(0, ws),
                "end_ms": start_ms + max(0, we),
                "speaker_id": speaker_id or w.get("speaker_id") or "spk_listen",
                "confidence": w.get("confidence"),
            }
        )
    text = str(evidence.get("stt_text") or evidence.get("text") or "").strip()
    if not text and words:
        text = " ".join(str(w["text"]) for w in words)
    if end_ms is None:
        end_ms = int(words[-1]["end_ms"]) if words else start_ms
    confs = []
    for w in words:
        try:
            if w.get("confidence") is not None:
                confs.append(float(w["confidence"]))
        except (TypeError, ValueError):
            pass
    mean_c = sum(confs) / len(confs) if confs else None
    return {
        "speaker_flow_id": "listen_clip",
        "speaker_id": speaker_id or "spk_listen",
        "start_ms": start_ms,
        "end_ms": end_ms,
        "duration_ms": max(0, int(end_ms) - int(start_ms)),
        "text": text,
        "words": words,
        "mean_confidence": mean_c,
        "source": "stt_listen",
    }


def fuse_flows(primary: dict[str, Any], listen: dict[str, Any]) -> dict[str, Any]:
    """Prefer listen transcript for vernacular signals; keep original timing/ids."""
    out = dict(primary)
    listen_text = str(listen.get("text") or "").strip()
    primary_text = str(primary.get("text") or "").strip()
    # Prefer listen text when it has non-ASCII or is longer with low primary confidence
    prefer_listen = False
    if listen_text:
        if any(ord(c) > 127 for c in listen_text):
            prefer_listen = True
        elif not primary_text:
            prefer_listen = True
        elif len(listen_text) >= max(8, int(len(primary_text) * 0.6)):
            # Clip re-STT often recovers mid-flow vernacular missed by English-biased pass
            prefer_listen = True
    if prefer_listen:
        out["text"] = listen_text
        out["words"] = list(listen.get("words") or primary.get("words") or [])
        if listen.get("mean_confidence") is not None:
            out["mean_confidence"] = listen.get("mean_confidence")
        out["listen_fused"] = True
        out["listen_text"] = listen_text
        out["primary_text"] = primary_text
    else:
        out["listen_fused"] = False
        out["listen_text"] = listen_text
    return out


def answer_from_listen_evidence(
    probe_id: str,
    evidence: dict[str, Any],
    flow: dict[str, Any] | None = None,
    *,
    low_conf: float = 0.85,
) -> dict[str, Any]:
    """Produce a contract-shaped answer from STT listen evidence (+ optional flow)."""
    start_ms = int((flow or {}).get("start_ms") or 0)
    end_ms = int((flow or {}).get("end_ms") or start_ms)
    listen_flow = listen_flow_from_evidence(
        evidence,
        speaker_id=str((flow or {}).get("speaker_id") or "spk_listen"),
        start_ms=start_ms,
        end_ms=end_ms,
    )
    if flow:
        target = fuse_flows(flow, listen_flow)
    else:
        target = listen_flow
    ans = heuristic_answer(probe_id, target, low_conf=low_conf)
    return {
        "text": str(ans.get("text") or "NO"),
        "source": "stt_listen",
        "confidence": min(0.85, float(ans.get("confidence") or 0.5) + 0.15),
        "listen_fused": bool(target.get("listen_fused")),
        "stt_text": str(evidence.get("stt_text") or evidence.get("text") or ""),
        "model_id": evidence.get("model_id"),
        "heuristic_base_source": ans.get("source"),
    }
