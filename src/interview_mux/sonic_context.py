"""BUILD-SFX-02: derive `understanding/sonic_context.json` from analysis artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from interview_mux.config import merged_config
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext

SONIC_CONTEXT_PATH = "understanding/sonic_context.json"
_ATLAS_BUCKETS = frozenset(
    {
        "one_on_one",
        "panel",
        "fireside",
        "technical_deep_dive",
        "media_profile",
        "debate",
        "noisy_room",
        "dense_jargon",
        "trauma_adjacent",
    }
)
_TRAUMA_WORDS = (
    "trauma",
    "grief",
    "violence",
    "assault",
    "abuse",
    "death",
    "loss",
    "bereavement",
    "ptsd",
    "suicide",
    "self-harm",
)
_JARGON_WORDS = (
    "api",
    "sdk",
    "latency",
    "throughput",
    "vector",
    "llm",
    "model",
    "schema",
    "kubernetes",
    "inference",
    "compliance",
)
_SCENARIO_BANS: dict[str, list[str]] = {
    "one_on_one": ["no overproduced trailer hits", "avoid comedic one-shots over emotional disclosures"],
    "panel": ["avoid continuous busy beds under crosstalk", "no sharp stingers during multi-speaker overlap"],
    "fireside": ["no aggressive percussion", "avoid jump-scare rises"],
    "technical_deep_dive": ["avoid cinematic drama cues", "no novelty/cartoon SFX"],
    "media_profile": ["avoid sensational tabloid cues", "no ironic comedic stabs"],
    "debate": ["avoid conflict-escalating impacts", "no sarcasm-coded comedic effects"],
    "noisy_room": ["avoid dense masking beds", "no bright broadband risers over speech"],
    "dense_jargon": ["avoid lyrical or harmonically busy beds", "no rapid-fire transition stacks"],
    "trauma_adjacent": ["no playful/comedic motifs", "avoid abrupt loud transients"],
}

SCENARIO_POSTURE: dict[str, dict[str, Any]] = {
    "one_on_one": {
        "bed_density": "sparse",
        "stinger_cap_per_minute": 1.5,
        "adaptive_max_assets_flow1": 5,
        "adaptive_max_assets_flow2": 3,
    },
    "panel": {
        "bed_density": "minimal",
        "stinger_cap_per_minute": 1.0,
        "adaptive_max_assets_flow1": 4,
        "adaptive_max_assets_flow2": 3,
    },
    "fireside": {
        "bed_density": "minimal",
        "stinger_cap_per_minute": 1.0,
        "adaptive_max_assets_flow1": 4,
        "adaptive_max_assets_flow2": 2,
    },
    "technical_deep_dive": {
        "bed_density": "none",
        "stinger_cap_per_minute": 0.5,
        "adaptive_max_assets_flow1": 3,
        "adaptive_max_assets_flow2": 2,
    },
    "media_profile": {
        "bed_density": "sparse",
        "stinger_cap_per_minute": 1.2,
        "adaptive_max_assets_flow1": 4,
        "adaptive_max_assets_flow2": 3,
    },
    "debate": {
        "bed_density": "none",
        "stinger_cap_per_minute": 0.4,
        "adaptive_max_assets_flow1": 3,
        "adaptive_max_assets_flow2": 2,
    },
    "noisy_room": {
        "bed_density": "none",
        "stinger_cap_per_minute": 0.0,
        "adaptive_max_assets_flow1": 2,
        "adaptive_max_assets_flow2": 1,
    },
    "dense_jargon": {
        "bed_density": "minimal",
        "stinger_cap_per_minute": 0.8,
        "adaptive_max_assets_flow1": 3,
        "adaptive_max_assets_flow2": 2,
    },
    "trauma_adjacent": {
        "bed_density": "none",
        "stinger_cap_per_minute": 0.0,
        "adaptive_max_assets_flow1": 2,
        "adaptive_max_assets_flow2": 1,
    },
}


_FLOW2_CROSSFADE_MS: dict[str, int] = {
    "media_profile": 80,
    "fireside": 180,
    "one_on_one": 120,
    "panel": 100,
    "technical_deep_dive": 140,
    "debate": 90,
    "noisy_room": 100,
    "dense_jargon": 130,
    "trauma_adjacent": 160,
}


def _read_if_dict(ctx: RunContext, rel: str) -> dict[str, Any] | None:
    if not ctx.artifact_exists(rel):
        return None
    raw = ctx.read_json(rel)
    return raw if isinstance(raw, dict) else None


def _slug(value: Any, *, fallback: str = "tag") -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return text or fallback


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for v in values:
        s = str(v or "").strip()
        if s:
            out.append(s)
    return out


def _segment_bounds(manifest: dict[str, Any] | None) -> list[tuple[str, int, int]]:
    if not isinstance(manifest, dict):
        return []
    out: list[tuple[str, int, int]] = []
    for seg in manifest.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        sid = str(seg.get("segment_id") or "").strip()
        if not sid:
            continue
        start_ms = seg.get("start_ms")
        end_ms = seg.get("end_ms")
        if start_ms is None and seg.get("start_time") is not None:
            start_ms = float(seg.get("start_time") or 0) * 1000.0
        if end_ms is None and seg.get("end_time") is not None:
            end_ms = float(seg.get("end_time") or 0) * 1000.0
        if start_ms is None or end_ms is None:
            continue
        out.append((sid, int(float(start_ms)), int(float(end_ms))))
    out.sort(key=lambda x: x[1])
    return out


def _segment_for_ms(bounds: list[tuple[str, int, int]], t_ms: int) -> str | None:
    for sid, start, end in bounds:
        if start <= t_ms < end:
            return sid
    return None


def _text_blob(ctx: RunContext) -> str:
    brief = _read_if_dict(ctx, "understanding/content_brief.json") or {}
    state = _read_if_dict(ctx, "understanding/analysis_state.json") or {}
    text_parts = [
        json.dumps(brief, ensure_ascii=False),
        json.dumps(state.get("style") or {}, ensure_ascii=False),
        json.dumps(state.get("narrative") or {}, ensure_ascii=False),
    ]
    return " ".join(text_parts).lower()


def classify_atlas_bucket(ctx: RunContext) -> str:
    brief = _read_if_dict(ctx, "understanding/content_brief.json") or {}
    state = _read_if_dict(ctx, "understanding/analysis_state.json") or {}
    sap = _read_if_dict(ctx, "understanding/source_acoustic_profile.json") or {}
    manifest = _read_if_dict(ctx, "segments/manifest.json") or {}

    style = state.get("style") if isinstance(state.get("style"), dict) else {}
    format_class = str(style.get("format_class") or "").strip()
    if not format_class and ctx.artifact_exists("understanding/speakers.json"):
        spk_doc = _read_if_dict(ctx, "understanding/speakers.json") or {}
        profile = spk_doc.get("conversation_profile") if isinstance(spk_doc.get("conversation_profile"), dict) else {}
        format_class = str(profile.get("format_class_candidate") or "").strip()
    overlap_proxy = float(((sap.get("pacing") or {}).get("overlap_proxy")) or 0.0)
    room_hint = str(((sap.get("energy") or {}).get("room_timbre_hint")) or "").lower()
    segs = [s for s in (manifest.get("segments") or []) if isinstance(s, dict)]
    seg_count = len(segs)
    crosstalk_count = sum(
        1
        for s in segs
        if "heavy_crosstalk" in _string_list(s.get("flags"))
        or ("crosstalk" in " ".join(_string_list(s.get("topic_tags"))).lower())
    )
    crosstalk_ratio = (crosstalk_count / seg_count) if seg_count else 0.0
    interviewee_count = len(
        {
            str(s.get("speaker_id"))
            for s in segs
            if str(s.get("speaker_role") or "") == "interviewee" and s.get("speaker_id")
        }
    )

    all_tags: list[str] = []
    for s in segs:
        all_tags.extend(_string_list(s.get("topic_tags")))
    for t in brief.get("topics") or []:
        if isinstance(t, dict):
            all_tags.append(str(t.get("name") or ""))
    tag_text = " ".join(all_tags).lower()
    jargon_hits = sum(1 for word in _JARGON_WORDS if word in tag_text)

    blob = _text_blob(ctx)
    trauma_hits = sum(1 for word in _TRAUMA_WORDS if word in blob)
    if trauma_hits >= 2:
        return "trauma_adjacent"
    if overlap_proxy >= 0.24 or crosstalk_ratio >= 0.15 or "roomy" in room_hint:
        return "noisy_room"
    if jargon_hits >= 3:
        return "dense_jargon"
    if interviewee_count >= 3:
        return "panel"
    if "debate" in blob or "argue" in blob or "disagree" in blob:
        return "debate"
    if format_class in _ATLAS_BUCKETS:
        return format_class
    if "profile" in blob or "biography" in blob:
        return "media_profile"
    if "technical" in blob or "deep dive" in blob:
        return "technical_deep_dive"
    return "one_on_one"


def build_tag_registry(ctx: RunContext) -> list[dict[str, Any]]:
    brief = _read_if_dict(ctx, "understanding/content_brief.json") or {}
    state = _read_if_dict(ctx, "understanding/analysis_state.json") or {}
    manifest = _read_if_dict(ctx, "segments/manifest.json") or {}
    sap = _read_if_dict(ctx, "understanding/source_acoustic_profile.json") or {}

    tags_by_id: dict[str, dict[str, Any]] = {}

    def upsert(
        *,
        tag_id: str,
        kind: str,
        keywords: list[str],
        provenance: list[str],
        segment_ids: list[str] | None = None,
        emotional_valence: str | None = None,
        confidence: float | None = None,
    ) -> None:
        if not tag_id or not keywords:
            return
        row = tags_by_id.get(tag_id)
        if row is None:
            row = {
                "tag_id": tag_id,
                "kind": kind,
                "keywords": sorted({k for k in keywords if k}),
                "segment_ids": sorted({s for s in (segment_ids or []) if s}),
                "provenance": sorted({p for p in provenance if p}),
            }
            if emotional_valence:
                row["emotional_valence"] = emotional_valence
            if confidence is not None:
                row["confidence"] = round(float(confidence), 3)
            tags_by_id[tag_id] = row
            return
        row["keywords"] = sorted(set(_string_list(row.get("keywords")) + keywords))
        row["segment_ids"] = sorted(set(_string_list(row.get("segment_ids")) + (segment_ids or [])))
        row["provenance"] = sorted(set(_string_list(row.get("provenance")) + provenance))
        if confidence is not None:
            prior = row.get("confidence")
            row["confidence"] = round(max(float(prior or 0.0), float(confidence)), 3)
        if emotional_valence and not row.get("emotional_valence"):
            row["emotional_valence"] = emotional_valence

    for topic in brief.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        name = str(topic.get("name") or "").strip()
        if not name:
            continue
        upsert(
            tag_id=f"topic_{_slug(name)}",
            kind="topic",
            keywords=[name],
            segment_ids=_string_list(topic.get("segment_ids")),
            confidence=topic.get("confidence"),
            provenance=["content_brief.topics"],
        )

    entities = brief.get("entities")
    if not isinstance(entities, list):
        entities = state.get("entities") or []
    for entity in entities:
        if isinstance(entity, dict):
            name = str(entity.get("name") or entity.get("entity") or "").strip()
            segs = _string_list(entity.get("segment_ids"))
        else:
            name = str(entity or "").strip()
            segs = []
        if not name:
            continue
        upsert(
            tag_id=f"entity_{_slug(name)}",
            kind="entity",
            keywords=[name],
            segment_ids=segs,
            confidence=0.7,
            provenance=["content_brief.entities_or_analysis_state.entities"],
        )

    for idx, beat in enumerate(brief.get("emotional_beats") or []):
        if isinstance(beat, dict):
            label = str(beat.get("beat") or beat.get("label") or beat.get("name") or "").strip()
            valence = str(beat.get("valence") or "").strip() or None
            segs = _string_list(beat.get("segment_ids"))
        else:
            label = str(beat or "").strip()
            valence = None
            segs = []
        if not label:
            continue
        upsert(
            tag_id=f"emotional_{_slug(label, fallback=f'beat_{idx:02d}')}",
            kind="emotional",
            keywords=[label],
            segment_ids=segs,
            emotional_valence=valence,
            confidence=0.72,
            provenance=["content_brief.emotional_beats"],
        )

    for theme in state.get("themes") or []:
        if not isinstance(theme, dict):
            continue
        label = str(theme.get("label") or theme.get("id") or "").strip()
        if not label:
            continue
        upsert(
            tag_id=f"theme_{_slug(theme.get('id') or label)}",
            kind="theme",
            keywords=[label],
            segment_ids=_string_list(theme.get("segment_ids")),
            confidence=theme.get("confidence", 0.75),
            provenance=["analysis_state.themes"],
        )

    for seg in manifest.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        sid = str(seg.get("segment_id") or "").strip()
        for raw in _string_list(seg.get("topic_tags")):
            upsert(
                tag_id=f"topic_{_slug(raw)}",
                kind="topic",
                keywords=[raw],
                segment_ids=[sid] if sid else [],
                confidence=0.6,
                provenance=["segments.manifest.topic_tags"],
            )

    pace = str(((sap.get("pacing") or {}).get("pace_class")) or "").strip()
    room = str(((sap.get("energy") or {}).get("room_timbre_hint")) or "").strip()
    acoustic_keywords = [k for k in (pace, room) if k]
    if acoustic_keywords:
        upsert(
            tag_id=f"acoustic_{_slug('_'.join(acoustic_keywords), fallback='profile')}",
            kind="acoustic",
            keywords=acoustic_keywords,
            confidence=0.85,
            provenance=["source_acoustic_profile"],
        )

    return sorted(tags_by_id.values(), key=lambda x: str(x.get("tag_id")))


def _cue_segment_fields(segment_id: str | None) -> dict[str, str]:
    """Schema allows omitted segment_id; never emit null."""
    cleaned = str(segment_id or "").strip()
    return {"segment_id": cleaned} if cleaned else {}


def build_cue_opportunities(ctx: RunContext) -> list[dict[str, Any]]:
    narrative = _read_if_dict(ctx, "master/narrative_plan.json") or {}
    gap_report = _read_if_dict(ctx, "understanding/gap_report.json") or {}
    value_features = _read_if_dict(ctx, "understanding/value_features.json") or {}
    brief = _read_if_dict(ctx, "understanding/content_brief.json") or {}
    manifest = _read_if_dict(ctx, "segments/manifest.json") or {}

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, int]] = set()
    bounds = _segment_bounds(manifest)

    def add(row: dict[str, Any]) -> None:
        kind = str(row.get("kind") or "")
        sid = str(row.get("segment_id") or "")
        start = int(row.get("start_ms") or -1)
        end = int(row.get("end_ms") or -1)
        key = (kind, sid, start, end)
        if kind and key not in seen:
            seen.add(key)
            stored = dict(row)
            if not sid:
                stored.pop("segment_id", None)
            out.append(stored)

    chapters = [c for c in (narrative.get("chapters") or []) if isinstance(c, dict)]
    for idx, chapter in enumerate(chapters):
        sid = str(chapter.get("suggested_open_segment_id") or "").strip()
        add(
            {
                "kind": "chapter_boundary",
                **_cue_segment_fields(sid),
                "beat": str(chapter.get("title") or chapter.get("chapter_id") or f"chapter_{idx + 1}"),
                "confidence": 0.78,
                "provenance": ["master/narrative_plan.json"],
            }
        )
    if chapters:
        first_sid = str(chapters[0].get("suggested_open_segment_id") or "").strip()
        last_sid = str(chapters[-1].get("suggested_open_segment_id") or "").strip()
        add({"kind": "cold_open", **_cue_segment_fields(first_sid), "confidence": 0.64, "provenance": ["narrative_plan"]})
        add({"kind": "outro", **_cue_segment_fields(last_sid), "confidence": 0.64, "provenance": ["narrative_plan"]})

    for line in gap_report.get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        sid = str(line.get("targets_segment_id") or "").strip()
        add(
            {
                "kind": "vo_bridge",
                **_cue_segment_fields(sid),
                "beat": str(line.get("gap_type") or "bridge"),
                "confidence": 0.81,
                "provenance": ["understanding/gap_report.json"],
            }
        )

    transcript_profile = (value_features.get("profiles") or {}).get("transcript")
    if isinstance(transcript_profile, dict):
        for flag in transcript_profile.get("quality_trajectory_flags") or []:
            if not isinstance(flag, dict):
                continue
            start_ms = int(flag.get("start_ms") or 0)
            sid = _segment_for_ms(bounds, start_ms)
            add(
                {
                    "kind": "tension_peak",
                    **_cue_segment_fields(sid),
                    "start_ms": start_ms,
                    "confidence": 0.62,
                    "provenance": ["understanding/value_features.json"],
                }
            )

    for beat in brief.get("emotional_beats") or []:
        if isinstance(beat, dict):
            label = str(beat.get("beat") or beat.get("label") or beat.get("name") or "").strip()
            seg_ids = _string_list(beat.get("segment_ids"))
        else:
            label = str(beat or "").strip()
            seg_ids = []
        if not label:
            continue
        sid = seg_ids[0] if seg_ids else None
        lower = label.lower()
        kind = "laughter_window" if "laugh" in lower else "emotional_beat"
        add(
            {
                "kind": kind,
                **_cue_segment_fields(sid),
                "beat": label,
                "confidence": 0.74,
                "provenance": ["understanding/content_brief.json"],
            }
        )

    return out


def build_segment_flags(ctx: RunContext) -> dict[str, list[str]]:
    sap = _read_if_dict(ctx, "understanding/source_acoustic_profile.json") or {}
    brief = _read_if_dict(ctx, "understanding/content_brief.json") or {}
    state = _read_if_dict(ctx, "understanding/analysis_state.json") or {}
    manifest = _read_if_dict(ctx, "segments/manifest.json") or {}
    disfluencies = _read_if_dict(ctx, "transcript/disfluencies.json") or {}
    value_features = _read_if_dict(ctx, "understanding/value_features.json") or {}
    bounds = _segment_bounds(manifest)

    overlap_high: set[str] = set()
    trauma_adjacent: set[str] = set()
    jargon_dense: set[str] = set()
    disfluency_restore: set[str] = set()
    comprehension_risk: set[str] = set()

    overlap_proxy = float(((sap.get("pacing") or {}).get("overlap_proxy")) or 0.0)
    segments = [s for s in (manifest.get("segments") or []) if isinstance(s, dict)]

    prev_end = -1
    for seg in segments:
        sid = str(seg.get("segment_id") or "").strip()
        if not sid:
            continue
        flags = {f.lower() for f in _string_list(seg.get("flags"))}
        tags_l = {t.lower() for t in _string_list(seg.get("topic_tags"))}

        start_ms = seg.get("start_ms")
        end_ms = seg.get("end_ms")
        if start_ms is None and seg.get("start_time") is not None:
            start_ms = float(seg.get("start_time") or 0) * 1000.0
        if end_ms is None and seg.get("end_time") is not None:
            end_ms = float(seg.get("end_time") or 0) * 1000.0
        start_i = int(float(start_ms)) if start_ms is not None else 0
        end_i = int(float(end_ms)) if end_ms is not None else start_i

        if overlap_proxy >= 0.2 or "heavy_crosstalk" in flags or start_i < prev_end:
            overlap_high.add(sid)
        prev_end = max(prev_end, end_i)

        if any(w in " ".join(tags_l) for w in _TRAUMA_WORDS):
            trauma_adjacent.add(sid)
        if any(w in " ".join(tags_l) for w in _JARGON_WORDS):
            jargon_dense.add(sid)

    trauma_blob = json.dumps(
        {
            "beats": brief.get("emotional_beats"),
            "operator_notes": state.get("operator_notes"),
            "style_notes": (state.get("style") or {}).get("sound_design_notes"),
        },
        ensure_ascii=False,
    ).lower()
    if any(word in trauma_blob for word in _TRAUMA_WORDS):
        for sid, _start, _end in bounds[: min(3, len(bounds))]:
            trauma_adjacent.add(sid)

    for ev in disfluencies.get("events") or []:
        if not isinstance(ev, dict):
            continue
        if str(ev.get("review_status") or "") != "confirmed":
            continue
        if ev.get("include_in_restore") is False:
            continue
        sid = str(ev.get("segment_id") or "").strip()
        if not sid and ev.get("start_ms") is not None:
            sid = _segment_for_ms(bounds, int(ev.get("start_ms") or 0)) or ""
        if sid:
            disfluency_restore.add(sid)

    transcript_profile = (value_features.get("profiles") or {}).get("transcript")
    if isinstance(transcript_profile, dict):
        from interview_mux.stage_enrichment import trust_dip_corroborated

        for row in transcript_profile.get("quality_trajectory_flags") or []:
            if not isinstance(row, dict):
                continue
            t_ms = int(row.get("start_ms") or 0)
            dip_ratio = float(row.get("dip_ratio") or 1.0)
            if not trust_dip_corroborated(ctx, t_ms, dip_ratio=dip_ratio):
                continue
            sid = _segment_for_ms(bounds, t_ms)
            if sid:
                comprehension_risk.add(sid)

    return {
        "overlap_high": sorted(overlap_high),
        "trauma_adjacent": sorted(trauma_adjacent),
        "jargon_dense": sorted(jargon_dense),
        "disfluency_restore": sorted(disfluency_restore),
        "comprehension_risk": sorted(comprehension_risk),
    }


def build_avoid_hard(ctx: RunContext) -> list[str]:
    state = _read_if_dict(ctx, "understanding/analysis_state.json") or {}
    style = state.get("style") if isinstance(state.get("style"), dict) else {}
    notes = str(style.get("sound_design_notes") or "").strip()
    bucket = classify_atlas_bucket(ctx)
    out: list[str] = []
    if notes:
        out.append(notes[:240])
    out.extend(_SCENARIO_BANS.get(bucket, []))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in out:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def _episode_minutes(ctx: RunContext) -> float:
    manifest = _read_if_dict(ctx, "segments/manifest.json") or {}
    max_end = 0
    for seg in manifest.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        end_ms = seg.get("end_ms")
        if end_ms is None and seg.get("end_time") is not None:
            end_ms = float(seg.get("end_time") or 0) * 1000.0
        if end_ms is not None:
            max_end = max(max_end, int(float(end_ms)))
    if max_end > 0:
        return max_end / 60000.0
    transcript = _read_if_dict(ctx, "transcript/full.json") or {}
    words = [w for w in (transcript.get("words") or []) if isinstance(w, dict)]
    if words:
        end = max(int(float(w.get("end_ms") or 0)) for w in words)
        return end / 60000.0
    return 0.0


def compute_mix_policy(ctx: RunContext, atlas_bucket: str) -> dict[str, Any]:
    cfg = merged_config()
    sap = _read_if_dict(ctx, "understanding/source_acoustic_profile.json") or {}
    posture = SCENARIO_POSTURE.get(atlas_bucket, SCENARIO_POSTURE["one_on_one"])
    sound_design_cfg = cfg.get("sound_design") or {}
    mmaudio_cfg = cfg.get("mmaudio") or {}

    underscore = str(((sap.get("mix_contract") or {}).get("underscore_policy")) or "normal")
    if underscore not in {"normal", "sparse", "skip"}:
        underscore = "normal"
    overlap_proxy = float(((sap.get("pacing") or {}).get("overlap_proxy")) or 0.0)
    if underscore == "sparse" and overlap_proxy >= 0.2:
        underscore_policy = "sparse_or_skip"
    else:
        underscore_policy = underscore

    duration_min = _episode_minutes(ctx)
    duration_bump = int(duration_min // 30.0)
    max_f1 = int(sound_design_cfg.get("max_assets_flow1", posture["adaptive_max_assets_flow1"]))
    max_f2 = int(sound_design_cfg.get("max_assets_flow2", posture["adaptive_max_assets_flow2"]))
    adaptive_f1 = min(max_f1, int(posture["adaptive_max_assets_flow1"]) + duration_bump)
    adaptive_f2 = min(max_f2, int(posture["adaptive_max_assets_flow2"]) + duration_bump)

    duration_bands = mmaudio_cfg.get("duration_bands_by_role")
    if not isinstance(duration_bands, dict) or not duration_bands:
        mn = float(mmaudio_cfg.get("min_duration_sec", 3.0))
        mx = float(mmaudio_cfg.get("max_duration_sec", 8.0))
        duration_bands = {
            "ambient_bed": [max(0.1, mn + 2.0), max(mx, mn + 3.0)],
            "chapter_stinger": [max(0.1, mn - 1.0), max(mx - 1.0, mn)],
            "transition_stinger": [max(0.1, mn - 1.0), max(mx - 2.0, mn)],
            "cold_open": [max(0.1, mn), max(mx, mn + 1.0)],
            "vo_bridge": [max(0.1, mn), max(mx - 1.5, mn + 0.5)],
            "accent_foley": [max(0.1, mn - 1.0), max(mx - 3.0, mn)],
        }

    normalized_bands: dict[str, list[float]] = {}
    for role, band in duration_bands.items():
        if not isinstance(band, list) or len(band) != 2:
            continue
        lo = max(0.1, float(band[0]))
        hi = max(lo, float(band[1]))
        normalized_bands[str(role)] = [round(lo, 2), round(hi, 2)]

    mix_cfg = cfg.get("mix") or {}
    default_crossfade = int(mix_cfg.get("crossfade_ms_flow2", 120))
    crossfade_ms_flow2 = int(_FLOW2_CROSSFADE_MS.get(atlas_bucket, default_crossfade))

    return {
        "underscore_policy": underscore_policy,
        "adaptive_max_assets_flow1": max(0, adaptive_f1),
        "adaptive_max_assets_flow2": max(0, adaptive_f2),
        "stinger_cap_per_minute": float(posture["stinger_cap_per_minute"]),
        "duration_bands_by_role": normalized_bands,
        "crossfade_ms_flow2": crossfade_ms_flow2,
    }


def compute_sonic_context_hash(doc: dict[str, Any]) -> str:
    payload = dict(doc)
    payload.pop("sonic_context_hash", None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def compact_for_volley(doc: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(doc, dict):
        return {}
    scenario = doc.get("scenario") if isinstance(doc.get("scenario"), dict) else {}
    mix = doc.get("mix_policy") if isinstance(doc.get("mix_policy"), dict) else {}
    seed = doc.get("sonic_identity_seed") if isinstance(doc.get("sonic_identity_seed"), dict) else {}
    tags = [t for t in (doc.get("tag_registry") or []) if isinstance(t, dict)]
    cues = [c for c in (doc.get("cue_opportunities") or []) if isinstance(c, dict)]
    return {
        "sonic_context_hash": doc.get("sonic_context_hash"),
        "atlas_bucket": scenario.get("atlas_bucket"),
        "sound_posture": scenario.get("sound_posture"),
        "sonic_identity_seed": {
            "primary_mood": seed.get("primary_mood"),
            "density_hint": seed.get("density_hint"),
            "room_character": seed.get("room_character"),
        },
        "top_tag_ids": [str(t.get("tag_id")) for t in tags[:12] if t.get("tag_id")],
        "cue_kinds": [str(c.get("kind")) for c in cues[:12] if c.get("kind")],
        "mix_policy": {
            "underscore_policy": mix.get("underscore_policy"),
            "adaptive_max_assets_flow1": mix.get("adaptive_max_assets_flow1"),
            "adaptive_max_assets_flow2": mix.get("adaptive_max_assets_flow2"),
            "stinger_cap_per_minute": mix.get("stinger_cap_per_minute"),
            "crossfade_ms_flow2": mix.get("crossfade_ms_flow2"),
        },
        "avoid_hard": _string_list(doc.get("avoid_hard"))[:8],
        "segment_flags": doc.get("segment_flags") or {},
    }


def build_palette_keyword_catalog(doc: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Exact tag_registry rows palettes must ground keywords against (BUILD-SFX)."""
    if not isinstance(doc, dict):
        return []
    catalog: list[dict[str, Any]] = []
    for row in doc.get("tag_registry") or []:
        if not isinstance(row, dict):
            continue
        keywords = [str(k).strip() for k in (row.get("keywords") or []) if str(k).strip()]
        if not keywords:
            continue
        catalog.append(
            {
                "tag_id": str(row.get("tag_id") or ""),
                "kind": str(row.get("kind") or ""),
                "keywords": keywords,
                "segment_ids": _string_list(row.get("segment_ids")),
                "provenance": _string_list(row.get("provenance")),
            }
        )
    return catalog


