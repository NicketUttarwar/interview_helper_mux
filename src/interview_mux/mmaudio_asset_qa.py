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


def _musicality_checks(samples: list[float], rate: int) -> dict[str, Any]:
    """Reject thin sine-like / no-onset / missing-bass theme stems."""
    fail: list[str] = []
    warn: list[str] = []
    pulse_clarity = 0.0
    speech_band_roughness = 0.0
    tonal_center_score = 0.5
    if not samples or rate <= 0:
        return {
            "fail_reasons": ["musicality_empty"],
            "warn_reasons": [],
            "pulse_clarity": 0.0,
            "speech_band_roughness": 0.0,
            "tonal_center_score": 0.0,
        }
    # Onset / energy variability: flat sine stubs have near-constant RMS windows.
    window = max(1, int(rate * 0.05))
    rms_vals: list[float] = []
    for i in range(0, len(samples) - window, window):
        rms_vals.append(_rms(samples[i : i + window]))
    if rms_vals:
        mean_r = sum(rms_vals) / len(rms_vals)
        var = sum((r - mean_r) ** 2 for r in rms_vals) / len(rms_vals)
        cv2 = var / (mean_r * mean_r) if mean_r > 1e-6 else 0.0
        if mean_r > 1e-6 and cv2 < 0.02:
            fail.append("musicality_no_onset_structure")
        # Soft pulse clarity: moderate RMS modulation is good; flat or chaotic is bad.
        pulse_clarity = max(0.0, min(1.0, (cv2 - 0.02) / 0.25))
    # Low-end energy proxy via long-window zero-crossing (too many ZC ⇒ thin/high-only).
    zc = sum(1 for a, b in zip(samples[::4], samples[4::4]) if a * b < 0)
    zc_rate = zc * 4 / max(1, len(samples) / rate) if samples else 0.0
    # Extremely high average ZC rate with low variance ⇒ sine-like tone.
    if zc_rate > 800 and len(rms_vals) > 4:
        # Estimate spectral flatness via peak/rms of whole clip.
        peak = max(abs(s) for s in samples) or 1e-8
        rms = _rms(samples) or 1e-8
        if peak / rms < 2.2:
            fail.append("musicality_sine_like_spectrum")
            tonal_center_score = 0.1
    # Missing low-end: downsample RMS of heavily low-passed proxy (moving average).
    ma = 0.0
    alpha = min(0.05, 200.0 / max(rate, 1))
    low_acc = 0.0
    for s in samples[::8]:
        ma = (1 - alpha) * ma + alpha * s
        low_acc += ma * ma
    low_rms = math.sqrt(low_acc / max(1, len(samples[::8])))
    total = _rms(samples) or 1e-8
    if low_rms / total < 0.08:
        warn.append("musicality_missing_low_end")
    speech_band_roughness = _band_energy_ratio(samples, rate, 1000.0, 4000.0)
    if speech_band_roughness > 0.55:
        warn.append("musicality_speech_band_harsh")
    return {
        "fail_reasons": fail,
        "warn_reasons": warn,
        "zc_rate": round(zc_rate, 2),
        "pulse_clarity": round(pulse_clarity, 4),
        "speech_band_roughness": round(speech_band_roughness, 4),
        "tonal_center_score": round(tonal_center_score, 4),
    }


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
    from interview_mux.music_motif import THEME_PUNCTUATOR_ROLES, THEME_ROLES, asset_id_is_banned, is_theme_role

    if asset_id_is_banned(asset_id):
        row["verdict"] = "fail"
        row["reasons"].append("banned_non_music_asset_id")
        row["action"] = "regenerate"
        row["recommended_action"] = "regenerate"
        return row

    gen_meta_path = path.with_suffix(".gen.json")
    if gen_meta_path.is_file():
        try:
            gmeta = json.loads(gen_meta_path.read_text(encoding="utf-8"))
            row["generation_backend"] = gmeta.get("backend")
            row["generation_seed"] = gmeta.get("seed")
            row["prompt_hash"] = gmeta.get("prompt_hash")
            if gmeta.get("backend") == "musical_stub":
                from interview_mux.musicgen_runner import fail_closed_on_stub

                row["reasons"].append("musical_stub_last_resort")
                if fail_closed_on_stub():
                    row["verdict"] = "fail"
                    row["reasons"].append("musical_stub_backend")
                    row["action"] = "regenerate"
                    row["recommended_action"] = "regenerate"
                    return row
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    stinger_roles = {"chapter_stinger", "transition_stinger", "cold_open", "accent_foley"} | set(
        THEME_PUNCTUATOR_ROLES
    )
    if role in stinger_roles or role in {"ambient_bed", "theme_underscore"} or is_theme_role(role):
        role_min_peak = min_peak
        if role in {"theme_cold_open", "theme_outro"}:
            role_min_peak = float(
                mm_cfg.get("min_cold_open_peak_dbfs", mm_cfg.get("min_stinger_peak_dbfs", min_peak))
            )
        elif role in stinger_roles or role in THEME_PUNCTUATOR_ROLES:
            role_min_peak = float(mm_cfg.get("min_stinger_peak_dbfs", min_peak))
        if peak_dbfs < role_min_peak or rms_dbfs < min_rms:
            row["verdict"] = "fail"
            row["reasons"].append("inaudible_level")
            row["action"] = "regenerate"
            row["recommended_action"] = "regenerate"
            row["suggested_level_db_delta"] = max(0.0, role_min_peak - peak_dbfs + 3.0)

    if bool(mm_cfg.get("musicality_qa_enabled", True)) and is_theme_role(role):
        musicality = _musicality_checks(samples, rate)
        row["musicality"] = musicality
        for reason in musicality.get("fail_reasons") or []:
            row["verdict"] = "fail"
            row["reasons"].append(reason)
            row["action"] = "regenerate"
            row["recommended_action"] = "regenerate"
        for reason in musicality.get("warn_reasons") or []:
            if row["verdict"] == "pass":
                row["verdict"] = "warn"
            row["reasons"].append(reason)

    if role in {"chapter_stinger", "transition_stinger", "cold_open", "accent_foley"} | set(THEME_PUNCTUATOR_ROLES):
        tail_n = int(rate * 0.2)
        if tail_n > 0 and len(samples) >= tail_n:
            tail_rms = _rms(samples[-tail_n:])
            if tail_rms > peak * 0.15:
                row["verdict"] = "warn" if row["verdict"] == "pass" else row["verdict"]
                row["reasons"].append("hot_tail")
                row["suggested_trim_ms"] = row.get("suggested_trim_ms", 200)

    if role in {"ambient_bed", "theme_underscore"} or role in THEME_ROLES:
        speech_ratio = _band_energy_ratio(samples, rate, 300.0, 3400.0)
        row["speech_band_ratio"] = round(speech_ratio, 4)
        # theme_underscore musical beds are pitched instruments — speech-band energy is expected;
        # only fail hard ambient_bed murmur-like leaks.
        if speech_ratio > 0.55 and role == "ambient_bed":
            row["verdict"] = "fail"
            row["reasons"].append("speech_band_leak")
            row["recommended_action"] = "regenerate"
            row["suggested_cfg_delta"] = -0.4
        elif speech_ratio > 0.7 and role == "theme_underscore":
            row["verdict"] = "warn" if row["verdict"] == "pass" else row["verdict"]
            row["reasons"].append("speech_band_heavy_music")
            if row.get("recommended_action") == "pass":
                row["recommended_action"] = "refine"
        elif speech_ratio > 0.4 and role == "ambient_bed":
            row["verdict"] = "warn" if row["verdict"] == "pass" else row["verdict"]
            row["reasons"].append("speech_band_leak")
            if row.get("recommended_action") == "pass":
                row["recommended_action"] = "refine"
            row["suggested_cfg_delta"] = -0.4

        if role in {"ambient_bed", "theme_underscore"} and mean_rms < 0.01:
            row["verdict"] = "warn" if row["verdict"] == "pass" else row["verdict"]
            row["reasons"].append("bed_too_quiet")
            row["suggested_level_db_delta"] = 2.0
        elif role == "ambient_bed" and row["verdict"] == "pass":
            row["suggested_level_db_delta"] = -2.0
            row["reasons"].append("default_speech_first_bed_lower")
        if role in {"ambient_bed", "theme_underscore"}:
            row["loop_seam_score"] = round(loop_seam_score(samples, rate), 4)

    # Tick/murmur density gate for theme music — reject percussive woodtick-like stems.
    if is_theme_role(role) or role in THEME_ROLES:
        dens = _peak_density(samples, rate)
        row["peak_density"] = round(dens, 4)
        if dens > 0.35:
            row["verdict"] = "fail"
            row["reasons"].append("tick_like_transient_density")
            row["recommended_action"] = "regenerate"
        # Near-flat noise beds (murmur/HVAC proxy): low peak density + low tonal variation.
        if dens < 0.02 and mean_rms > 0.02 and peak / max(mean_rms, 1e-6) < 1.8:
            row["verdict"] = "fail"
            row["reasons"].append("murmur_like_noise_bed")
            row["recommended_action"] = "regenerate"

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
    # Prefer staging-aware path: generation writes via ctx.path(); final_path is
    # empty until stage flush, which previously yielded assets=[] QA forever.
    assets_dir = ctx.path("sound_design", "assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
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


def heal_mmaudio_qa_wav_parity(ctx: RunContext) -> dict[str, Any]:
    """Make ``mmaudio_qa.json`` complete: every QA row has a wav, every wav has QA.

    Phantom QA rows (asset ids without a wav) make the artifact ``partial`` and
    halt ``mmaudio_sfx`` even when mix can continue without those stems.
    """
    qa = load_mmaudio_qa(ctx)
    assets_dir = ctx.path("sound_design", "assets")
    wav_ids = {p.stem for p in assets_dir.glob("*.wav")} if assets_dir.is_dir() else set()
    qa_ids = {
        str(row.get("asset_id"))
        for row in (qa.get("assets") or [])
        if isinstance(row, dict) and row.get("asset_id")
    }
    missing_qa = sorted(wav_ids - qa_ids)
    extra_qa = sorted(qa_ids - wav_ids)
    if not missing_qa and not extra_qa:
        return {"healed": False, "dropped": [], "analyzed": []}
    if missing_qa:
        qa = run_mmaudio_asset_qa(ctx)
        qa_ids = {
            str(row.get("asset_id"))
            for row in (qa.get("assets") or [])
            if isinstance(row, dict) and row.get("asset_id")
        }
        extra_qa = sorted(qa_ids - wav_ids)
    dropped: list[str] = []
    if extra_qa:
        keep = [
            row
            for row in (qa.get("assets") or [])
            if isinstance(row, dict) and str(row.get("asset_id") or "") in wav_ids
        ]
        dropped = extra_qa
        qa = {"version": int(qa.get("version") or 1), "assets": keep}
    try:
        from interview_mux.write_staging import write_committed_json

        write_committed_json(ctx, OUTPUT_PATH, qa, stage_key="mmaudio_sfx")
    except Exception:
        try:
            ctx.write_json(OUTPUT_PATH, qa, stage_key="mmaudio_sfx", skip_handoff=True)
        except Exception:
            out = ctx.final_path(*OUTPUT_PATH.split("/"))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(qa, indent=2) + "\n", encoding="utf-8")
    ctx.log(
        "mmaudio_qa parity heal: "
        + f"analyzed={missing_qa[:8]} dropped={dropped[:8]}",
        level="warning",
        stage="mmaudio_sfx",
    )
    return {"healed": True, "dropped": dropped, "analyzed": missing_qa}


