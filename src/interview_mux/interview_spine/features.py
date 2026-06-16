from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from interview_mux.audio_energy import energy_windows_from_path


def enrich_window_features(
    windows: list[dict[str, Any]],
    *,
    wav_path: Path,
    words: list[dict[str, Any]],
    prosody_enabled: bool = False,
) -> list[dict[str, Any]]:
    packed = energy_windows_from_path(wav_path)
    sorted_words = sorted(words, key=lambda w: float(w.get("start_ms", 0)))

    for win in windows:
        start_ms = int(win["start_ms"])
        end_ms = int(win["end_ms"])
        span_words = win.pop("_words", [])
        if not span_words:
            span_words = [
                w
                for w in sorted_words
                if int(w.get("start_ms", 0)) >= start_ms - 50 and int(w.get("end_ms", 0)) <= end_ms + 50
            ]

        pause_before = 0.0
        if span_words and sorted_words:
            first = span_words[0]
            idx = next((i for i, w in enumerate(sorted_words) if w is first), None)
            if idx is not None and idx > 0:
                pause_before = max(
                    0.0,
                    float(first.get("start_ms", 0)) - float(sorted_words[idx - 1].get("end_ms", 0)),
                )

        speech_ms = sum(
            max(0.0, float(w.get("end_ms", 0)) - float(w.get("start_ms", 0))) for w in span_words
        )
        word_count = len(span_words)
        wpm = round((word_count / max(speech_ms / 60000.0, 1e-6)), 1) if word_count else 0.0

        rms_p50 = 0.0
        if packed is not None:
            rms, times_ms, _peak = packed
            mask = (times_ms >= start_ms) & (times_ms <= end_ms)
            if np.any(mask):
                rms_p50 = float(np.percentile(rms[mask], 50))

        f0_median: float | None = None
        if prosody_enabled and wav_path.is_file():
            f0_median = _estimate_f0_median_hz(wav_path, start_ms, end_ms)

        win["features"] = {
            "rms_p50": round(rms_p50, 6),
            "pause_before_ms": round(pause_before, 1),
            "speaking_rate_wpm": wpm,
            "f0_median_hz": round(f0_median, 1) if f0_median is not None else None,
        }
    return windows


def _estimate_f0_median_hz(wav_path: Path, start_ms: int, end_ms: int) -> float | None:
    try:
        import librosa
        import soundfile as sf
    except ImportError:
        return None
    audio, sr = sf.read(str(wav_path), always_2d=True)
    mono = audio.mean(axis=1)
    s0 = max(0, int(start_ms * sr / 1000))
    s1 = min(len(mono), int(end_ms * sr / 1000))
    if s1 - s0 < sr // 10:
        return None
    chunk = mono[s0:s1]
    f0, voiced_flag, _ = librosa.pyin(
        chunk,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
        sr=sr,
    )
    voiced = f0[voiced_flag] if voiced_flag is not None else f0[~np.isnan(f0)]
    voiced = voiced[~np.isnan(voiced)] if voiced.size else np.array([])
    if voiced.size == 0:
        return None
    return float(np.median(voiced))


def build_speaker_stats(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_speaker: dict[str, list[dict[str, Any]]] = {}
    for win in windows:
        sid = win.get("speaker_id")
        if not sid:
            continue
        by_speaker.setdefault(str(sid), []).append(win)

    stats: list[dict[str, Any]] = []
    for speaker_id, rows in sorted(by_speaker.items()):
        wpms = [float(r.get("features", {}).get("speaking_rate_wpm") or 0) for r in rows]
        avg_wpm = round(sum(wpms) / len(wpms), 1) if wpms else 0.0
        f0s = [
            float(r["features"]["f0_median_hz"])
            for r in rows
            if r.get("features", {}).get("f0_median_hz") is not None
        ]
        register_hint = _register_hint(f0s, avg_wpm)
        stats.append(
            {
                "speaker_id": speaker_id,
                "turn_count": len(rows),
                "avg_wpm": avg_wpm,
                "register_hint": register_hint,
            }
        )
    return stats


def _register_hint(f0s: list[float], avg_wpm: float) -> str:
    if not f0s:
        return "neutral_conversational"
    med = float(np.median(f0s))
    if med < 120:
        base = "low_register"
    elif med > 220:
        base = "high_register"
    else:
        base = "mid_register"
    if avg_wpm >= 160:
        return f"{base}_fast"
    if avg_wpm <= 100:
        return f"{base}_slow"
    return base
