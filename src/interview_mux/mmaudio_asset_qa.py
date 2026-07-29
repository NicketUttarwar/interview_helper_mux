"""Deterministic QA for locally generated MMAudio SFX WAV assets."""

from __future__ import annotations

import json
import math
import struct
import wave
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import load_sonic_context

OUTPUT_PATH = "sound_design/mmaudio_qa.json"


def _read_wav_frames(path: Path) -> tuple[list[float], int]:
    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
    if sample_width != 2:
        raise ValueError(f"unsupported sample width {sample_width}")
    count = len(raw) // 2
    samples = struct.unpack(f"<{count}h", raw)
    if n_channels > 1:
        samples = [samples[i] for i in range(0, count, n_channels)]
    floats = [s / 32768.0 for s in samples]
    return floats, rate


def _rms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def _peak_density(samples: list[float], rate: int, *, window_ms: int = 20) -> float:
    """Fraction of short windows with sharp transient peaks (stinger percussiveness proxy)."""
    if not samples or rate <= 0:
        return 0.0
    window = max(1, int(rate * window_ms / 1000))
    if len(samples) < window:
        return 0.0
    hot = 0
    count = 0
    for i in range(0, len(samples) - window, window):
        chunk = samples[i : i + window]
        peak = max(abs(s) for s in chunk) if chunk else 0.0
        rms = _rms(chunk)
        count += 1
        if rms > 1e-6 and peak >= 0.12 and peak / rms >= 3.0:
            hot += 1
    return hot / count if count else 0.0


def _band_energy_ratio(samples: list[float], rate: int, low_hz: float, high_hz: float) -> float:
    """Crude speech-band ratio via windowed RMS on band-limited proxy (zero-crossing gate)."""
    if not samples or rate <= 0:
        return 0.0
    total = _rms(samples)
    if total < 1e-6:
        return 0.0
    band_samples: list[float] = []
    window = max(1, int(rate / 200))
    for i in range(0, len(samples) - window, window):
        chunk = samples[i : i + window]
        zc = sum(1 for a, b in zip(chunk, chunk[1:]) if a * b < 0)
        freq_est = zc * rate / (2 * len(chunk))
        if low_hz <= freq_est <= high_hz:
            band_samples.extend(chunk)
    if not band_samples:
        return 0.0
    return _rms(band_samples) / total


