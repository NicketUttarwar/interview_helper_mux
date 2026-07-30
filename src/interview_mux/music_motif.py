"""Music-only motif family: roles, bans, music_brief, and MusicGen prompt compile."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.run_context import RunContext

# Creative-delivery show audio — music and undertones only.
THEME_ROLES = frozenset(
    {
        "theme_cold_open",
        "theme_underscore",
        "theme_emphasis",
        "theme_chapter_resolve",
        "theme_outro",
        "theme_transition",
    }
)

THEME_BED_ROLES = frozenset({"theme_underscore"})
THEME_PUNCTUATOR_ROLES = frozenset(
    {"theme_cold_open", "theme_emphasis", "theme_chapter_resolve", "theme_outro", "theme_transition"}
)

# Never ship in creative-delivery show audio.
BANNED_SFX_ROLES = frozenset(
    {
        "chapter_stinger",
        "transition_stinger",
        "ambient_bed",
        "vo_bridge",
        "accent_foley",
        "transition_whoosh",
        "rhetorical_punctuator",
        "era_music_bed",
        "environmental_foley",
        "cold_open",  # legacy SFX cold_open — use theme_cold_open
        "outro",  # legacy — use theme_outro
    }
)

BANNED_TEXTURE_TOKENS = frozenset(
    {
        "woodtick",
        "woodblock",
        "desk tap",
        "desk-tap",
        "click",
        "tick",
        "slap",
        "boing",
        "comic",
        "cartoon",
        "whoosh",
        "riser",
        "trailer",
        "swish",
        "foley",
        "footstep",
        "hvac",
        "fluorescent",
        "murmur",
        "room tone",
        "room-tone",
        "applause",
        "crowd",
        "noise bed",
        "sound effect",
        "sfx",
    }
)

BANNED_ASSET_ID_SUBSTR = (
    "woodtick",
    "murmur",
    "hvac",
    "tick",
    "boing",
    "whoosh",
    "swish",
    "foley",
    "airy_swish",
)

_INSTRUMENT_HINTS = (
    "guitar",
    "piano",
    "strings",
    "violin",
    "cello",
    "bass",
    "keys",
    "synth",
    "pad",
    "flute",
    "horn",
    "trumpet",
    "drums",
    "percussion",
    "harp",
    "ukulele",
    "mandolin",
    "organ",
    "rhodes",
    "instrumental",
    "melody",
    "motif",
    "chord",
    "phrase",
    "underscore",
    "orchestral",
)


def is_theme_role(role: str | None) -> bool:
    return str(role or "").strip() in THEME_ROLES


def is_banned_role(role: str | None) -> bool:
    return str(role or "").strip() in BANNED_SFX_ROLES


def text_has_banned_texture(text: str) -> bool:
    low = (text or "").lower()
    return any(tok in low for tok in BANNED_TEXTURE_TOKENS)


def asset_id_is_banned(asset_id: str) -> bool:
    low = str(asset_id or "").lower()
    return any(s in low for s in BANNED_ASSET_ID_SUBSTR)


def prompt_looks_musical(text: str) -> bool:
    low = (text or "").lower()
    if text_has_banned_texture(low):
        return False
    return any(h in low for h in _INSTRUMENT_HINTS)


def validate_theme_prompt(prompt: str, *, require_dna: str | None = None) -> list[str]:
    """Return list of arbiter failures (empty = ok)."""
    errs: list[str] = []
    p = (prompt or "").strip()
    if len(p) < 24:
        errs.append("prompt_too_short")
    if text_has_banned_texture(p):
        errs.append("banned_texture_language")
    if not prompt_looks_musical(p):
        errs.append("missing_instrument_or_melody_language")
    if require_dna and require_dna.strip() and require_dna.strip().lower() not in p.lower():
        errs.append("missing_prompt_dna")
    return errs


def build_music_brief(ctx: RunContext) -> dict[str, Any]:
    """Pack narrative/sonic/topic context for MusicGen (curated, not full transcripts)."""
    narrative: dict[str, Any] = {}
    if ctx.artifact_exists("master/narrative_plan.json"):
        raw = ctx.read_json("master/narrative_plan.json")
        narrative = raw if isinstance(raw, dict) else {}
    content: dict[str, Any] = {}
    for rel in ("understanding/content_brief.json", "understanding/content_brief_reanchor.json"):
        if ctx.artifact_exists(rel):
            raw = ctx.read_json(rel)
            if isinstance(raw, dict):
                content = raw
                break
    delivery: dict[str, Any] = {}
    if ctx.artifact_exists("understanding/delivery_brief.json"):
        raw = ctx.read_json("understanding/delivery_brief.json")
        delivery = raw if isinstance(raw, dict) else {}
    sonic: dict[str, Any] = {}
    if ctx.artifact_exists("understanding/sonic_context.json"):
        raw = ctx.read_json("understanding/sonic_context.json")
        sonic = raw if isinstance(raw, dict) else {}
    speakers: dict[str, Any] = {}
    if ctx.artifact_exists("understanding/speakers.json"):
        raw = ctx.read_json("understanding/speakers.json")
        speakers = raw if isinstance(raw, dict) else {}
    selection: dict[str, Any] = {}
    if ctx.artifact_exists("master/selection.json"):
        raw = ctx.read_json("master/selection.json")
        selection = raw if isinstance(raw, dict) else {}

    arc = str(narrative.get("arc_summary") or "")[:400]
    chapters = [c for c in (narrative.get("chapters") or []) if isinstance(c, dict)]
    chapter_moods: list[dict[str, Any]] = []
    acts: list[dict[str, Any]] = []
    for i, ch in enumerate(chapters):
        title = str(ch.get("title") or ch.get("label") or f"chapter_{i+1}")
        summary = str(ch.get("summary") or ch.get("purpose") or "")[:180]
        mood = "determined"
        energy = "mid"
        blob = f"{title} {summary}".lower()
        if any(w in blob for w in ("triumph", "win", "payday", "sale", "windfall", "success")):
            mood, energy = "triumphant", "lift"
        elif any(w in blob for w in ("begin", "boot", "start", "early", "scrappy")):
            mood, energy = "hopeful", "calm"
        elif any(w in blob for w in ("crossroad", "tension", "risk", "fear", "struggle")):
            mood, energy = "tense", "rising"
        chapter_moods.append(
            {
                "chapter_id": str(ch.get("chapter_id") or ch.get("id") or f"ch_{i+1}"),
                "title": title,
                "mood": mood,
                "lift_or_calm": "lift" if energy == "lift" else "calm",
            }
        )
        acts.append({"title": title, "mood": mood, "energy": energy, "summary": summary})

    topics: list[str] = []
    for key in ("topics", "theme_tags", "keywords"):
        val = content.get(key)
        if isinstance(val, list):
            topics.extend(str(t) for t in val[:12] if t)
        elif isinstance(val, dict):
            topics.extend(str(k) for k in list(val.keys())[:12])
    topics = [t for t in topics if t][:16]

    quotes: list[str] = []
    if ctx.artifact_exists("segments/manifest.json"):
        man = ctx.read_json("segments/manifest.json")
        segs = (man.get("segments") or []) if isinstance(man, dict) else []
        ordered = [str(s) for s in (selection.get("ordered_segment_ids") or [])]
        by_id = {
            str(r.get("segment_id")): r
            for r in segs
            if isinstance(r, dict) and r.get("segment_id")
        }
        # Sample evenly for evocative short quotes.
        step = max(1, len(ordered) // 6) if ordered else 1
        for sid in ordered[::step][:8]:
            row = by_id.get(sid) or {}
            text = str(row.get("text") or row.get("transcript") or "").strip()
            if len(text) >= 40:
                quotes.append(text[:120].rstrip(" .,;") + ("…" if len(text) > 120 else ""))

    sonic_mood = str(
        ((sonic.get("mix_policy") or {}) if isinstance(sonic.get("mix_policy"), dict) else {}).get(
            "primary_mood"
        )
        or (sonic.get("primary_mood") if isinstance(sonic.get("primary_mood"), str) else "")
        or "determined"
    )
    profile = speakers.get("conversation_profile") if isinstance(speakers.get("conversation_profile"), dict) else {}
    tone = str(profile.get("tone_class_candidate") or "conversational")

    genre_hint = "business documentary instrumental"
    if any("sport" in t.lower() for t in topics):
        genre_hint = "sports documentary instrumental"
    elif any(w in arc.lower() for w in ("family", "grief", "loss", "trauma")):
        genre_hint = "intimate acoustic documentary"

    instrumentation = ["warm acoustic guitar", "soft piano", "subtle low strings"]
    if "lift" in {a.get("energy") for a in acts}:
        instrumentation.append("light brushed pulse")

    payoff_moments: list[dict[str, Any]] = []
    for ch in chapter_moods:
        if ch.get("lift_or_calm") == "lift":
            payoff_moments.append(
                {
                    "segment_id": None,
                    "reason": f"chapter_payoff:{ch.get('title')}",
                    "energy": "lift",
                }
            )

    brief = {
        "version": 1,
        "show_identity": {
            "genre_hint": genre_hint,
            "mood": sonic_mood or "determined",
            "energy": "mid",
            "tone": tone,
            "instrumentation_prefs": instrumentation,
        },
        "narrative_spine": {
            "arc_one_liner": arc or "long-form interview documentary arc",
            "acts": acts,
        },
        "motif_seeds": {
            "keywords": topics[:12],
            "forbidden_textures": sorted(BANNED_TEXTURE_TOKENS),
        },
        "payoff_moments": payoff_moments[:8],
        "chapter_moods": chapter_moods,
        "prompt_constraints": {
            "no_vocals": True,
            "no_sfx": True,
            "instruments_only": True,
        },
        "source_quotes_short": quotes[:8],
        "delivery_hints": {
            "sfx_density": delivery.get("sfx_density"),
            "selection_mode": delivery.get("selection_mode"),
        },
    }
    return brief


def default_motif_family(brief: dict[str, Any]) -> dict[str, Any]:
    ident = brief.get("show_identity") if isinstance(brief.get("show_identity"), dict) else {}
    instruments = list(ident.get("instrumentation_prefs") or ["warm acoustic guitar", "soft piano"])
    mood = str(ident.get("mood") or "determined")
    genre = str(ident.get("genre_hint") or "documentary instrumental")
    keywords = []
    seeds = brief.get("motif_seeds") if isinstance(brief.get("motif_seeds"), dict) else {}
    keywords = [str(k) for k in (seeds.get("keywords") or [])[:6]]
    topic_bit = (", ".join(keywords) if keywords else "founder's journey")
    motif_phrase = (
        f"ascending four-note motif on {instruments[0]}, answered by soft "
        f"{instruments[1] if len(instruments) > 1 else 'piano'} chords"
    )
    prompt_dna = (
        f"{genre}, {mood} mood, instrumental only, {motif_phrase}, "
        f"themes of {topic_bit}, no vocals"
    )
    acts = []
    spine = brief.get("narrative_spine") if isinstance(brief.get("narrative_spine"), dict) else {}
    for a in spine.get("acts") or []:
        if isinstance(a, dict):
            acts.append(
                {
                    "title": a.get("title"),
                    "mood": a.get("mood"),
                    "energy": a.get("energy"),
                }
            )
    return {
        "motif_id": "show_theme_v1",
        "genre_hint": genre,
        "instrumentation": instruments,
        "scale_or_mode": "major_warm",
        "tempo_bpm_feel": "mid_72_88",
        "time_feel": "straight_gentle",
        "motif_phrase": motif_phrase,
        "mood": mood,
        "energy_curve_by_act": acts,
        "prompt_dna": prompt_dna,
        "stems": [
            "theme_cold_open",
            "theme_underscore_calm",
            "theme_underscore_lift",
            "theme_emphasis",
            "theme_chapter_resolve",
            "theme_transition",
            "theme_outro",
        ],
    }


def compile_musicgen_prompt(
    *,
    brief: dict[str, Any],
    motif: dict[str, Any],
    role: str,
    chapter_mood: str | None = None,
    extra_tags: list[str] | None = None,
) -> tuple[str, str]:
    """Return (positive_prompt, negative_prompt) optimized for MusicGen."""
    dna = str(motif.get("prompt_dna") or "").strip()
    phrase = str(motif.get("motif_phrase") or "").strip()
    instruments = ", ".join(str(x) for x in (motif.get("instrumentation") or [])[:4])
    form = {
        "theme_cold_open": "opening theme phrase, clear melodic introduction, full presence",
        "theme_underscore": "loopable soft underscore bed under dialogue, gentle repeating motif, low dynamics",
        "theme_underscore_calm": "calm looping underscore undertone, soft dynamics, speech-friendly",
        "theme_underscore_lift": "slightly brighter underscore lift variant, still under dialogue",
        "theme_emphasis": "short melodic swell phrase highlighting a key claim, not a sound effect",
        "theme_chapter_resolve": "cadential resolving musical tag, gentle note phrase ending a section",
        "theme_transition": "short melodic bridge of musical notes between sections, no whoosh",
        "theme_outro": "soft resolving outro phrase fading out",
    }.get(role, "instrumental musical phrase")

    mood = chapter_mood or str(motif.get("mood") or "determined")
    tags = [str(t) for t in (extra_tags or []) if t][:4]
    quotes = brief.get("source_quotes_short") if isinstance(brief.get("source_quotes_short"), list) else []
    quote_bit = ""
    if quotes and role in {"theme_emphasis", "theme_cold_open"}:
        quote_bit = f" evocative of: {quotes[0][:80]}"

    positive = (
        f"{dna}. Form: {form}. Instruments: {instruments}. "
        f"Melodic contour: {phrase}. Mood: {mood}."
    )
    if tags:
        positive += f" Topics: {', '.join(tags)}."
    positive += quote_bit
    positive += " Pure instrumental music, clear musical notes and phrases."

    negative = (
        "vocals, lyrics, speech, whispering, singing, choir, crowd, applause, "
        "whoosh, riser, trailer hit, foley, sound effects, sfx, woodblock, tick, "
        "click, slap, boing, HVAC hum, murmur, noise bed, room tone only, "
        "comic cartoon sounds, footsteps, door slam"
    )
    return positive.strip(), negative


def ensure_motif_on_plan(sdp: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    """Ensure SDP carries motif_family; strip banned roles from assets when creative."""
    out = dict(sdp)
    family = out.get("motif_family")
    if not isinstance(family, dict) or not family.get("prompt_dna"):
        out["motif_family"] = default_motif_family(brief)
    assets = [a for a in (out.get("assets") or []) if isinstance(a, dict)]
    cleaned: list[dict[str, Any]] = []
    for a in assets:
        role = str(a.get("role") or "")
        aid = str(a.get("asset_id") or "")
        if is_banned_role(role) or asset_id_is_banned(aid):
            continue
        if role and not is_theme_role(role) and role not in THEME_ROLES:
            # Migrate legacy bed/stinger labels when possible.
            if role in {"ambient_bed", "era_music_bed"}:
                a = {**a, "role": "theme_underscore"}
            elif role in {"chapter_stinger", "cold_open"}:
                a = {**a, "role": "theme_chapter_resolve" if "stinger" in role else "theme_cold_open"}
            elif role in {"vo_bridge", "transition_stinger", "transition_whoosh"}:
                a = {**a, "role": "theme_transition"}
            else:
                continue
        cleaned.append(a)
    if not cleaned:
        family = out["motif_family"]
        dna_slug = re.sub(r"[^a-z0-9]+", "_", str(family.get("motif_id") or "theme"))[:24]
        phrase = str(family.get("motif_phrase") or "ascending melodic motif")
        instruments = ", ".join(str(x) for x in (family.get("instrumentation") or ["acoustic guitar", "piano"])[:3])
        cleaned = [
            {
                "asset_id": f"{dna_slug}_cold_open",
                "role": "theme_cold_open",
                "description": f"Opening theme: {phrase}; instruments: {instruments}",
                "duration_seconds": 12,
            },
            {
                "asset_id": f"{dna_slug}_underscore_calm",
                "role": "theme_underscore",
                "description": f"Calm looping underscore undertone: {phrase}; instruments: {instruments}",
                "duration_seconds": 16,
            },
            {
                "asset_id": f"{dna_slug}_underscore_lift",
                "role": "theme_underscore",
                "description": f"Lift underscore variant: {phrase}; instruments: {instruments}",
                "duration_seconds": 16,
            },
            {
                "asset_id": f"{dna_slug}_emphasis",
                "role": "theme_emphasis",
                "description": f"Short melodic swell: {phrase}",
                "duration_seconds": 8,
            },
            {
                "asset_id": f"{dna_slug}_chapter_resolve",
                "role": "theme_chapter_resolve",
                "description": f"Cadential resolve tag: {phrase}",
                "duration_seconds": 8,
            },
            {
                "asset_id": f"{dna_slug}_transition",
                "role": "theme_transition",
                "description": f"Short melodic bridge notes: {phrase}",
                "duration_seconds": 6,
            },
            {
                "asset_id": f"{dna_slug}_outro",
                "role": "theme_outro",
                "description": f"Soft resolving outro: {phrase}",
                "duration_seconds": 12,
            },
        ]
    else:
        # Fill required schema fields when migrating legacy rows.
        for a in cleaned:
            role = str(a.get("role") or "theme_underscore")
            if not a.get("description"):
                a["description"] = f"Instrumental {role.replace('_', ' ')} motif"
            if a.get("duration_seconds") is None:
                a["duration_seconds"] = {
                    "theme_cold_open": 12,
                    "theme_outro": 12,
                    "theme_underscore": 16,
                    "theme_emphasis": 8,
                    "theme_chapter_resolve": 8,
                    "theme_transition": 6,
                }.get(role, 10)
    out["assets"] = cleaned
    return out