def loop_seam_score(samples: list[float], rate: int) -> float:
    """Score loop continuity using level, boundary, and waveform agreement."""
    if not samples or rate <= 0:
        return 0.0
    window = max(1, int(rate * 0.08))
    if len(samples) < window * 2:
        return 0.0
    head_samples = samples[:window]
    tail_samples = samples[-window:]
    head_rms = _rms(head_samples)
    tail_rms = _rms(tail_samples)
    level_scale = max(head_rms, tail_rms, 1e-6)
    level_score = 1.0 - min(1.0, abs(head_rms - tail_rms) / level_scale)

    # A loop splice must not introduce a sample step. Normalize by local signal
    # energy so this remains useful for both quiet beds and mastered stems.
    boundary_delta = abs(samples[0] - samples[-1])
    boundary_scale = max(level_scale * 2.0, 1e-5)
    boundary_score = 1.0 - min(1.0, boundary_delta / boundary_scale)

    head_mean = sum(head_samples) / window
    tail_mean = sum(tail_samples) / window
    head_centered = [value - head_mean for value in head_samples]
    tail_centered = [value - tail_mean for value in tail_samples]
    head_energy = math.sqrt(sum(value * value for value in head_centered))
    tail_energy = math.sqrt(sum(value * value for value in tail_centered))
    if head_energy > 1e-8 and tail_energy > 1e-8:
        correlation = sum(
            head * tail for head, tail in zip(head_centered, tail_centered)
        ) / (head_energy * tail_energy)
        correlation_score = max(0.0, min(1.0, (correlation + 1.0) / 2.0))
    else:
        # Constant windows have no defined correlation. Treat matching values
        # as continuous and differing DC levels as discontinuous.
        correlation_score = boundary_score

    score = 0.25 * level_score + 0.35 * boundary_score + 0.40 * correlation_score
    return max(0.0, min(1.0, score))


def _loop_seam_score(samples: list[float], rate: int) -> float:
    """Backward-compatible private alias for older callers."""
    return loop_seam_score(samples, rate)


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
