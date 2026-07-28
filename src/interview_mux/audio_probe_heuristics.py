"""Fail-open heuristic answers when MLX interrogate is unavailable."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.audio_probe_flows import flow_signals

_QUESTION = re.compile(r"\?|^(who|what|when|where|why|how|do|does|did|is|are|can|could|would)\b", re.I)


def heuristic_answer(probe_id: str, flow: dict[str, Any], *, low_conf: float = 0.85) -> dict[str, Any]:
    """Return a parseable response string + metadata for a probe."""
    sig = flow_signals(flow, low_conf=low_conf)
    text = str(flow.get("text") or "")
    start = int(flow.get("start_ms") or 0)
    end = int(flow.get("end_ms") or start)
    dur = max(1, end - start)

    if probe_id == "vprobe.multilingual_or_uncommon":
        yes = bool(sig["non_ascii"] or sig["uncommon_ratio"] >= 0.2 or (sig["brick_count"] >= 2 and not sig["one_off_miscomprehension"]))
        return {"text": "YES" if yes else "NO", "source": "heuristic", "confidence": 0.55 if yes else 0.6}

    if probe_id == "vprobe.non_english_speech":
        return {"text": "YES" if sig["non_ascii"] else "NO", "source": "heuristic", "confidence": 0.7}

    if probe_id == "vprobe.uncommon_english":
        yes = (not sig["non_ascii"]) and sig["uncommon_ratio"] >= 0.25
        return {"text": "YES" if yes else "NO", "source": "heuristic", "confidence": 0.5}

    if probe_id == "vprobe.extract_keywords":
        toks = [t.strip(".,!?;:\"'") for t in text.split()]
        special: list[str] = []
        for t in toks:
            if not t:
                continue
            if re.search(r"[^\x00-\x7f]", t) or (t.isalpha() and len(t) > 4 and t.lower() not in {"about", "really", "something", "because"}):
                if re.search(r"[^\x00-\x7f]", t) or sig["uncommon_ratio"] >= 0.2:
                    special.append(t)
            if len(special) >= 5:
                break
        if not special and sig["non_ascii"]:
            special = [t for t in toks if re.search(r"[^\x00-\x7f]", t)][:5]
        body = ", ".join(special) if special else "none"
        return {"text": f"KEYWORDS: {body}", "source": "heuristic", "confidence": 0.45}

    if probe_id == "vprobe.span_hint":
        # Heuristic: mark middle third of low-confidence / non-ascii island as special
        words = [w for w in (flow.get("words") or []) if isinstance(w, dict)]
        island: list[dict[str, Any]] = []
        for w in words:
            wt = str(w.get("text") or "")
            try:
                c = float(w.get("confidence")) if w.get("confidence") is not None else 1.0
            except (TypeError, ValueError):
                c = 1.0
            if re.search(r"[^\x00-\x7f]", wt) or c < low_conf:
                island.append(w)
        if island:
            a = int(island[0].get("start_ms") or start) - start
            b = int(island[-1].get("end_ms") or end) - start
        else:
            a = int(dur * 0.25)
            b = int(dur * 0.75)
        a = max(0, a)
        b = max(a + 200, min(dur, b))

        def fmt(ms: int) -> str:
            s = ms // 1000
            return f"{s // 60:02d}:{s % 60:02d}"

        return {
            "text": f"SPANS: {fmt(a)}-{fmt(b)}",
            "source": "heuristic",
            "confidence": 0.4,
        }

    if probe_id == "vprobe.passion_or_emphasis":
        sp = float(sig.get("stress_proxy") or 0)
        level = "high" if sp >= 0.45 else ("mid" if sp >= 0.25 else "low")
        return {"text": f"LEVEL: {level}", "source": "heuristic", "confidence": 0.4}

    if probe_id == "vprobe.pull_quote":
        yes = float(sig.get("stress_proxy") or 0) >= 0.35 and len(text.split()) >= 6
        return {"text": "YES" if yes else "NO", "source": "heuristic", "confidence": 0.35}

    if probe_id == "vprobe.speech_act":
        if _QUESTION.search(text.strip()):
            act = "question"
        elif len(text.split()) <= 4:
            act = "aside"
        else:
            act = "answer"
        return {"text": f"ACT: {act}", "source": "heuristic", "confidence": 0.45}

    if probe_id == "vprobe.crosstalk":
        # Without diarization overlap signal, use very low confidence dense bricks
        yes = sig["brick_count"] >= 4 and float(sig.get("stress_proxy") or 0) >= 0.4
        return {"text": "YES" if yes else "NO", "source": "heuristic", "confidence": 0.3}

    if probe_id == "vprobe.non_speech_bleed":
        return {"text": "NO", "source": "heuristic", "confidence": 0.3}

    if probe_id == "vprobe.unintelligible":
        yes = (flow.get("mean_confidence") is not None and float(flow["mean_confidence"]) < 0.55) or sig["brick_count"] >= 5
        return {"text": "YES" if yes else "NO", "source": "heuristic", "confidence": 0.5}

    if probe_id == "vprobe.affect_burst":
        yes = float(sig.get("stress_proxy") or 0) >= 0.5
        return {"text": "YES" if yes else "NO", "source": "heuristic", "confidence": 0.35}

    if probe_id == "vprobe.name_or_title":
        caps = [t.strip(".,") for t in text.split() if t[:1].isupper() and t.lower() not in {"i", "i'm"}]
        body = ", ".join(caps[:5]) if caps else "none"
        return {"text": f"KEYWORDS: {body}", "source": "heuristic", "confidence": 0.35}

    if probe_id == "vprobe.sensitive_disclosure":
        keys = ("diagnosed", "abuse", "suicide", "password", "ssn", "credit card")
        yes = any(k in text.lower() for k in keys)
        return {"text": "YES" if yes else "NO", "source": "heuristic", "confidence": 0.4}

    if probe_id == "vprobe.disagreement":
        keys = ("disagree", "wrong", "no way", "that's not", "i don't think")
        yes = any(k in text.lower() for k in keys)
        return {"text": "YES" if yes else "NO", "source": "heuristic", "confidence": 0.4}

    if probe_id == "vprobe.nonliteral":
        keys = ("just kidding", "sarcasm", "metaphorically", "lol", "haha")
        yes = any(k in text.lower() for k in keys)
        return {"text": "YES" if yes else "NO", "source": "heuristic", "confidence": 0.35}

    if probe_id == "vprobe.acoustic_discontinuity":
        return {"text": "NO", "source": "heuristic", "confidence": 0.3}

    if probe_id == "vprobe.retelling":
        return {"text": "NO", "source": "heuristic", "confidence": 0.3}

    if probe_id == "vprobe.payoff_moment":
        keys = ("that's when", "in the end", "finally", "the point is", "what matters")
        yes = any(k in text.lower() for k in keys) or float(sig.get("stress_proxy") or 0) >= 0.45
        return {"text": "YES" if yes else "NO", "source": "heuristic", "confidence": 0.35}

    return {"text": "NO", "source": "heuristic", "confidence": 0.2}