def analyze_asset_wav(
    *,
    asset_id: str,
    path: Path,
    plan_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    role = str((plan_row or {}).get("role", ""))
    plan_duration = float((plan_row or {}).get("duration_seconds") or 0)
    silence_threshold = float((merged_config().get("mmaudio") or {}).get("silence_rms_threshold", 0.001))
    row: dict[str, Any] = {
        "asset_id": asset_id,
        "role": role,
        "verdict": "pass",
        "generation_status": "pass",
        "recommended_action": "pass",
        "reasons": [],
    }

    if not path.is_file():
        row["verdict"] = "fail"
        row["generation_status"] = "failed"
        row["reasons"].append("missing_wav")
        row["action"] = "regenerate"
        row["recommended_action"] = "regenerate"
        return row

    try:
        size = path.stat().st_size
        if size < 1000:
            row["verdict"] = "fail"
            row["generation_status"] = "failed"
            row["reasons"].append("suspiciously_small_wav")
            row["action"] = "regenerate"
            row["recommended_action"] = "regenerate"
            return row
        samples, rate = _read_wav_frames(path)
    except (OSError, ValueError, wave.Error):
        row["verdict"] = "fail"
        row["generation_status"] = "failed"
        row["reasons"].append("unreadable_wav")
        row["action"] = "regenerate"
        row["recommended_action"] = "regenerate"
        return row

    actual_duration = len(samples) / rate if rate else 0.0
    row["actual_duration_seconds"] = round(actual_duration, 3)

    if plan_duration > 0:
        if actual_duration > plan_duration + 1.0:
            row["verdict"] = "warn"
            row["reasons"].append("duration_exceeds_plan")
            trim_ms = int((actual_duration - plan_duration) * 1000)
            row["suggested_trim_ms"] = trim_ms
            row["action"] = "trim_hint"
        elif actual_duration < plan_duration * 0.5:
            row["verdict"] = "fail"
            row["reasons"].append("duration_wildly_short")
            row["action"] = "regenerate"

    peak = max(abs(s) for s in samples) if samples else 0.0
    mean_rms = _rms(samples)
    peak_dbfs = 20.0 * math.log10(max(peak, 1e-8))
    rms_dbfs = 20.0 * math.log10(max(mean_rms, 1e-8))
    row["peak_dbfs"] = round(peak_dbfs, 2)
    row["rms_dbfs"] = round(rms_dbfs, 2)
    row["silence_detected"] = bool(mean_rms <= silence_threshold)
    if row["silence_detected"]:
        row["verdict"] = "fail"
        row["generation_status"] = "placeholder"
        row["reasons"].append("silence_detected")
        row["recommended_action"] = "regenerate"
    if peak > 0.98:
        row["verdict"] = "warn" if row["verdict"] == "pass" else row["verdict"]
        row["reasons"].append("peak_too_hot")
        row["suggested_level_db_delta"] = -3.0

    mm_cfg = merged_config().get("mmaudio") or {}
    # Reject near-inaudible assets (e.g. stingers at ~−35 dBFS) before mix.
    min_peak = float(mm_cfg.get("min_audible_peak_dbfs", -28.0))
    min_rms = float(mm_cfg.get("min_audible_rms_dbfs", -40.0))
    stinger_roles = {"chapter_stinger", "transition_stinger", "cold_open", "accent_foley"}
    if role in stinger_roles or role == "ambient_bed":
        role_min_peak = min_peak
        if role in stinger_roles:
            role_min_peak = float(mm_cfg.get("min_stinger_peak_dbfs", min_peak))
        if peak_dbfs < role_min_peak or rms_dbfs < min_rms:
            row["verdict"] = "fail"
            row["reasons"].append("inaudible_level")
            row["action"] = "regenerate"
            row["recommended_action"] = "regenerate"
            row["suggested_level_db_delta"] = max(0.0, role_min_peak - peak_dbfs + 3.0)

    if role in {"chapter_stinger", "transition_stinger", "cold_open", "accent_foley"}:
        tail_n = int(rate * 0.2)
        if tail_n > 0 and len(samples) >= tail_n:
            tail_rms = _rms(samples[-tail_n:])
            if tail_rms > peak * 0.15:
                row["verdict"] = "warn" if row["verdict"] == "pass" else row["verdict"]
                row["reasons"].append("hot_tail")
                row["suggested_trim_ms"] = row.get("suggested_trim_ms", 200)

    if role == "ambient_bed":
        speech_ratio = _band_energy_ratio(samples, rate, 300.0, 3400.0)
        row["speech_band_ratio"] = round(speech_ratio, 4)
        if speech_ratio > 0.55:
            # Speech-band-heavy "beds" sound like hum/buzz under dialogue — fail + regenerate.
            row["verdict"] = "fail"
            row["reasons"].append("speech_band_leak")
            row["recommended_action"] = "regenerate"
            row["suggested_cfg_delta"] = -0.4
        elif speech_ratio > 0.4:
            row["verdict"] = "warn" if row["verdict"] == "pass" else row["verdict"]
            row["reasons"].append("speech_band_leak")
            if row.get("recommended_action") == "pass":
                row["recommended_action"] = "refine"
            row["suggested_cfg_delta"] = -0.4

        if mean_rms < 0.01:
            row["verdict"] = "warn" if row["verdict"] == "pass" else row["verdict"]
            row["reasons"].append("bed_too_quiet")
            row["suggested_level_db_delta"] = 2.0
        elif role == "ambient_bed" and row["verdict"] == "pass":
            row["suggested_level_db_delta"] = -2.0
            row["reasons"].append("default_speech_first_bed_lower")
        row["loop_seam_score"] = round(_loop_seam_score(samples, rate), 4)

    if role == "era_music_bed":
        speech_ratio = _band_energy_ratio(samples, rate, 300.0, 3400.0)
        row["speech_band_ratio"] = round(speech_ratio, 4)
        if speech_ratio > 0.55:
            row["verdict"] = "fail"
            row["reasons"].append("speech_band_leak")
            row["recommended_action"] = "regenerate"

    if role == "chapter_stinger" and row["verdict"] == "pass":
        row["suggested_crossfade_ms"] = 120

    if row["verdict"] == "warn":
        row["recommended_action"] = "trim_hint" if row.get("suggested_trim_ms") else "refine"
    elif row["verdict"] == "fail" and row["recommended_action"] == "pass":
        row["recommended_action"] = "regenerate"

    return row


def run_mmaudio_asset_qa(ctx: RunContext) -> dict[str, Any]:
    assets_dir = ctx.final_path("sound_design", "assets")
    plan_by_id: dict[str, dict[str, Any]] = {}
    sdp_palettes: list[dict[str, Any]] = []
    if ctx.artifact_exists("understanding/sound_design_plan.json"):
        sdp = ctx.read_json("understanding/sound_design_plan.json")
        sdp_palettes = [p for p in (sdp.get("palettes") or []) if isinstance(p, dict)]
        for asset in sdp.get("assets") or []:
            if isinstance(asset, dict) and asset.get("asset_id"):
                plan_by_id[str(asset["asset_id"])] = asset
    prompt_by_id: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("sound_design/sfx_prompts.json"):
        doc = ctx.read_json("sound_design/sfx_prompts.json")
        for row in (doc.get("prompts") or []):
            if isinstance(row, dict) and row.get("asset_id"):
                prompt_by_id[str(row["asset_id"])] = row
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    generation_meta = meta.get("sfx_generation_meta") if isinstance(meta.get("sfx_generation_meta"), dict) else {}
    sonic = load_sonic_context(ctx) or {}
    atlas_bucket = str(((sonic.get("scenario") or {}).get("atlas_bucket")) or "")
    sap_room_hint = ""
    if ctx.artifact_exists("understanding/source_acoustic_profile.json"):
        sap = ctx.read_json("understanding/source_acoustic_profile.json")
        if isinstance(sap, dict):
            sap_room_hint = str(((sap.get("energy") or {}).get("room_timbre_hint")) or "")
    sonic_keywords = {
        str(k).lower()
        for row in (sonic.get("tag_registry") or [])
        if isinstance(row, dict)
        for k in (row.get("keywords") or [])
        if str(k).strip()
    }

    results: list[dict[str, Any]] = []
    if assets_dir.is_dir():
        for wav in sorted(assets_dir.glob("*.wav")):
            aid = wav.stem
            results.append(
                analyze_asset_wav(
                    asset_id=aid,
                    path=wav,
                    plan_row=plan_by_id.get(aid),
                )
            )
    for row in results:
        aid = str(row.get("asset_id") or "")
        gen = generation_meta.get(aid) if isinstance(generation_meta, dict) else {}
        if isinstance(gen, dict) and gen.get("generation_status"):
            row["generation_status"] = str(gen.get("generation_status"))
        prompt = prompt_by_id.get(aid) or {}
        row["theme_fit_score"] = round(_theme_fit_score(str(prompt.get("sfx_prompt") or ""), sonic_keywords), 4)
        if row.get("theme_fit_score", 1.0) < float((merged_config().get("mmaudio") or {}).get("theme_fit_threshold", 0.6)):
            if row.get("verdict") == "pass":
                row["verdict"] = "warn"
            row.setdefault("reasons", []).append("low_theme_fit")
            if row.get("recommended_action") == "pass":
                row["recommended_action"] = "refine"
        if row.get("generation_status") in {"failed", "placeholder"} and row.get("verdict") == "pass":
            row["verdict"] = "fail"
            row.setdefault("reasons", []).append("generation_status_not_pass")
            row["recommended_action"] = "regenerate"
        if row.get("silence_detected") is True:
            row["generation_status"] = "placeholder"
            row["recommended_action"] = "regenerate"
        from interview_mux.semantic_audio_qa import apply_semantic_verdict, maybe_semantic_similarity

        semantic = maybe_semantic_similarity(
            wav_path=assets_dir / f"{aid}.wav",
            prompt_text=str(prompt.get("sfx_prompt") or ""),
            asset_id=aid,
        )
        apply_semantic_verdict(row, semantic)
        bucket = _expected_sonic_bucket(plan_by_id.get(aid), sdp_palettes)
        sap_expected = _expected_bucket_from_room_timbre(sap_room_hint)
        wav_path = assets_dir / f"{aid}.wav"
        if wav_path.is_file():
            try:
                samples, rate = _read_wav_frames(wav_path)
                inferred = _infer_sonic_bucket(samples, rate)
                palette_match = bucket is None or inferred == bucket
                sap_match = sap_expected is None or inferred == sap_expected
                row["spectral_bucket_match"] = palette_match and sap_match
                row["inferred_sonic_bucket"] = inferred
                if sap_expected:
                    row["sap_expected_sonic_bucket"] = sap_expected
                if bucket and inferred != bucket and row.get("verdict") == "pass":
                    row["verdict"] = "warn"
                    row.setdefault("reasons", []).append("spectral_bucket_mismatch")
                    if row.get("recommended_action") == "pass":
                        row["recommended_action"] = "refine"
                if sap_expected and inferred != sap_expected:
                    if row.get("verdict") == "pass":
                        row["verdict"] = "warn"
                    row.setdefault("reasons", []).append("room_timbre_mismatch")
                    if row.get("recommended_action") == "pass":
                        row["recommended_action"] = "refine"
                role = str(row.get("role") or "")
                if (
                    atlas_bucket == "trauma_adjacent"
                    and role in {"chapter_stinger", "transition_stinger", "cold_open"}
                ):
                    density = _peak_density(samples, rate)
                    row["peak_density"] = round(density, 4)
                    threshold = float(
                        (merged_config().get("mmaudio") or {}).get("trauma_peak_density_threshold", 0.32)
                    )
                    if density >= threshold:
                        row["verdict"] = "fail"
                        row.setdefault("reasons", []).append("trauma_percussive_transient")
                        row["recommended_action"] = "regenerate"
            except (OSError, ValueError, wave.Error):
                pass

    doc = {"version": 1, "assets": results}
    # Always commit to the final artifact tree (not only .pending_writes).
    try:
        ctx.write_json(OUTPUT_PATH, doc, stage_key="mmaudio_sfx", skip_handoff=True)
    except Exception:
        out = ctx.final_path(*OUTPUT_PATH.split("/"))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if results:
        fails = sum(1 for r in results if r.get("verdict") == "fail")
        warns = sum(1 for r in results if r.get("verdict") == "warn")
        ctx.log(
            f"mmaudio_qa: {len(results)} asset(s) — {fails} fail, {warns} warn",
            level="info",
            stage="mmaudio_sfx",
        )
    return doc


def _loop_seam_score(samples: list[float], rate: int) -> float:
    if not samples or rate <= 0:
        return 0.0
    window = max(1, int(rate * 0.08))
    if len(samples) < window * 2:
        return 0.0
    head = _rms(samples[:window])
    tail = _rms(samples[-window:])
    denom = max(head, tail, 1e-6)
    delta = abs(head - tail) / denom
    return max(0.0, min(1.0, 1.0 - delta))


def _theme_fit_score(prompt: str, sonic_keywords: set[str]) -> float:
    if not prompt.strip():
        return 0.0
    if not sonic_keywords:
        return 1.0
    words = {w.lower() for w in prompt.split() if len(w) >= 3}
    if not words:
        return 0.0
    overlap = len(words & sonic_keywords)
    return min(1.0, overlap / max(4, min(12, len(sonic_keywords))))


_ROLE_SONIC_BUCKET: dict[str, str] = {
    "ambient_bed": "ambient_territory",
    "chapter_stinger": "transition_family",
    "transition_stinger": "transition_family",
    "cold_open": "transition_family",
    "vo_bridge": "accent_texture",
    "accent_foley": "accent_texture",
}


def _expected_bucket_from_room_timbre(room_timbre_hint: str) -> str | None:
    """Map SAP room_timbre_hint tokens to expected inferred sonic buckets."""
    hint = str(room_timbre_hint or "").lower().strip()
    if not hint:
        return None
    if "bright" in hint or "presence" in hint or "transient" in hint:
        return "transition_family"
    if "warm" in hint or "low_mid" in hint or "roomy" in hint or "broadband" in hint:
        return "ambient_territory"
    if "neutral_mid" in hint or hint.startswith("dry_close_mic"):
        return "accent_texture"
    return None


def _expected_sonic_bucket(
    plan_row: dict[str, Any] | None,
    palettes: list[dict[str, Any]],
) -> str | None:
    if not plan_row:
        return None
    palette_id = str(plan_row.get("palette_id") or "")
    if palette_id:
        for palette in palettes:
            if str(palette.get("palette_id") or "") == palette_id:
                bucket = palette.get("sonic_bucket")
                if bucket:
                    return str(bucket)
    role = str(plan_row.get("role") or "")
    return _ROLE_SONIC_BUCKET.get(role)


def _infer_sonic_bucket(samples: list[float], rate: int) -> str:
    low = _band_energy_ratio(samples, rate, 80.0, 800.0)
    mid = _band_energy_ratio(samples, rate, 800.0, 4000.0)
    high = _band_energy_ratio(samples, rate, 4000.0, 12000.0)
    if low >= mid and low >= high:
        return "ambient_territory"
    if high >= max(low, mid) * 1.15:
        return "transition_family"
    return "accent_texture"


def load_mmaudio_qa(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(OUTPUT_PATH):
        return {"version": 1, "assets": []}
    doc = ctx.read_json(OUTPUT_PATH)
    return doc if isinstance(doc, dict) else {"version": 1, "assets": []}
