"""Music-only motif family: roles, bans, music_brief, and MusicGen prompt compile."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.run_context import RunContext

# Creative-delivery show audio — music and undertones only.
# Canonical palette kinds (aliases keep theme_* for one release).
PALETTE_KINDS = (
    "motif",
    "underscore_loop",
    "optional_loop",
    "stinger",
    "full_bed",
)

THEME_ROLES = frozenset(
    {
        # Legacy / generation roles
        "theme_cold_open",
        "theme_underscore",
        "theme_emphasis",
        "theme_chapter_resolve",
        "theme_outro",
        "theme_transition",
        # Fixed palette kinds
        "motif",
        "underscore_loop",
        "optional_loop",
        "stinger",
        "full_bed",
    }
)

THEME_BED_ROLES = frozenset(
    {
        "theme_underscore",
        "underscore_loop",
        "optional_loop",
    }
)
THEME_PUNCTUATOR_ROLES = frozenset(
    {
        "theme_emphasis",
        "theme_chapter_resolve",
        "theme_transition",
        "stinger",
    }
)

# Map palette / legacy labels → generation role used by MusicGen + mix.
_ROLE_CANON: dict[str, str] = {
    "motif": "theme_cold_open",
    "underscore_loop": "theme_underscore",
    "optional_loop": "theme_underscore",
    "stinger": "theme_emphasis",
    "full_bed": "theme_cold_open",
    "theme_cold_open": "theme_cold_open",
    "theme_underscore": "theme_underscore",
    "theme_emphasis": "theme_emphasis",
    "theme_chapter_resolve": "theme_chapter_resolve",
    "theme_transition": "theme_transition",
    "theme_outro": "theme_outro",
}

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
        "cold_open",  # legacy SFX cold_open — use theme_cold_open / motif
        "outro",  # legacy — use theme_outro / full_bed
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


def canon_generation_role(role: str | None) -> str:
    """Map palette kind / alias to the MusicGen+mix role string."""
    r = str(role or "").strip()
    return _ROLE_CANON.get(r, r or "theme_underscore")


def palette_kind_for_role(role: str | None, *, energy: str | None = None) -> str:
    """Classify an asset role into a fixed palette kind."""
    r = str(role or "").strip()
    if r in PALETTE_KINDS:
        return r
    if r in {"theme_cold_open", "motif"}:
        return "motif"
    if r in {"theme_outro", "full_bed"}:
        return "full_bed"
    if r in {"theme_emphasis", "theme_chapter_resolve", "theme_transition", "stinger"}:
        return "stinger"
    if r in {"theme_underscore", "underscore_loop", "optional_loop"}:
        if str(energy or "").lower() in {"lift", "optional", "alt", "alternate"}:
            return "optional_loop"
        return "underscore_loop"
    return "underscore_loop"


def analysis_palette_counts(ctx: RunContext) -> dict[str, int]:
    """Analysis-driven fixed palette inventory (kinds only; never invent new stem types)."""
    counts = {
        "motif": 1,
        "underscore_loop": 1,
        "optional_loop": 1,
        "stingers": 3,
        "full_beds": 2,
    }
    mode = ""
    dens = "moderate"
    try:
        from interview_mux.narrative_mode import sonic_density_for_mode

        if ctx.artifact_exists("mastering/mastering_plan.json"):
            plan = ctx.read_json("mastering/mastering_plan.json")
            if isinstance(plan, dict):
                mode = str(
                    plan.get("confirmed_mode")
                    or plan.get("narrative_mode")
                    or plan.get("provisional_mode")
                    or ""
                ).strip()
                dens = sonic_density_for_mode(mode, plan)
    except Exception:
        pass

    chapters = 0
    if ctx.artifact_exists("master/narrative_plan.json"):
        raw = ctx.read_json("master/narrative_plan.json")
        if isinstance(raw, dict):
            chapters = len([c for c in (raw.get("chapters") or []) if isinstance(c, dict)])

    ordered_n = 0
    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            ordered_n = len([s for s in (sel.get("ordered_segment_ids") or []) if s])

    # Cue-slot / density budget when policy exists.
    max_beds = 2
    max_punct = 4
    try:
        from interview_mux.soundscape_policy import load_policy

        pol = load_policy(ctx)
        if isinstance(pol, dict):
            dens_block = pol.get("sfx_density") if isinstance(pol.get("sfx_density"), dict) else {}
            if dens_block.get("max_beds") is not None:
                max_beds = int(dens_block.get("max_beds") or 0)
            if dens_block.get("max_punctuators") is not None:
                max_punct = int(dens_block.get("max_punctuators") or 0)
            slots = [s for s in (pol.get("cue_slots") or []) if isinstance(s, dict)]
            if slots:
                punct_slots = 0
                for slot in slots:
                    allowed = {str(x) for x in (slot.get("allowed_roles") or [])}
                    if allowed & {
                        "theme_emphasis",
                        "theme_chapter_resolve",
                        "theme_transition",
                        "stinger",
                    }:
                        punct_slots += 1
                if punct_slots > 0:
                    max_punct = min(max_punct, punct_slots) if max_punct else punct_slots
    except Exception:
        pass

    dens_l = str(dens or "").lower()
    mode_l = str(mode or "").lower()
    if dens_l in {"minimal", "sparse"} or mode_l in {"sparse_source", "conversational_host"}:
        counts["optional_loop"] = 0
        counts["stingers"] = max(1, min(2, chapters or 1))
        counts["full_beds"] = 1
    elif dens_l in {"hook_forward", "rich", "dense"} or mode_l in {
        "hook_montage",
        "documentary_bridge",
    }:
        counts["optional_loop"] = 1
        counts["stingers"] = max(3, min(6, (chapters or 2) + 1))
        counts["full_beds"] = 2
    else:
        counts["optional_loop"] = 1 if ordered_n >= 8 or chapters >= 2 else 0
        counts["stingers"] = max(2, min(5, chapters or 2))
        counts["full_beds"] = 2 if ordered_n >= 10 else 1

    if max_punct > 0:
        counts["stingers"] = max(1, min(counts["stingers"], max_punct))
    if max_beds <= 1:
        counts["optional_loop"] = 0
    return counts


def build_fixed_palette_assets(
    brief: dict[str, Any],
    counts: dict[str, int],
    *,
    motif_family: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build the exact fixed palette asset rows from analysis counts."""
    family = motif_family if isinstance(motif_family, dict) else default_motif_family(brief)
    dna_slug = re.sub(r"[^a-z0-9]+", "_", str(family.get("motif_id") or "theme"))[:24]
    phrase = str(family.get("motif_phrase") or "ascending melodic motif")
    instruments = ", ".join(
        str(x) for x in (family.get("instrumentation") or ["acoustic guitar", "piano", "bass"])[:4]
    )
    assets: list[dict[str, Any]] = [
        {
            "asset_id": f"{dna_slug}_motif",
            "role": "theme_cold_open",
            "palette_kind": "motif",
            "description": f"Show motif / cold-open seed: {phrase}; instruments: {instruments}",
            "duration_seconds": 14,
        },
        {
            "asset_id": f"{dna_slug}_underscore_loop",
            "role": "theme_underscore",
            "palette_kind": "underscore_loop",
            "energy": "calm",
            "description": (
                f"Primary loopable underscore under dialogue: {phrase}; instruments: {instruments}"
            ),
            "duration_seconds": 12,
        },
    ]
    if int(counts.get("optional_loop") or 0) > 0:
        assets.append(
            {
                "asset_id": f"{dna_slug}_optional_loop",
                "role": "theme_underscore",
                "palette_kind": "optional_loop",
                "energy": "lift",
                "description": (
                    f"Alternate underscore loop (anti-repetition lift): {phrase}; "
                    f"instruments: {instruments}"
                ),
                "duration_seconds": 12,
            }
        )
    n_stingers = max(0, int(counts.get("stingers") or 0))
    for i in range(n_stingers):
        assets.append(
            {
                "asset_id": f"{dna_slug}_stinger_{i+1:02d}",
                "role": "theme_emphasis",
                "palette_kind": "stinger",
                "description": f"Chapter/hinge stinger phrase {i+1}: {phrase}",
                "duration_seconds": 6,
            }
        )
    n_beds = max(1, min(2, int(counts.get("full_beds") or 1)))
    assets.append(
        {
            "asset_id": f"{dna_slug}_full_bed_open",
            "role": "theme_cold_open",
            "palette_kind": "full_bed",
            "placement_hint": "open",
            "description": (
                f"Complex enjoyable full bed for episode open: layered ensemble, "
                f"{phrase}; instruments: {instruments}"
            ),
            "duration_seconds": 20,
        }
    )
    if n_beds >= 2:
        assets.append(
            {
                "asset_id": f"{dna_slug}_full_bed_close",
                "role": "theme_outro",
                "palette_kind": "full_bed",
                "placement_hint": "close",
                "description": (
                    f"Complex enjoyable full bed for episode close: resolving ensemble, "
                    f"{phrase}; instruments: {instruments}"
                ),
                "duration_seconds": 18,
            }
        )
    family["stems"] = [str(a.get("palette_kind") or a.get("role")) for a in assets]
    family["palette_counts"] = dict(counts)
    return assets


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
    """Return list of arbiter failures (empty = ok). Succinct prompts are preferred."""
    errs: list[str] = []
    p = (prompt or "").strip()
    if len(p) < 20:
        errs.append("prompt_too_short")
    if len(p) > 420:
        errs.append("prompt_too_long")
    if text_has_banned_texture(p):
        errs.append("banned_texture_language")
    if not prompt_looks_musical(p):
        errs.append("missing_instrument_or_melody_language")
    # Soft DNA check: require a short token from dna when provided (not full dump).
    if require_dna and require_dna.strip():
        token = require_dna.strip().split(",")[0].strip()[:48]
        if token and token.lower() not in p.lower():
            # Accept key_center / motif phrase fragments instead of full DNA echo.
            words = [w for w in re.split(r"\W+", token.lower()) if len(w) >= 4][:2]
            if words and not any(w in p.lower() for w in words):
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

    genre_hint = "upbeat documentary instrumental with layered ensemble"
    blob_topics = " ".join(t.lower() for t in topics)
    if any("sport" in t.lower() for t in topics):
        genre_hint = "upbeat sports documentary instrumental with driving ensemble"
    elif any(w in arc.lower() for w in ("family", "grief", "loss", "trauma")):
        genre_hint = "intimate rhythmic acoustic documentary with warm ensemble"
    elif any(w in blob_topics for w in ("tech", "startup", "founder", "invest", "business")):
        genre_hint = "bright business documentary instrumental with piano guitar bass and strings"
    elif any(w in arc.lower() for w in ("science", "nature", "explore", "travel")):
        genre_hint = "curious documentary instrumental with acoustic and soft strings"

    instrumentation = [
        "bright acoustic guitar",
        "punchy piano",
        "warm electric bass",
        "soft string harmony",
        "light brushed percussion",
    ]
    if "lift" in {a.get("energy") for a in acts}:
        instrumentation.append("driving brushed pulse")

    # Operator music mood override from style / delivery notes.
    mood_override = _resolve_music_mood_override(ctx, delivery)
    if mood_override == "brighter":
        instrumentation = ["bright acoustic guitar", "sparkling piano", "warm bass", "light strings", "crisp brushed percussion"]
        genre_hint = f"brighter {genre_hint}"
    elif mood_override == "darker":
        instrumentation = ["low acoustic guitar", "felt piano", "round bass", "dark strings", "soft low pulse"]
        genre_hint = f"darker {genre_hint}"
    elif mood_override == "more_acoustic":
        instrumentation = ["fingerstyle acoustic guitar", "upright piano", "acoustic bass", "chamber strings", "brushed snare"]
        genre_hint = f"acoustic {genre_hint}"
    elif mood_override == "more_rhythmic":
        instrumentation = ["acoustic guitar", "piano stabs", "punchy bass", "soft strings", "driving brushed groove"]
        genre_hint = f"rhythmic {genre_hint}"

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

    key_center = "G"
    if any(w in arc.lower() for w in ("grief", "loss", "trauma", "dark")):
        key_center = "D"
    elif mood_override == "brighter":
        key_center = "A"
    elif mood_override == "darker":
        key_center = "E"

    brief = {
        "version": 1,
        "show_identity": {
            "genre_hint": genre_hint,
            "mood": sonic_mood or "determined",
            "energy": "mid",
            "tone": tone,
            "instrumentation_prefs": instrumentation,
            "music_mood_override": mood_override,
            "key_center": key_center,
            "scale_or_mode": "major_bright" if mood_override != "darker" else "minor_warm",
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
            "music_mood_override": mood_override,
        },
    }
    return brief


