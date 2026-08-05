"""War Room cover prompt theme, harvest, STYLE_HEAD v2, and validation (no truncation)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, repo_root

STYLE_CONTRACT_VERSION = 2

# Legacy alias kept for tests / callers that still import FIXED_NEGATIVE.
# Images API has no negative_prompt — fold avoidances into without-clauses.
FIXED_NEGATIVE = ""

_REALISM_RE = re.compile(
    r"(?<![-\w])(photo(?:graph(?:ic)?)?|photoreal(?:istic)?|realistic)(?![-\w])",
    re.I,
)
_LETTERED_SIGNAGE_RE = re.compile(
    r"\b(text|letters?|typography|words?|caption|title|logo|watermark|signage|label)\b",
    re.I,
)
# Depiction language that asks for a person's likeness (objects/symbols remain OK).
_PERSON_LIKENESS_RE = re.compile(
    r"(?:"
    r"\bportraits?\b|"
    r"\bselfie\b|"
    r"\blikeness\b|"
    r"\b(human|person(?:'s)?|people|man(?:'s)?|woman(?:'s)?|girl(?:'s)?|boy(?:'s)?)\s+"
    r"(face|faces|figure|figures|body|bodies|portrait|portraits)\b|"
    r"\b(face|faces|figure|figures)\s+of\s+(a\s+)?(person|people|man|woman|founder|guest|host)\b|"
    r"\b(crowd|crowds)\s+of\s+(people|faces)\b|"
    r"\bsilhouettes?\s+of\s+(a\s+)?(person|people|man|woman|founder)\b|"
    r"\bdepict(?:ing|s)?\s+(a\s+)?(person|people|man|woman|human)\b"
    r")",
    re.I,
)
_NO_PERSON_WITHOUT_RE = re.compile(
    r"\bwithout\b[^.]*\b(person|people|portrait|likeness|human\s+face|identifiable\s+people)\b",
    re.I,
)
_REQUIRED_ACCENT_NAMES = ("cerulean", "crimson")
_DEFAULT_NO_PERSON_WITHOUT = (
    "without any person likeness, human face, portrait, or identifiable people"
)


def cover_image_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    root = cfg if cfg is not None else merged_config()
    podcast = root.get("podcast") if isinstance(root.get("podcast"), dict) else {}
    cov = podcast.get("cover_image") if isinstance(podcast.get("cover_image"), dict) else {}
    return dict(cov)


def cover_theme_path(cfg: dict[str, Any] | None = None) -> Path:
    root = cfg if cfg is not None else merged_config()
    podcast = root.get("podcast") if isinstance(root.get("podcast"), dict) else {}
    rel = str(podcast.get("cover_theme_path") or "config/podcast/cover_theme.json")
    p = Path(rel)
    if not p.is_absolute():
        p = repo_root() / p
    return p


def load_cover_theme(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    path = cover_theme_path(cfg)
    if not path.is_file():
        return _default_theme()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else _default_theme()
    except Exception:
        return _default_theme()


def _default_theme() -> dict[str, Any]:
    return {
        "version": STYLE_CONTRACT_VERSION,
        "palette": {
            "midnight_charcoal": {"hex": "#0B1220"},
            "old_gold": {"hex": "#C9A227"},
            "cerulean": {"hex": "#2A5C8A"},
            "crimson": {"hex": "#8B1E3F"},
        },
        "required_accents": list(_REQUIRED_ACCENT_NAMES),
        "composition": {
            "forbid_photorealism": True,
            "forbid_person_likeness": True,
            "hero_must_be": "objects_symbols_places_or_abstract_forms",
        },
        "text_policy": {"depicted_text": "asterisks_only"},
        "prompt_anatomy": [
            "hero_subject",
            "supporting_motifs",
            "composition",
            "palette_locks",
            "material_finish",
            "lighting",
            "asterisks_text_policy",
            "without_clauses",
        ],
    }


def palette_locks_text(theme: dict[str, Any] | None = None) -> str:
    theme = theme or load_cover_theme()
    palette = theme.get("palette") if isinstance(theme.get("palette"), dict) else {}
    parts: list[str] = []
    for name in (
        "midnight_charcoal",
        "old_gold",
        "map_sepia",
        "map_ink",
        "cerulean",
        "crimson",
        "bone_white",
        "deep_black",
    ):
        entry = palette.get(name)
        if isinstance(entry, dict) and entry.get("hex"):
            parts.append(f"{name} {entry['hex']}")
        elif isinstance(entry, str):
            parts.append(f"{name} {entry}")
    accents = theme.get("required_accents") or list(_REQUIRED_ACCENT_NAMES)
    accent_note = " and ".join(str(a) for a in accents)
    return (
        "Palette locks: "
        + ", ".join(parts)
        + f". Required accents every episode: {accent_note}."
    )


def build_style_head(theme: dict[str, Any] | None = None) -> str:
    """STYLE_HEAD v2 — palette, accents, composition, asterisks; no default objects."""
    theme = theme or load_cover_theme()
    locks = palette_locks_text(theme)
    return (
        "Square podcast title card, bold vintage line art with subtle pointillist grain, "
        "flat graphic shapes, high contrast, non-photorealistic. "
        f"{locks} "
        "Depicted text policy: asterisks only (*** clusters) — no letters, words, or sentences "
        "in any language. Clear hero hierarchy with supporting motifs from the episode harvest only. "
        "Compose:"
    )


# Module-level STYLE_HEAD rebuilt from theme on import (and refreshable).
STYLE_HEAD = build_style_head()


def refresh_style_head(cfg: dict[str, Any] | None = None) -> str:
    global STYLE_HEAD
    STYLE_HEAD = build_style_head(load_cover_theme(cfg))
    return STYLE_HEAD


def prompt_max_chars(cfg: dict[str, Any] | None = None) -> int:
    cov = cover_image_cfg(cfg)
    try:
        n = int(cov.get("prompt_max_chars") or 32000)
    except (TypeError, ValueError):
        n = 32000
    return max(500, min(n, 100_000))


def prompt_max_tokens(selection: dict[str, Any] | None = None) -> int:
    """Char-based budget expressed as ~4 chars/token for craft LLM guidance."""
    if selection and selection.get("prompt_max_tokens"):
        try:
            return max(32, int(selection["prompt_max_tokens"]))
        except (TypeError, ValueError):
            pass
    return max(32, prompt_max_chars() // 4)


def estimate_tokens(text: str) -> int:
    s = (text or "").strip()
    if not s:
        return 0
    return max(1, (len(s) + 3) // 4)


def contains_realism(text: str) -> bool:
    return bool(_REALISM_RE.search(text or ""))


def contains_lettered_signage_request(text: str) -> bool:
    """Heuristic: prompt asks for readable text/logo (asterisks-only is OK)."""
    s = text or ""
    if "***" in s and not re.search(r"\b(words?|letters?|typography|logo)\b", s, re.I):
        return False
    return bool(_LETTERED_SIGNAGE_RE.search(s))


def has_required_accents(text: str) -> bool:
    lower = (text or "").lower()
    return all(name in lower for name in _REQUIRED_ACCENT_NAMES)


def has_without_clauses(text: str) -> bool:
    return bool(re.search(r"\bwithout\b", text or "", re.I))


def contains_person_likeness(text: str) -> bool:
    """True when the prompt asks to depict a person / face / portrait likeness.

    Avoidance ``without …`` clauses are stripped first so required no-person
    without-clauses do not false-positive.
    """
    cleaned = re.sub(r"\bwithout\b[^.]*", " ", text or "", flags=re.I)
    return bool(_PERSON_LIKENESS_RE.search(cleaned))


def has_no_person_without_clause(text: str) -> bool:
    return bool(_NO_PERSON_WITHOUT_RE.search(text or ""))


def anatomy_coverage(prompt: str, theme: dict[str, Any] | None = None) -> list[str]:
    """Return missing anatomy keys (empty = ok). Soft checklist for validation."""
    theme = theme or load_cover_theme()
    keys = theme.get("prompt_anatomy") or []
    lower = (prompt or "").lower()
    missing: list[str] = []
    checks = {
        "hero_subject": bool(re.search(r"\b(hero|focal|center(?:ed)?|dominant)\b", lower)),
        "supporting_motifs": bool(
            re.search(r"\b(motif|supporting|flanking|secondary)\b", lower)
        )
        or lower.count(",") >= 3,
        "composition": bool(
            re.search(r"\b(composition|framed|hierarchy|balanced|asymmetric)\b", lower)
        ),
        "palette_locks": has_required_accents(prompt)
        or "palette" in lower
        or "#" in (prompt or ""),
        "material_finish": bool(
            re.search(r"\b(ink|paper|grain|matte|etch|line.?art|pointill)\b", lower)
        ),
        "lighting": bool(
            re.search(r"\b(light(?:ing)?|glow|shadow|rim|contrast)\b", lower)
        ),
        "asterisks_text_policy": "***" in (prompt or "")
        or "asterisk" in lower
        or ("no text" in lower and "no letter" in lower),
        "without_clauses": has_without_clauses(prompt),
    }
    for key in keys:
        k = str(key)
        if k in checks and not checks[k]:
            missing.append(k)
    return missing


def validate_prompt(
    prompt: str,
    *,
    max_chars: int | None = None,
    theme: dict[str, Any] | None = None,
) -> list[str]:
    """Return rejection reasons. Never silently truncate."""
    errors: list[str] = []
    p = (prompt or "").strip()
    if not p:
        errors.append("empty_prompt")
        return errors
    cap = prompt_max_chars() if max_chars is None else max_chars
    if len(p) > cap:
        errors.append(f"over_budget:{len(p)}>{cap}")
    if contains_realism(p):
        errors.append("realism_language")
    if contains_person_likeness(p):
        errors.append("person_likeness")
    if not has_required_accents(p):
        errors.append("missing_required_accents")
    if not has_without_clauses(p):
        errors.append("missing_without_clauses")
    if not has_no_person_without_clause(p):
        errors.append("missing_no_person_without_clause")
    missing = anatomy_coverage(p, theme)
    if missing:
        errors.append("incomplete_anatomy:" + ",".join(missing))
    return errors


def assemble_prompt(
    motifs: list[str],
    *,
    style_head: str | None = None,
    without_clauses: list[str] | None = None,
    theme: dict[str, Any] | None = None,
) -> str:
    head = (style_head or STYLE_HEAD).strip()
    motif_text = ", ".join(m.strip() for m in motifs if m and str(m).strip())
    if not motif_text:
        # Harvest-empty fallback: abstract geometry only — no stock map/mic.
        motif_text = (
            "abstract geometric focal emblem, interlocking arcs, sparse pointillist field"
        )
    without = without_clauses or [
        "without photorealism",
        "without readable letters or words in any language",
        "without logos or watermarks",
        "without copying show-art emblems",
        _DEFAULT_NO_PERSON_WITHOUT,
    ]
    without_text = ", ".join(w.strip() for w in without if w and str(w).strip())
    theme = theme or load_cover_theme()
    accents = palette_locks_text(theme)
    body = (
        f"{head} hero subject and motifs: {motif_text}. "
        f"Composition: clear centered hierarchy, balanced negative space. "
        f"{accents} "
        "Material: vintage ink line art on charcoal ground with pointillist grain. "
        "Lighting: high-contrast graphic punch with soft rim glow on hero. "
        "Depicted text: asterisks only (***) if any plate appears. "
        f"{without_text}."
    )
    return body.strip()


def enforce_budget(
    prompt: str, motifs: list[str], *, max_tokens: int
) -> tuple[str, list[str]]:
    """Deprecated for OpenAI path — prefer validate_prompt (no truncation).

    Kept for compatibility: if over budget, returns prompt unchanged and motifs;
    callers must treat over-budget as validation failure.
    """
    _ = max_tokens
    return prompt, list(motifs)


def load_image_selection(repo: Path | None = None) -> dict[str, Any]:
    """Legacy local_image selection — unused for OpenAI covers; returns OpenAI budget."""
    _ = repo
    return {
        "provider": "openai",
        "prompt_max_tokens": prompt_max_chars() // 4,
        "prompt_max_chars": prompt_max_chars(),
    }


def _clip_str(val: Any, n: int = 240) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    return s[:n]


def _theme_labels_from_brief(brief: dict[str, Any]) -> list[str]:
    themes: list[str] = []
    for t in brief.get("topics") or []:
        if isinstance(t, dict) and t.get("name"):
            themes.append(str(t["name"]))
        elif isinstance(t, str):
            themes.append(t)
    for t in brief.get("themes") or []:
        if isinstance(t, str):
            themes.append(t)
        elif isinstance(t, dict) and t.get("name"):
            themes.append(str(t["name"]))
    return themes[:12]


def harvest_motif_context(ctx: Any) -> dict[str, Any]:
    """Pull post-master episode signals for dynamic cover motifs (no default props)."""

    def _read(rel: str) -> Any:
        try:
            if ctx.artifact_exists(rel):
                return ctx.read_json(rel)
        except Exception:
            return None
        return None

    meta = _read("publish/episode_meta.json") or {}
    brief = _read("understanding/content_brief.json") or {}
    narrative = _read("understanding/narrative_arc.json") or {}
    selection = _read("master/selection.json") or {}
    analysis = _read("analysis/analysis_state.json") or {}
    speakers = _read("understanding/speakers.json") or {}
    sdp = _read("creative/sound_design_plan.json") or {}
    sonic = _read("creative/sonic_mood.json") or {}

    themes = _theme_labels_from_brief(brief) if isinstance(brief, dict) else []
    chapters: list[str] = []
    if isinstance(selection, dict):
        for ch in selection.get("chapters") or []:
            if isinstance(ch, dict):
                title = ch.get("title") or ch.get("name")
                if title:
                    chapters.append(str(title)[:120])
    if isinstance(narrative, dict):
        for ch in narrative.get("chapters") or []:
            if isinstance(ch, dict) and ch.get("title"):
                chapters.append(str(ch["title"])[:120])

    sdp_labels: list[str] = []
    if isinstance(sdp, dict):
        for key in ("themes", "palette_labels", "motif_hints", "beds"):
            for item in sdp.get(key) or []:
                if isinstance(item, str):
                    sdp_labels.append(item[:80])
                elif isinstance(item, dict):
                    lab = item.get("label") or item.get("name") or item.get("theme")
                    if lab:
                        sdp_labels.append(str(lab)[:80])

    speaker_bits: list[str] = []
    if isinstance(speakers, dict):
        for sp in speakers.get("speakers") or speakers.get("roles") or []:
            if isinstance(sp, dict):
                bit = sp.get("display_name") or sp.get("role") or sp.get("name")
                if bit:
                    speaker_bits.append(str(bit)[:80])

    mood = None
    if isinstance(sonic, dict):
        mood = sonic.get("mood") or sonic.get("summary") or sonic.get("label")
    if mood is None and isinstance(sdp, dict):
        mood = sdp.get("mood") or sdp.get("emotional_register")

    thesis = brief.get("thesis") if isinstance(brief, dict) else None
    stakes = brief.get("stakes") if isinstance(brief, dict) else None
    if isinstance(analysis, dict) and not stakes:
        stakes = analysis.get("stakes") or (analysis.get("brief") or {}).get("stakes")

    return {
        "episode_title": _clip_str((meta or {}).get("title"), 160),
        "episode_description": _clip_str((meta or {}).get("description"), 600),
        "thesis": _clip_str(thesis, 400),
        "stakes": _clip_str(stakes, 300),
        "themes": themes[:10],
        "chapter_titles": chapters[:8],
        "speaker_labels": speaker_bits[:6],
        "sound_design_theme_labels": sdp_labels[:10],
        "sonic_mood": _clip_str(mood, 200),
        "forbid_default_props": True,
        "note": (
            "Invent motifs only from this harvest as objects/symbols. "
            "Never depict a person, face, portrait, or anyone's likeness. "
            "Do not default to war-room maps, ribbon mics, or show emblems."
        ),
    }


BRILLIANT_EXEMPLAR = (
    "Square podcast title card, bold vintage line art with subtle pointillist grain, "
    "flat graphic shapes, high contrast, non-photorealistic. Palette locks: midnight_charcoal "
    "#0B1220, old_gold #C9A227, cerulean #2A5C8A, crimson #8B1E3F. Required accents every "
    "episode: cerulean and crimson. Depicted text policy: asterisks only (***). Compose: "
    "hero subject a fractured glass chess king cracked along a golden fault line, supporting "
    "motifs of orbiting sealed envelopes and a single suspended hourglass silhouette, "
    "composition clear centered hierarchy with asymmetric negative space on the left, "
    "material etched ink on charcoal with bone-white highlights and old-gold edge ticks, "
    "lighting high-contrast graphic punch with soft cerulean rim and crimson underglow, "
    "asterisk plate *** only if a nameplate appears, without photorealism, without readable "
    "letters or words in any language, without logos or watermarks, without copying show-art "
    "emblems, without any person likeness, human face, portrait, or identifiable people."
)

DISAMBIGUATION_VOLLEY = (
    "Disambiguation examples (instruction only — invent your own without-clauses):\n"
    "- If harvest mentions 'board', prefer strategy board / abstract grid — without corporate whiteboard.\n"
    "- If harvest mentions 'network', prefer constellation nodes — without social-app UI chrome.\n"
    "- If harvest mentions 'stage', prefer geometric proscenium arches — without photoreal concert photos.\n"
    "- If harvest names people or roles, use objects that stand for the idea — without any person "
    "likeness, human face, portrait, or identifiable people.\n"
    "Always include without-clauses covering photorealism, readable lettering, logos, "
    "show-emblem copy, and person likeness."
)
