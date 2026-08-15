"""Envelope sidechain ducking for under-segment beds (mix house-chain step 6).

Applies base cue level elsewhere; this module applies time-varying attenuation
derived from a soft speech *gate* (present vs air), not syllable-amplitude
tracking. Fail-open callers keep static duck when the speech window is unusable.
"""

from __future__ import annotations

import array
import math
from typing import Any

import numpy as np
from pydub import AudioSegment

DEFAULT_ATTACK_MS = 40
DEFAULT_RELEASE_MS = 900
DEFAULT_HOP_MS = 20
_SILENCE_DBFS = -55.0
_FULL_SPEECH_DBFS = -22.0
# Gate opens once speech clears silence by this many dB (avoids syllable pumping).
_GATE_OPEN_ABOVE_SILENCE_DB = 8.0


def sidechain_duck_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    if cfg is None:
        import interview_mux.config as mux_config

        cfg = mux_config.merged_config()
    mix = dict(cfg.get("mix") or {})
    try:
        from interview_mux.production_profile import mix_rules

        mix.update(mix_rules())
    except Exception:
        pass
    raw = mix.get("sidechain_duck") if isinstance(mix.get("sidechain_duck"), dict) else {}
    pause = raw.get("pause_ride_db", mix.get("pause_ride_db", 1.0))
    return {
        "enabled": bool(raw.get("enabled", True)),
        "attack_ms": int(raw.get("attack_ms", DEFAULT_ATTACK_MS)),
        "release_ms": int(raw.get("release_ms", DEFAULT_RELEASE_MS)),
        "hop_ms": int(raw.get("hop_ms", DEFAULT_HOP_MS)),
        # Raise underscore in intentional air / post-VO gaps (music-only pause-ride).
        # Keep modest so beds do not surge over adjacent native/synthetic speech.
        "pause_ride_db": float(pause),
    }


def speech_window_usable(speech_window: AudioSegment | None) -> bool:
    if speech_window is None or len(speech_window) <= 0:
        return False
    try:
        return int(speech_window.rms) > 0
    except Exception:
        return False


def _hop_rms_db(speech: AudioSegment, hop_ms: int) -> list[float]:
    hop = max(1, int(hop_ms))
    out: list[float] = []
    for start in range(0, max(1, len(speech)), hop):
        chunk = speech[start : start + hop]
        if len(chunk) <= 0 or chunk.rms <= 0:
            out.append(-120.0)
            continue
        try:
            out.append(float(chunk.dBFS))
        except Exception:
            out.append(-120.0)
    return out if out else [-120.0]


def _gate_from_db(db: float, *, silence_db: float, open_db: float) -> float:
    """Binary soft gate: 1.0 when speech is present, 0.0 in air."""
    if db <= silence_db:
        return 0.0
    if db >= open_db:
        return 1.0
    # Narrow transition band only — not continuous loudness tracking.
    span = max(1e-6, open_db - silence_db)
    return max(0.0, min(1.0, (db - silence_db) / span))


def _follow_envelope(
    amounts: list[float],
    *,
    hop_ms: int,
    attack_ms: float,
    release_ms: float,
) -> list[float]:
    hop = max(1.0, float(hop_ms))
    attack = max(hop, float(attack_ms))
    release = max(hop, float(release_ms))
    attack_coeff = 1.0 - math.exp(-hop / attack)
    release_coeff = 1.0 - math.exp(-hop / release)
    env = 0.0
    out: list[float] = []
    for target in amounts:
        if target > env:
            # Speech rising → duck deeper (attack)
            env += (target - env) * attack_coeff
        else:
            # Speech falling → recover toward base (release)
            env += (target - env) * release_coeff
        out.append(max(0.0, min(1.0, env)))
    return out


