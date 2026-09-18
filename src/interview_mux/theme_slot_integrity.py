"""Theme open/outro slot integrity — no silent duration, generate from reservations.

Root cause (exec_11130): EDL/mix reserved opening_music + preserve_full_duration outro
air without MusicGen ever producing those WAVs (lazy cue refs + mix-time cue invent).
Limbo omit then cleared "missing" while leaving silent pads on the timeline.

Invariants:
1. Speech-free theme roles cannot contribute timeline ms without an audible WAV.
2. Reserved bookend assets are always in the MusicGen required set.
3. Mix may rebind outro anchors but must not create new outro cues.
4. Honest music omit shrinks/clears reservations in the same write.
5. Coverage "realized" requires an audible file on disk.
6. Heals for hollow bookends pin mmaudio_sfx (or music-epoch place), not silence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

SPEECH_FREE_THEME_ROLES: frozenset[str] = frozenset({"theme_cold_open", "theme_outro"})

# Peak absolute sample threshold (~-40 dBFS on int16) — digital silence fails.
_AUDIBLE_PEAK_FLOOR = 300


def is_speech_free_theme_role(role: str | None) -> bool:
    return str(role or "").strip() in SPEECH_FREE_THEME_ROLES


def wav_is_audible(path: Path | None, *, peak_floor: int = _AUDIBLE_PEAK_FLOOR) -> bool:
    """True when path exists, is non-trivial, and has measurable peak energy."""
    if path is None:
        return False
    try:
        p = Path(path)
        if not p.is_file() or p.stat().st_size < 1000:
            return False
    except OSError:
        return False
    try:
        import array
        import wave

        with wave.open(str(p), "rb") as w:
            n = w.getnframes()
            ch = w.getnchannels()
            sw = w.getsampwidth()
            if n <= 0 or sw != 2:
                return False
            # Sample up to ~2s from start and ~1s from end.
            sr = max(1, w.getframerate())
            head_n = min(n, sr * 2)
            w.setpos(0)
            raw = w.readframes(head_n)
            samples = array.array("h")
            samples.frombytes(raw)
            if ch > 1:
                samples = samples[::ch]
            peak = max((abs(x) for x in samples), default=0)
            if peak >= peak_floor:
                return True
            if n > head_n:
                tail_n = min(n, sr)
                w.setpos(max(0, n - tail_n))
                raw = w.readframes(tail_n)
                samples = array.array("h")
                samples.frombytes(raw)
                if ch > 1:
                    samples = samples[::ch]
                peak = max((abs(x) for x in samples), default=0)
                return peak >= peak_floor
            return False
    except Exception:
        # Unreadable WAV → treat as unusable (fail closed).
        return False


def resolve_theme_asset_wav(ctx: Any, asset_id: str) -> Path | None:
    aid = str(asset_id or "").strip()
    if not aid or not hasattr(ctx, "read_path"):
        return None
    for parts in (
        ("sound_design", "assets", f"{aid}.wav"),
        ("master", "sfx", f"{aid}.wav"),
    ):
        try:
            path = ctx.read_path(*parts)
        except Exception:
            continue
        if path is not None and Path(path).is_file():
            return Path(path)
        try:
            committed = ctx.final_path(*parts)
            if committed.is_file():
                return Path(committed)
        except Exception:
            pass
    return None


def theme_asset_audible(ctx: Any, asset_id: str) -> bool:
    return wav_is_audible(resolve_theme_asset_wav(ctx, asset_id))


def _sdp(ctx: Any) -> dict[str, Any]:
    if not hasattr(ctx, "artifact_exists"):
        return {}
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return {}
    try:
        doc = ctx.read_json("understanding/sound_design_plan.json")
    except Exception:
        return {}
    return doc if isinstance(doc, dict) else {}


def _podcast_cues(sdp: dict[str, Any]) -> list[dict[str, Any]]:
    flow = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    podcast = flow.get("podcast") if isinstance(flow.get("podcast"), dict) else {}
    cues = podcast.get("cues") if isinstance(podcast.get("cues"), list) else []
    out = [c for c in cues if isinstance(c, dict)]
    top = sdp.get("cues") if isinstance(sdp.get("cues"), list) else []
    out.extend(c for c in top if isinstance(c, dict))
    return out


def _asset_role(asset: dict[str, Any]) -> str:
    return str(asset.get("role") or asset.get("music_role") or "").strip()


def preferred_cold_open_asset_id(ctx: Any) -> str | None:
    assets = [a for a in (_sdp(ctx).get("assets") or []) if isinstance(a, dict)]
    cold = [a for a in assets if _asset_role(a) == "theme_cold_open" and a.get("asset_id")]
    if not cold:
        return None
    for a in cold:
        if "full_bed" in str(a.get("asset_id") or "").lower():
            return str(a["asset_id"])
    return str(cold[0]["asset_id"])


def preferred_outro_asset_id(ctx: Any) -> str | None:
    assets = [a for a in (_sdp(ctx).get("assets") or []) if isinstance(a, dict)]
    try:
        from interview_mux.music_lane import pick_theme_outro_asset

        picked = pick_theme_outro_asset(assets)
        if isinstance(picked, dict) and picked.get("asset_id"):
            return str(picked["asset_id"])
    except Exception:
        pass
    for a in assets:
        if _asset_role(a) == "theme_outro" and a.get("asset_id"):
            return str(a["asset_id"])
    return None


def speech_free_palette_asset_ids(ctx: Any) -> set[str]:
    """Preferred speech-free palette ids (one open + one close), not every motif."""
    ids: set[str] = set()
    open_id = preferred_cold_open_asset_id(ctx)
    close_id = preferred_outro_asset_id(ctx)
    if open_id:
        ids.add(open_id)
    if close_id:
        ids.add(close_id)
    return ids


def edl_has_opening_music_reservation(ctx: Any) -> bool:
    if not hasattr(ctx, "artifact_exists") or not ctx.artifact_exists("master/edl.json"):
        return False
    try:
        edl = ctx.read_json("master/edl.json")
    except Exception:
        return False
    if not isinstance(edl, dict):
        return False
    for clip in edl.get("clips") or []:
        if not isinstance(clip, dict):
            continue
        if str(clip.get("air_kind") or "") != "opening_music":
            continue
        if int(clip.get("duration_ms") or 0) > 0:
            return True
    return False


def episode_close_music_required(ctx: Any) -> bool:
    try:
        from interview_mux.information_packages import information_packages_cfg

        return bool(
            (information_packages_cfg().get("episode_close") or {}).get("require_music", True)
        )
    except Exception:
        return True


def reserved_theme_asset_ids(ctx: Any, *, include_omitted: bool = False) -> set[str]:
    """Asset ids that must be generated before mix may reserve their air.

    Includes:
    - non-skipped cues already targeting speech-free roles
    - preferred cold_open when EDL has opening_music (or cold_open cue expected)
    - preferred outro when episode_close requires music

    By default omitted beds are discarded (mix completeness excludes them).
    Pass ``include_omitted=True`` for omit-all ship-bar checks (MSFX-B2).
    """
    ids: set[str] = set()
    sdp = _sdp(ctx)
    by_id = {
        str(a.get("asset_id")): a
        for a in (sdp.get("assets") or [])
        if isinstance(a, dict) and a.get("asset_id")
    }

    for cue in _podcast_cues(sdp):
        if cue.get("skip") is True:
            continue
        aid = str(cue.get("asset_id") or "").strip()
        role = str(cue.get("role") or cue.get("music_role") or "").strip()
        if not aid:
            continue
        if is_speech_free_theme_role(role):
            ids.add(aid)
            continue
        asset = by_id.get(aid) or {}
        if is_speech_free_theme_role(_asset_role(asset)):
            ids.add(aid)

    # Prefer single bookend stems — do not require every motif+bed variant.
    if edl_has_opening_music_reservation(ctx) or any(
        not c.get("skip") and str(c.get("role") or "") == "theme_cold_open"
        for c in _podcast_cues(sdp)
    ):
        open_id = preferred_cold_open_asset_id(ctx)
        if open_id:
            ids.add(open_id)
    elif preferred_cold_open_asset_id(ctx):
        # Palette has a cold_open stem — generate it so music epoch can seed the cue.
        ids.add(str(preferred_cold_open_asset_id(ctx)))

    if episode_close_music_required(ctx):
        close_id = preferred_outro_asset_id(ctx)
        if close_id:
            ids.add(close_id)

    if not include_omitted:
        for aid in music_omitted_asset_ids(ctx):
            ids.discard(aid)
    return ids


def music_omitted_asset_ids(ctx: Any) -> set[str]:
    ids: set[str] = set()
    try:
        if ctx.artifact_exists("operator/music_omitted.json"):
            doc = ctx.read_json("operator/music_omitted.json")
            for row in (doc.get("omitted") or []) if isinstance(doc, dict) else []:
                if isinstance(row, dict) and row.get("asset_id"):
                    ids.add(str(row["asset_id"]))
    except Exception:
        pass
    try:
        if ctx.artifact_exists("run_meta.json"):
            meta = ctx.read_json("run_meta.json")
            if isinstance(meta, dict):
                for aid in meta.get("music_omitted_asset_ids") or []:
                    if aid:
                        ids.add(str(aid))
    except Exception:
        pass
    return ids


def reserved_themes_all_omitted(ctx: Any) -> bool:
    """True when creative delivery expects theme beds and every reserved id is omitted.

    Clinic MSFX-B2: omit-all is not ship-legal under creative_delivery — callers
    must fail delight / block mix (honest fail, not hollow ship).
    """
    try:
        from interview_mux.creative_delivery import creative_delivery_required

        if not creative_delivery_required():
            return False
    except Exception:
        return False
    planned = reserved_theme_asset_ids(ctx, include_omitted=True)
    if not planned:
        return False
    omitted = music_omitted_asset_ids(ctx)
    return planned <= omitted


def refuse_silent_theme_overlay(
    *,
    role: str | None,
    asset_id: str,
    missing_asset: bool,
    audio: Any | None = None,
) -> str | None:
    """Return error reason when a speech-free overlay would ship silence."""
    if not is_speech_free_theme_role(role):
        return None
    if missing_asset:
        return (
            f"speech-free theme {role!r} asset {asset_id!r} missing — "
            "refusing silent duration (pin mmaudio_sfx)"
        )
    if audio is None:
        return (
            f"speech-free theme {role!r} asset {asset_id!r} has no audio — "
            "refusing silent duration"
        )
    try:
        # pydub: near-silent segments report very low dBFS
        if float(getattr(audio, "dBFS", -90.0)) < -55.0 and len(audio) > 200:
            return (
                f"speech-free theme {role!r} asset {asset_id!r} is near-silent — "
                "refusing silent duration (pin mmaudio_sfx)"
            )
    except Exception:
        pass
    return None


def shrink_theme_reservations_for_omit(ctx: Any, asset_ids: list[str] | set[str]) -> dict[str, Any]:
    """Clear cue + EDL reservations for omitted theme assets (same-write honesty)."""
    aids = {str(a) for a in asset_ids if a}
    out: dict[str, Any] = {
        "asset_ids": sorted(aids),
        "cues_skipped": 0,
        "opening_music_cleared": 0,
        "written": [],
    }
    if not aids:
        return out

    sdp_rel = "understanding/sound_design_plan.json"
    if ctx.artifact_exists(sdp_rel):
        try:
            sdp = ctx.read_json(sdp_rel)
        except Exception:
            sdp = None
        if isinstance(sdp, dict):
            changed = False
            flow = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
            podcast = flow.get("podcast") if isinstance(flow.get("podcast"), dict) else {}
            flow_cues = list(podcast.get("cues") or [])
            for cue in flow_cues:
                if not isinstance(cue, dict):
                    continue
                if str(cue.get("asset_id") or "") not in aids:
                    continue
                cue["skip"] = True
                cue["preserve_full_duration"] = False
                out["cues_skipped"] += 1
                changed = True
            top = list(sdp.get("cues") or []) if isinstance(sdp.get("cues"), list) else []
            for cue in top:
                if not isinstance(cue, dict):
                    continue
                if str(cue.get("asset_id") or "") not in aids:
                    continue
                cue["skip"] = True
                cue["preserve_full_duration"] = False
                out["cues_skipped"] += 1
                changed = True
            if changed:
                podcast = dict(podcast)
                podcast["cues"] = flow_cues
                flow = dict(flow)
                flow["podcast"] = podcast
                sdp["flow_plans"] = flow
                if top:
                    sdp["cues"] = top
                ctx.write_json(sdp_rel, sdp)
                out["written"].append(sdp_rel)

    # Drop opening_music air when a cold_open asset was omitted.
    cold_omitted = False
    sdp = _sdp(ctx)
    by_id = {
        str(a.get("asset_id")): a
        for a in (sdp.get("assets") or [])
        if isinstance(a, dict) and a.get("asset_id")
    }
    for aid in aids:
        role = _asset_role(by_id.get(aid) or {})
        if role == "theme_cold_open" or "full_bed_open" in aid or "motif" in aid:
            cold_omitted = True
            break
    if cold_omitted and ctx.artifact_exists("master/edl.json"):
        try:
            edl = ctx.read_json("master/edl.json")
        except Exception:
            edl = None
        if isinstance(edl, dict):
            clips = list(edl.get("clips") or [])
            rebuilt: list[Any] = []
            cleared = 0
            for clip in clips:
                if (
                    isinstance(clip, dict)
                    and str(clip.get("air_kind") or "") == "opening_music"
                    and int(clip.get("duration_ms") or 0) > 0
                ):
                    c = dict(clip)
                    c["duration_ms"] = 0
                    c["preserve_planned_music"] = False
                    c["omitted_theme_slot"] = True
                    rebuilt.append(c)
                    cleared += 1
                    continue
                rebuilt.append(clip)
            if cleared:
                edl["clips"] = rebuilt
                ctx.write_json("master/edl.json", edl)
                out["opening_music_cleared"] = cleared
                out["written"].append("master/edl.json")

    return out


def ensure_cold_open_cue(ctx: Any) -> list[str]:
    """Seed a theme_cold_open cue when palette has the asset but cues omit it."""
    written: list[str] = []
    sdp_rel = "understanding/sound_design_plan.json"
    if not ctx.artifact_exists(sdp_rel):
        return written
    try:
        sdp = ctx.read_json(sdp_rel)
    except Exception:
        return written
    if not isinstance(sdp, dict):
        return written

    assets = [a for a in (sdp.get("assets") or []) if isinstance(a, dict)]
    open_asset = None
    for a in assets:
        if _asset_role(a) != "theme_cold_open":
            continue
        # Prefer full_bed_open over motif.
        if open_asset is None:
            open_asset = a
        if "full_bed" in str(a.get("asset_id") or "").lower():
            open_asset = a
            break
    if open_asset is None:
        return written

    cues = _podcast_cues(sdp)
    has_open = any(
        not c.get("skip")
        and (
            str(c.get("role") or "") == "theme_cold_open"
            or str(c.get("asset_id") or "") == str(open_asset.get("asset_id"))
        )
        for c in cues
    )
    if has_open:
        return written

    first = ""
    if ctx.artifact_exists("master/selection.json"):
        try:
            sel = ctx.read_json("master/selection.json")
            ordered = [str(x) for x in (sel.get("ordered_segment_ids") or []) if x]
            first = ordered[0] if ordered else ""
        except Exception:
            first = ""

    cue = {
        "cue_id": "theme_cold_open_seed",
        "role": "theme_cold_open",
        "asset_id": str(open_asset.get("asset_id") or ""),
        "placement": "before_segment",
        "level_db": -10,
        "preserve_full_duration": True,
        "skip": False,
    }
    if first:
        cue["before_segment_id"] = first
        cue["segment_id"] = first

    flow = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    podcast = flow.get("podcast") if isinstance(flow.get("podcast"), dict) else {}
    flow_cues = list(podcast.get("cues") or [])
    flow_cues.insert(0, cue)
    podcast = dict(podcast)
    podcast["cues"] = flow_cues
    flow = dict(flow)
    flow["podcast"] = podcast
    sdp["flow_plans"] = flow
    ctx.write_json(sdp_rel, sdp)
    written.append(sdp_rel)
    return written


def ensure_theme_bookend_cues(ctx: Any) -> list[str]:
    """Music-epoch: ensure cold_open + outro cues exist (create allowed)."""
    written: list[str] = []
    written.extend(ensure_cold_open_cue(ctx))
    try:
        from interview_mux.listen_quality import place_episode_close_cue

        written.extend(place_episode_close_cue(ctx, allow_create=True))
    except TypeError:
        # Older signature without allow_create.
        from interview_mux.listen_quality import place_episode_close_cue

        written.extend(place_episode_close_cue(ctx))
    except Exception:
        pass
    return written


def assert_theme_bookends_ready_for_mix(ctx: Any) -> None:
    """Fail closed when mix would invent or pad speech-free theme air."""
    omitted = music_omitted_asset_ids(ctx)
    required = reserved_theme_asset_ids(ctx)
    # MSFX-B2: omit-all under creative_delivery is not ship-legal.
    if reserved_themes_all_omitted(ctx):
        planned = reserved_theme_asset_ids(ctx, include_omitted=True)
        raise RuntimeError(
            "mix: all reserved theme beds omitted (omit-all) — not ship-legal "
            "under creative_delivery; regenerate MusicGen beds or remutate "
            "sonic_weave (honest fail, not hollow ship): "
            + ", ".join(sorted(planned)[:8])
        )
    missing = sorted(a for a in required if a not in omitted and not theme_asset_audible(ctx, a))
    if missing:
        raise RuntimeError(
            "mix: speech-free theme WAV(s) missing/inaudible — pin mmaudio_sfx: "
            + ", ".join(missing[:8])
        )

    if episode_close_music_required(ctx):
        sdp = _sdp(ctx)
        has_outro_asset = any(
            isinstance(a, dict) and _asset_role(a) == "theme_outro"
            for a in (sdp.get("assets") or [])
        )
        has_outro_cue = any(
            not c.get("skip")
            and (
                str(c.get("role") or "") == "theme_outro"
                or "outro" in str(c.get("cue_id") or "").lower()
            )
            for c in _podcast_cues(sdp)
        )
        # Asset planned but cue never seeded in music epoch — do not invent at mix.
        if has_outro_asset and not has_outro_cue:
            # If all outro assets omitted, OK only when creative_delivery is off
            # (omit-all already refused above when creative required).
            outro_ids = {
                str(a.get("asset_id"))
                for a in (sdp.get("assets") or [])
                if isinstance(a, dict) and _asset_role(a) == "theme_outro" and a.get("asset_id")
            }
            if outro_ids - omitted:
                raise RuntimeError(
                    "mix: theme_outro cue missing — place in music epoch "
                    "(music_palette_compose / place_episode_close_cue), not at mix"
                )

    if edl_has_opening_music_reservation(ctx):
        open_id = preferred_cold_open_asset_id(ctx)
        live = ({open_id} if open_id else set()) - omitted
        if live and not any(theme_asset_audible(ctx, a) for a in live):
            raise RuntimeError(
                "mix: opening_music reserved but no audible theme_cold_open WAV — "
                "pin mmaudio_sfx"
            )


def hollow_opening_music_finding(ctx: Any) -> dict[str, Any] | None:
    """Junction/delight: opening_music with no audible cold_open is critical."""
    if not edl_has_opening_music_reservation(ctx):
        return None
    omitted = music_omitted_asset_ids(ctx)
    open_id = preferred_cold_open_asset_id(ctx)
    live = ({open_id} if open_id else set()) - omitted
    if not live:
        return None
    if any(theme_asset_audible(ctx, a) for a in live):
        return None
    return {
        "code": "hollow_opening_music",
        "severity": "critical",
        "kind": "hollow_opening_music",
        "action": "regenerate_theme_cold_open",
        "evidence": "opening_music reserved without audible theme_cold_open WAV",
        "detail": {"asset_ids": sorted(live)[:8]},
    }