def sonic_provenance_keyword_set(doc: dict[str, Any] | None) -> set[str]:
    """Lowercased keyword tokens accepted for palette provenance lint."""
    if not isinstance(doc, dict):
        return set()
    out: set[str] = set()
    for row in doc.get("tag_registry") or []:
        if not isinstance(row, dict):
            continue
        tag_id = str(row.get("tag_id") or "").strip().lower()
        if tag_id:
            out.add(tag_id)
        for keyword in row.get("keywords") or []:
            token = str(keyword or "").strip().lower()
            if token:
                out.add(token)
    return out


def _keyword_tokens(value: str) -> set[str]:
    import re

    low = value.strip().lower()
    if not low:
        return set()
    tokens = set(re.findall(r"[a-z0-9]+", low))
    tokens.add(low)
    return tokens


_STOP_TOKENS = frozenset({"and", "or", "the", "a", "an", "to", "of", "in", "for", "on", "at", "with"})


def palette_keyword_matches_sonic_provenance(keyword: str, sonic_keywords: set[str]) -> bool:
    """True when a palette keyword traces to sonic_context tag_registry."""
    kw = str(keyword or "").strip().lower()
    if not kw or not sonic_keywords:
        return False
    if kw in sonic_keywords:
        return True
    for sk in sonic_keywords:
        if len(kw) >= 4 and (kw in sk or sk in kw):
            return True
    kw_tokens = _keyword_tokens(kw) - _STOP_TOKENS
    if not kw_tokens:
        return False
    for sk in sonic_keywords:
        overlap = kw_tokens & (_keyword_tokens(sk) - _STOP_TOKENS)
        if overlap:
            return True
    return False