def _apply_gain_envelope(bed: AudioSegment, gain_db_per_hop: list[float], hop_ms: int) -> AudioSegment:
    if not gain_db_per_hop:
        return bed
    samples = np.array(bed.get_array_of_samples(), dtype=np.float64)
    channels = max(1, int(bed.channels))
    if channels > 1:
        samples = samples.reshape((-1, channels))
    frame_rate = int(bed.frame_rate) or 48_000
    hop_frames = max(1, int(round(frame_rate * hop_ms / 1000.0)))
    n_frames = samples.shape[0] if samples.ndim == 2 else len(samples)

    hop_gains = np.array([10.0 ** (g / 20.0) for g in gain_db_per_hop], dtype=np.float64)
    frame_idx = np.arange(n_frames, dtype=np.float64)
    hop_pos = frame_idx / float(hop_frames)
    hop_pos = np.clip(hop_pos, 0.0, max(0.0, len(hop_gains) - 1.000001))
    lo = np.floor(hop_pos).astype(np.int64)
    hi = np.minimum(lo + 1, len(hop_gains) - 1)
    frac = hop_pos - lo
    frame_gain = hop_gains[lo] * (1.0 - frac) + hop_gains[hi] * frac

    if samples.ndim == 2:
        shaped = samples * frame_gain[:, None]
        flat = shaped.reshape(-1)
    else:
        flat = samples * frame_gain

    max_amp = float(1 << (8 * bed.sample_width - 1)) - 1.0
    dtype = np.int16 if bed.sample_width == 2 else np.int32
    clipped = np.clip(np.rint(flat), -max_amp, max_amp).astype(dtype, copy=False)
    out_samples = array.array(bed.array_type)
    out_samples.frombytes(clipped.tobytes())
    return bed._spawn(out_samples)


def envelope_duck(
    bed: AudioSegment,
    speech_window: AudioSegment,
    *,
    depth_db: float,
    attack_ms: float = DEFAULT_ATTACK_MS,
    release_ms: float = DEFAULT_RELEASE_MS,
    hop_ms: float = DEFAULT_HOP_MS,
    pause_ride_db: float = 0.0,
) -> AudioSegment:
    """Duck ``bed`` with a soft speech gate; depth_db is max attenuation under speech.

    Caller should apply base cue ``level_db`` before this. Under silence the gate
    recovers toward 0 dB attenuation (base level preserved), optionally boosted by
    ``pause_ride_db`` so underscore rides up in intentional air. Under continuous
    speech the attenuation stays near ``−depth_db`` rather than pumping with
    syllable amplitude.
    """
    if depth_db <= 0 or len(bed) <= 0:
        return bed
    if not speech_window_usable(speech_window):
        return bed.apply_gain(-float(depth_db))

    hop = max(1, int(hop_ms))
    # Align lengths: duck over the bed window using speech of matching timeline length
    speech = speech_window[: len(bed)]
    if len(speech) < len(bed):
        speech = speech + AudioSegment.silent(
            duration=len(bed) - len(speech),
            frame_rate=speech.frame_rate or bed.frame_rate,
        )

    hop_db = _hop_rms_db(speech, hop)
    # Adaptive silence / open anchors from the window itself (fail-open to defaults)
    finite = [d for d in hop_db if d > -119.0]
    if not finite:
        return bed.apply_gain(-float(depth_db))
    p90 = float(np.percentile(finite, 90))
    full_db = max(_FULL_SPEECH_DBFS, min(-6.0, p90))
    silence_db = min(_SILENCE_DBFS, full_db - 18.0)
    open_db = silence_db + _GATE_OPEN_ABOVE_SILENCE_DB

    amounts = [_gate_from_db(d, silence_db=silence_db, open_db=open_db) for d in hop_db]
    followed = _follow_envelope(
        amounts,
        hop_ms=hop,
        attack_ms=attack_ms,
        release_ms=release_ms,
    )
    ride = max(0.0, float(pause_ride_db))
    # Under speech: −depth; in air: +pause_ride (amount→0).
    gain_db = [(-float(depth_db) * a) + (ride * (1.0 - a)) for a in followed]
    return _apply_gain_envelope(bed, gain_db, hop)


def duck_bed_with_sidechain(
    bed: AudioSegment,
    speech_window: AudioSegment | None,
    *,
    level_db: float,
    duck_db: float,
    cfg: dict[str, Any] | None = None,
) -> AudioSegment:
    """Apply base level then envelope duck, or static ``level_db - duck_db`` fallback."""
    settings = sidechain_duck_cfg(cfg)
    leveled = bed.apply_gain(float(level_db))
    if not settings["enabled"] or not speech_window_usable(speech_window):
        return leveled.apply_gain(-float(duck_db))
    assert speech_window is not None
    return envelope_duck(
        leveled,
        speech_window,
        depth_db=float(duck_db),
        attack_ms=float(settings["attack_ms"]),
        release_ms=float(settings["release_ms"]),
        hop_ms=float(settings["hop_ms"]),
        pause_ride_db=float(settings.get("pause_ride_db") or 0.0),
    )