_MOOD_OVERRIDE_TOKENS = {
    "brighter": ("brighter", "bright mood", "more bright"),
    "darker": ("darker", "dark mood", "more dark", "moody"),
    "more_acoustic": ("more_acoustic", "more acoustic", "acoustic only", "fully acoustic"),
    "more_rhythmic": ("more_rhythmic", "more rhythmic", "more pulse", "more groove"),
}


def _resolve_music_mood_override(ctx: RunContext, delivery: dict[str, Any]) -> str | None:
    """Operator mood: brighter | darker | more_acoustic | more_rhythmic."""
    candidates: list[str] = []
    for key in ("music_mood_override", "music_mood", "sound_design_mood"):
        val = delivery.get(key)
        if val:
            candidates.append(str(val))
    if ctx.artifact_exists("understanding/analysis_state.json"):
        try:
            st = ctx.read_json("understanding/analysis_state.json")
            style = st.get("style") if isinstance(st, dict) else {}
            if isinstance(style, dict):
                if style.get("music_mood_override"):
                    candidates.append(str(style["music_mood_override"]))
                notes = str(style.get("sound_design_notes") or "")
                if notes:
                    candidates.append(notes)
        except Exception:
            pass
    if ctx.artifact_exists("understanding/soundscape_policy.json"):
        try:
            pol = ctx.read_json("understanding/soundscape_policy.json")
            ov = pol.get("operator_overrides") if isinstance(pol, dict) else {}
            if isinstance(ov, dict) and ov.get("music_mood_override"):
                candidates.append(str(ov["music_mood_override"]))
        except Exception:
            pass
    blob = " ".join(candidates).lower()
    for canon, toks in _MOOD_OVERRIDE_TOKENS.items():
        if any(t in blob for t in toks) or blob.strip() == canon:
            return canon
    return None