def align_palette_keywords_to_sonic_context(
    palettes: list[dict[str, Any]],
    sonic_doc: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Normalize palette keywords/tag_ids from tag_registry segment overlap."""
    if not isinstance(sonic_doc, dict) or not palettes:
        return palettes
    registry = [t for t in (sonic_doc.get("tag_registry") or []) if isinstance(t, dict)]
    if not registry:
        return palettes
    aligned: list[dict[str, Any]] = []
    for pal in palettes:
        if not isinstance(pal, dict):
            continue
        row = dict(pal)
        seg_ids = {str(s) for s in (row.get("segment_ids") or []) if str(s).strip()}
        matched = [
            t
            for t in registry
            if seg_ids & {str(s) for s in (t.get("segment_ids") or []) if str(s).strip()}
        ]
        if not matched and row.get("theme_label"):
            theme_slug = _slug(str(row.get("theme_label") or ""))
            matched = [t for t in registry if theme_slug and theme_slug in str(t.get("tag_id") or "")]
        keywords = [str(k).strip() for k in (row.get("keywords") or []) if str(k).strip()]
        sonic_kw = sonic_provenance_keyword_set(sonic_doc)
        if keywords and any(palette_keyword_matches_sonic_provenance(k, sonic_kw) for k in keywords):
            aligned.append(row)
            continue
        if matched:
            merged_kw: list[str] = []
            tag_ids: list[str] = []
            for tag in matched[:4]:
                tag_ids.append(str(tag.get("tag_id") or ""))
                merged_kw.extend(str(k).strip() for k in (tag.get("keywords") or []) if str(k).strip())
            row["tag_ids"] = sorted({t for t in tag_ids if t})
            row["keywords"] = sorted({k for k in merged_kw if k})[:8] or keywords
        aligned.append(row)
    return aligned


def build_sonic_context(ctx: RunContext) -> dict[str, Any]:
    brief = _read_if_dict(ctx, "understanding/content_brief.json") or {}
    state = _read_if_dict(ctx, "understanding/analysis_state.json") or {}
    sap = _read_if_dict(ctx, "understanding/source_acoustic_profile.json") or {}
    value_features = _read_if_dict(ctx, "understanding/value_features.json") or {}

    style = state.get("style") if isinstance(state.get("style"), dict) else {}
    with logged_step("sonic_context/classify_scenario", ctx=ctx, stage="sonic_context_build"):
        atlas_bucket = classify_atlas_bucket(ctx)
        posture = dict(SCENARIO_POSTURE.get(atlas_bucket, SCENARIO_POSTURE["one_on_one"]))

    with logged_step("sonic_context/build_registry", ctx=ctx, stage="sonic_context_build"):
        tags = build_tag_registry(ctx)
        cues = build_cue_opportunities(ctx)
        flags = build_segment_flags(ctx)
        mix_policy = compute_mix_policy(ctx, atlas_bucket)

    beats = brief.get("emotional_beats") or ((state.get("narrative") or {}).get("emotional_beats") or [])
    primary_mood = ""
    if isinstance(beats, list) and beats:
        if isinstance(beats[0], dict):
            primary_mood = str(beats[0].get("beat") or beats[0].get("label") or beats[0].get("name") or "").strip()
        else:
            primary_mood = str(beats[0]).strip()
    if not primary_mood:
        primary_mood = str(style.get("tone_class") or style.get("tone") or "neutral")

    density_hint = str(posture.get("bed_density") or "minimal")
    if mix_policy.get("underscore_policy") in {"skip", "sparse_or_skip"}:
        density_hint = "minimal_or_none"

    room_character = str(((sap.get("energy") or {}).get("room_timbre_hint")) or "unknown")
    built_from = [
        rel
        for rel in (
            "understanding/content_brief.json",
            "understanding/analysis_state.json",
            "understanding/source_acoustic_profile.json",
            "segments/manifest.json",
            "master/narrative_plan.json",
            "understanding/gap_report.json",
            "understanding/value_features.json",
            "transcript/disfluencies.json",
        )
        if ctx.artifact_exists(rel)
    ]

    doc: dict[str, Any] = {
        "version": 1,
        "built_from": built_from,
        "sparse_mode": len(tags) == 0,
        "scenario": {
            "format_class": str(style.get("format_class") or "unknown"),
            "tone_class": str(style.get("tone_class") or style.get("tone") or "unknown"),
            "atlas_bucket": atlas_bucket,
            "sound_posture": posture,
        },
        "sonic_identity_seed": {
            "primary_mood": primary_mood,
            "density_hint": density_hint,
            "room_character": room_character,
        },
        "tag_registry": tags,
        "cue_opportunities": cues,
        "mix_policy": mix_policy,
        "avoid_hard": build_avoid_hard(ctx),
        "segment_flags": flags,
        "value_features_summary": (value_features.get("profiles") if isinstance(value_features.get("profiles"), dict) else {}),
    }
    with logged_step("sonic_context/finalize_hash", ctx=ctx, stage="sonic_context_build"):
        doc["sonic_context_hash"] = compute_sonic_context_hash(doc)
    return doc


def load_sonic_context(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(SONIC_CONTEXT_PATH):
        return None
    data = ctx.read_json(SONIC_CONTEXT_PATH)
    if not isinstance(data, dict):
        return None
    return data