def default_motif_family(brief: dict[str, Any]) -> dict[str, Any]:
    ident = brief.get("show_identity") if isinstance(brief.get("show_identity"), dict) else {}
    instruments = list(
        ident.get("instrumentation_prefs")
        or [
            "bright acoustic guitar",
            "punchy piano",
            "warm electric bass",
            "soft string harmony",
            "light brushed percussion",
        ]
    )
    if "pulse" not in " ".join(instruments).lower() and "drum" not in " ".join(instruments).lower():
        instruments = list(instruments) + ["light rhythmic pulse"]
    mood = str(ident.get("mood") or "determined")
    genre = str(ident.get("genre_hint") or "upbeat documentary instrumental")
    key_center = str(ident.get("key_center") or "G")
    scale_or_mode = str(ident.get("scale_or_mode") or "major_bright")
    keywords = []
    seeds = brief.get("motif_seeds") if isinstance(brief.get("motif_seeds"), dict) else {}
    keywords = [str(k) for k in (seeds.get("keywords") or [])[:6]]
    topic_bit = (", ".join(keywords) if keywords else "founder's journey")
    motif_phrase = (
        f"ascending four-note motif on {instruments[0]}, answered by "
        f"{instruments[1] if len(instruments) > 1 else 'piano'} chords in {key_center} {scale_or_mode}, "
        f"supported by bass and light percussion"
    )
    prompt_dna = (
        f"{genre}, {mood} mood, key of {key_center} {scale_or_mode}, "
        f"layered ensemble instrumental only, {motif_phrase}, "
        f"themes of {topic_bit}, audible pulse"
    )
    acts = []
    spine = brief.get("narrative_spine") if isinstance(brief.get("narrative_spine"), dict) else {}
    for a in spine.get("acts") or []:
        if isinstance(a, dict):
            acts.append(
                {
                    "title": a.get("title"),
                    "mood": a.get("mood"),
                    "energy": a.get("energy") or "lift",
                }
            )
    return {
        "motif_id": "show_theme_v1",
        "genre_hint": genre,
        "instrumentation": instruments,
        "key_center": key_center,
        "scale_or_mode": scale_or_mode,
        "tempo_bpm_feel": "upbeat_96_112",
        "time_feel": "driving_pulse",
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


def tempo_clause_for_wpm(wpm: float | None) -> str:
    """Map local speech WPM → MusicGen tempo/feel (always upbeat pulse floor)."""
    if wpm is None or wpm <= 0:
        return "upbeat mid-tempo pulse around 100 BPM, clear rhythmic accompaniment"
    if wpm < 120:
        return "mid-upbeat groove around 92–100 BPM, clear pulse under speech"
    if wpm < 150:
        return "upbeat pulse around 100–112 BPM, energetic rhythmic bed"
    return "driving rhythmic bed around 112–124 BPM, high-energy pulse"


def estimate_segment_wpm(text: str, duration_ms: int) -> float | None:
    words = [w for w in str(text or "").split() if w.strip()]
    if not words or duration_ms <= 0:
        return None
    minutes = duration_ms / 60000.0
    if minutes <= 0:
        return None
    return len(words) / minutes


def compile_musicgen_prompt(
    *,
    brief: dict[str, Any],
    motif: dict[str, Any],
    role: str,
    chapter_mood: str | None = None,
    extra_tags: list[str] | None = None,
    wpm: float | None = None,
    palette_kind: str | None = None,
    energy: str | None = None,
) -> tuple[str, str]:
    """Authoritative succinct MusicGen recipe: instruments, energy, space, bans."""
    kind = palette_kind or palette_kind_for_role(role, energy=energy)
    gen_role = canon_generation_role(role)
    phrase = str(motif.get("motif_phrase") or "ascending melodic motif").strip()
    # Keep phrase short for MusicGen.
    if len(phrase) > 90:
        phrase = phrase[:87].rstrip() + "…"
    instruments = ", ".join(str(x) for x in (motif.get("instrumentation") or [])[:4])
    if not instruments:
        instruments = "acoustic guitar, piano, bass, light percussion"
    key_center = str(motif.get("key_center") or "G")
    scale_or_mode = str(motif.get("scale_or_mode") or "major_bright")
    mood = chapter_mood or str(motif.get("mood") or "determined")
    tempo = tempo_clause_for_wpm(wpm)

    form_by_kind = {
        "motif": "short show motif / cold-open seed, clear melodic lead",
        "underscore_loop": "loopable duck-safe underscore under dialogue, soft midrange",
        "optional_loop": "alternate lift underscore loop, still duck-safe under dialogue",
        "stinger": "short hinge stinger phrase of musical notes, not a sound effect",
        "full_bed": "complex enjoyable full bed with layered ensemble, speech-free presence",
    }
    # Legacy role fallbacks when kind not set.
    if kind not in form_by_kind:
        form_by_kind[kind] = {
            "theme_cold_open": form_by_kind["motif"],
            "theme_outro": form_by_kind["full_bed"],
            "theme_underscore": form_by_kind["underscore_loop"],
            "theme_emphasis": form_by_kind["stinger"],
            "theme_chapter_resolve": form_by_kind["stinger"],
            "theme_transition": form_by_kind["stinger"],
        }.get(gen_role, "instrumental musical phrase with clear pulse")

    form = form_by_kind.get(kind) or "instrumental musical phrase with clear pulse"
    tags = [str(t) for t in (extra_tags or []) if t][:2]
    tag_bit = f"; topics {', '.join(tags)}" if tags else ""

    # Recipe class from brief when present (succinct, not story dump).
    ident = brief.get("show_identity") if isinstance(brief.get("show_identity"), dict) else {}
    genre = str(ident.get("genre_hint") or motif.get("genre_hint") or "documentary instrumental")
    if len(genre) > 40:
        genre = genre[:37].rstrip() + "…"
    # Shorten tempo clause for MusicGen token budget.
    tempo_short = tempo
    if len(tempo_short) > 48:
        tempo_short = "upbeat pulse ~100 BPM"

    positive = (
        f"{genre}; {form}; {instruments}; "
        f"key {key_center} {scale_or_mode}; motif: {phrase}; "
        f"{mood}; {tempo_short}{tag_bit}. Instrumental, audible pulse."
    )
    positive = re.sub(r"\s+", " ", positive).strip()
    if len(positive) > 400:
        positive = positive[:397].rstrip() + "…"

    negative = (
        "vocals, lyrics, speech, singing, choir, whoosh, riser, foley, sound effects, "
        "tick, woodblock, HVAC, murmur, pad-only drone, room tone"
    )
    return positive, negative


def harden_palette_inventory(
    sdp: dict[str, Any],
    brief: dict[str, Any],
    *,
    counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Force SDP assets to the exact fixed palette inventory (no ad-hoc extra stems)."""
    out = dict(sdp)
    family = out.get("motif_family")
    if not isinstance(family, dict) or not family.get("prompt_dna"):
        family = default_motif_family(brief)
        out["motif_family"] = family
    use_counts = counts or {
        "motif": 1,
        "underscore_loop": 1,
        "optional_loop": 1,
        "stingers": 3,
        "full_beds": 2,
    }
    # Prefer existing motif DNA / descriptions when present, but enforce counts.
    existing = [a for a in (out.get("assets") or []) if isinstance(a, dict)]
    by_kind: dict[str, list[dict[str, Any]]] = {k: [] for k in PALETTE_KINDS}
    for a in existing:
        role = str(a.get("role") or "")
        aid = str(a.get("asset_id") or "")
        if is_banned_role(role) or asset_id_is_banned(aid):
            continue
        if role and not is_theme_role(role):
            if role in {"ambient_bed", "era_music_bed"}:
                a = {**a, "role": "theme_underscore"}
            elif role in {"chapter_stinger", "cold_open"}:
                a = {
                    **a,
                    "role": "theme_chapter_resolve" if "stinger" in role else "theme_cold_open",
                }
            elif role in {"vo_bridge", "transition_stinger", "transition_whoosh"}:
                a = {**a, "role": "theme_transition"}
            else:
                continue
        kind = str(a.get("palette_kind") or "") or palette_kind_for_role(
            str(a.get("role") or ""), energy=str(a.get("energy") or "") or None
        )
        # Distinguish motif vs full_bed when both use theme_cold_open.
        if kind == "motif" and "full_bed" in aid:
            kind = "full_bed"
        if kind == "full_bed" and ("motif" in aid or aid.endswith("_cold_open")) and "full_bed" not in aid:
            # Keep first cold_open-like as motif if we still need one.
            if not by_kind["motif"]:
                kind = "motif"
        if kind in by_kind:
            by_kind[kind].append({**a, "palette_kind": kind})

    built = build_fixed_palette_assets(brief, use_counts, motif_family=family)
    # Overlay descriptions from LLM assets when kinds match.
    merged: list[dict[str, Any]] = []
    used_existing: set[str] = set()
    for row in built:
        kind = str(row.get("palette_kind") or "")
        candidates = [c for c in by_kind.get(kind, []) if str(c.get("asset_id")) not in used_existing]
        if candidates:
            src = candidates[0]
            used_existing.add(str(src.get("asset_id")))
            merged.append(
                {
                    **row,
                    "asset_id": str(src.get("asset_id") or row["asset_id"]),
                    "description": str(src.get("description") or row.get("description") or ""),
                    "duration_seconds": src.get("duration_seconds") or row.get("duration_seconds"),
                    "energy": src.get("energy") or row.get("energy"),
                    "role": str(src.get("role") or row.get("role")),
                    "palette_kind": kind,
                }
            )
        else:
            merged.append(row)

    out["assets"] = merged
    family = out.get("motif_family")
    if isinstance(family, dict):
        ident = brief.get("show_identity") if isinstance(brief.get("show_identity"), dict) else {}
        family.setdefault("key_center", ident.get("key_center") or "G")
        family.setdefault("scale_or_mode", ident.get("scale_or_mode") or "major_bright")
        family["palette_counts"] = dict(use_counts)
        family["stems"] = [str(a.get("palette_kind") or a.get("role")) for a in merged]
        out["motif_family"] = family
    out["palette_counts"] = dict(use_counts)
    return out


def ensure_motif_on_plan(
    sdp: dict[str, Any],
    brief: dict[str, Any],
    *,
    ctx: RunContext | None = None,
    counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Ensure SDP carries motif_family and exact fixed palette inventory."""
    use_counts = counts
    if use_counts is None and ctx is not None:
        try:
            use_counts = analysis_palette_counts(ctx)
        except Exception:
            use_counts = None
    return harden_palette_inventory(sdp, brief, counts=use_counts)
