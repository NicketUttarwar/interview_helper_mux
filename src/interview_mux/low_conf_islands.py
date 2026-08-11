"""Recall-first low-confidence cluster ladder + density guarantee for selection.

Where [`stt_lexicon_islands`](src/interview_mux/stt_lexicon_islands.py) finds tight
consecutive low-confidence runs for a soft prefer-include boost, this module runs a
four-tier fallback ladder (tight → loose → window → segment_soft) that tolerates
confident English sprinkled inside a garbled stretch (lingua franca), density-ranks
every native segment, and hard-includes the densest decile so the pack can never
drop the densest insight the STT could not name.

Detection never recovers the true word — it only flags spans and protects them.
"""

from __future__ import annotations

import math
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.stt_lexicon_islands import _COMMON_EN, _NON_ASCII

ISLANDS_PATH = "analysis/low_conf_islands.json"
DENSITY_PATH = "analysis/low_conf_density_ranking.json"
MUST_KEEP_PATH = "analysis/low_conf_must_keep.json"

LADDER: tuple[str, ...] = ("tight", "loose", "window", "segment_soft")

# Later tiers describe a wider read of the same core, so a merged island reports
# the loosest tier that fired (tight+loose → "loose") with tiers_fired intact.
_KIND_RANK = {"tight": 0, "loose": 1, "window": 2, "segment_soft": 3}

# Cluster-kind credit in the density score (segment_soft still ranks, at a discount).
_KIND_WEIGHT = {"tight": 1.0, "loose": 1.0, "window": 0.75, "segment_soft": 0.45}

_BACKCHANNEL = frozenset(
    {"yeah", "yes", "no", "okay", "ok", "right", "mhm", "mm", "hmm", "uh", "um", "so", "and"}
)

_CLUSTER_DEFAULTS: dict[str, Any] = {
    "low_confidence_threshold": 0.85,
    "high_confidence_threshold": 0.90,
    "min_low_ratio_loose": 0.45,
    "min_low_words_loose": 3,
    "max_high_conf_sprinkle": 8,
    "break_on_high_run": 5,
    "cluster_break_pause_ms": 700,
    "window_ms_options": [2000, 4000, 6000],
    "window_mean_conf_max": 0.88,
    "min_bricks_in_window": 4,
    "segment_soft_density": 0.12,
    "null_confidence_as": "mid",
    # Bounds + pad quality (not in the plan table; keep detection sane on long tape).
    "max_cluster_ms": 20000,
    "min_pad_words": 2,
}

_SELECTION_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "top_percentile": 0.10,
    "enforcement_mode": "authoritative",
    "min_positive_density": 0.0,
    "recall_first": True,
}


def low_conf_selection_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolved ``analysis.low_conf_selection`` with the nested cluster ladder block."""
    resolved = cfg if cfg is not None else merged_config()
    analysis = resolved.get("analysis") if isinstance(resolved.get("analysis"), dict) else {}
    block = analysis.get("low_conf_selection") if isinstance(analysis.get("low_conf_selection"), dict) else {}
    cluster_block = block.get("cluster") if isinstance(block.get("cluster"), dict) else {}
    out = {**_SELECTION_DEFAULTS, **{k: v for k, v in block.items() if k != "cluster"}}
    out["cluster"] = {**_CLUSTER_DEFAULTS, **cluster_block}
    return out


def enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(low_conf_selection_cfg(cfg).get("enabled", True))


def word_band(conf: Any, low: float = 0.85, high: float = 0.90) -> str:
    """``low`` | ``mid`` | ``high`` for one word confidence; null reads as ``mid``."""
    if conf is None:
        return "mid"
    try:
        value = float(conf)
    except (TypeError, ValueError):
        return "mid"
    if value < float(low):
        return "low"
    if value < float(high):
        return "mid"
    return "high"


def _ms(row: dict[str, Any], key: str) -> int:
    try:
        return int(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _token(w: dict[str, Any]) -> str:
    return str(w.get("text") or w.get("word") or "").strip()


def _norm_token(text: str) -> str:
    return str(text or "").strip(".,!?;:\"'()[]").lower()


def _raw_conf(w: dict[str, Any]) -> float | None:
    value = w.get("confidence")
    if value is None:
        value = w.get("conf")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _prepare_words(words: list[dict[str, Any]], *, low: float, high: float) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for w in words:
        if not isinstance(w, dict):
            continue
        text = _token(w)
        if not text:
            continue
        conf = _raw_conf(w)
        prepared.append(
            {
                "text": text,
                "start_ms": _ms(w, "start_ms"),
                "end_ms": _ms(w, "end_ms") or _ms(w, "start_ms"),
                "speaker_id": str(w.get("speaker_id") or w.get("speaker") or "") or None,
                "confidence": conf,
                "band": word_band(conf, low, high),
            }
        )
    prepared.sort(key=lambda w: (w["start_ms"], w["end_ms"]))
    return prepared


def _null_conf_value(cluster: dict[str, Any]) -> float:
    """Numeric stand-in for missing confidence (mid band by default)."""
    low = float(cluster["low_confidence_threshold"])
    high = float(cluster["high_confidence_threshold"])
    mode = str(cluster.get("null_confidence_as") or "mid").lower()
    if mode == "low":
        return max(0.0, low - 0.01)
    if mode == "high":
        return high
    return (low + high) / 2.0


def _mean_conf(words: list[dict[str, Any]], *, null_value: float) -> float:
    if not words:
        return 1.0
    total = 0.0
    for w in words:
        conf = w.get("confidence")
        total += null_value if conf is None else float(conf)
    return total / len(words)


def _is_content_token(text: str) -> bool:
    tok = _norm_token(text)
    return bool(tok) and tok not in _COMMON_EN and len(tok) > 2


def _has_non_ascii(words: list[dict[str, Any]]) -> bool:
    return any(_NON_ASCII.search(w["text"]) for w in words)


def _has_uncommon_english(words: list[dict[str, Any]]) -> bool:
    toks = [_norm_token(w["text"]) for w in words]
    toks = [t for t in toks if t.isalpha() and len(t) > 2]
    if not toks:
        return False
    uncommon = sum(1 for t in toks if t not in _COMMON_EN and t.isascii())
    return uncommon / len(toks) >= 0.5


def _pad_quality(
    words: list[dict[str, Any]],
    start_i: int,
    end_i: int,
    *,
    cluster: dict[str, Any],
) -> tuple[bool, list[str], list[str]]:
    """High-confidence, non-backchannel pad on both sides of the low-word core.

    Indices address the core rather than the merged island span: the window tier
    routinely swallows the pads themselves, and a pad that lands inside the widest
    span still proves the speaker returned to fluent English around the garble.
    """
    min_pad = int(cluster.get("min_pad_words") or 2)
    max_gap = int(cluster["cluster_break_pause_ms"])
    left: list[dict[str, Any]] = []
    right: list[dict[str, Any]] = []

    k = start_i - 1
    while k >= 0 and len(left) < min_pad:
        w = words[k]
        if w["band"] != "high":
            break
        anchor = left[0] if left else words[start_i]
        if anchor["start_ms"] - w["end_ms"] > max_gap:
            break
        left.insert(0, w)
        k -= 1

    k = end_i + 1
    while k < len(words) and len(right) < min_pad:
        w = words[k]
        if w["band"] != "high":
            break
        anchor = right[-1] if right else words[end_i]
        if w["start_ms"] - anchor["end_ms"] > max_gap:
            break
        right.append(w)
        k += 1

    left_texts = [w["text"] for w in left]
    right_texts = [w["text"] for w in right]

    def _substantive(side: list[str]) -> bool:
        return any(_norm_token(t) not in _BACKCHANNEL for t in side)

    padded = (
        len(left) >= min_pad
        and len(right) >= min_pad
        and _substantive(left_texts)
        and _substantive(right_texts)
    )
    return padded, left_texts, right_texts


def _tier_tight(words: list[dict[str, Any]], *, cluster: dict[str, Any]) -> list[tuple[int, int]]:
    max_gap = int(cluster["cluster_break_pause_ms"])
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(words)
    while i < n:
        if words[i]["band"] != "low":
            i += 1
            continue
        j = i
        while (
            j + 1 < n
            and words[j + 1]["band"] == "low"
            and words[j + 1]["start_ms"] - words[j]["end_ms"] <= max_gap
        ):
            j += 1
        spans.append((i, j))
        i = j + 1
    return spans


def _tier_loose(words: list[dict[str, Any]], *, cluster: dict[str, Any]) -> list[tuple[int, int]]:
    """Sprinkle-tolerant expansion: confident English inside a span never ends it."""
    min_ratio = float(cluster["min_low_ratio_loose"])
    min_lows = int(cluster["min_low_words_loose"])
    max_sprinkle = int(cluster["max_high_conf_sprinkle"])
    break_run = int(cluster["break_on_high_run"])
    break_pause = int(cluster["cluster_break_pause_ms"])
    max_ms = int(cluster["max_cluster_ms"])

    spans: list[tuple[int, int]] = []
    n = len(words)
    i = 0
    while i < n:
        if words[i]["band"] != "low":
            i += 1
            continue
        low_count = 0
        sprinkle = 0
        high_run = 0
        best: int | None = None
        j = i
        while j < n:
            w = words[j]
            if w["start_ms"] - words[i]["start_ms"] > max_ms:
                break
            if w["band"] == "low":
                low_count += 1
                high_run = 0
            else:
                sprinkle += 1
                if sprinkle > max_sprinkle:
                    break
                # Function words are glue, not a return to fluent English.
                if w["band"] == "high" and _is_content_token(w["text"]):
                    high_run += 1
                gap = w["start_ms"] - words[j - 1]["end_ms"] if j > i else 0
                if high_run >= break_run and gap >= break_pause:
                    break
            total = j - i + 1
            if low_count >= min_lows and (low_count / total) >= min_ratio:
                best = j
            j += 1
        if best is not None:
            spans.append((i, best))
            i = best + 1
            continue
        i += 1
    return spans


def _tier_window(words: list[dict[str, Any]], *, cluster: dict[str, Any]) -> list[tuple[int, int]]:
    """Fixed ms windows catch mixed stretches tight/loose miss."""
    if not words:
        return []
    mean_max = float(cluster["window_mean_conf_max"])
    min_bricks = int(cluster["min_bricks_in_window"])
    null_value = _null_conf_value(cluster)
    options = [int(x) for x in (cluster.get("window_ms_options") or []) if int(x) > 0]
    tape_start = words[0]["start_ms"]
    tape_end = words[-1]["end_ms"]
    spans: list[tuple[int, int]] = []
    for size in options:
        step = max(500, size // 2)
        t = tape_start
        while t < tape_end:
            lo, hi = t, t + size
            idx = [k for k, w in enumerate(words) if w["start_ms"] < hi and w["end_ms"] > lo]
            t += step
            if not idx:
                continue
            member = [words[k] for k in idx]
            lows = sum(1 for w in member if w["band"] == "low")
            if lows <= 0:
                continue
            if _mean_conf(member, null_value=null_value) < mean_max or lows >= min_bricks:
                spans.append((idx[0], idx[-1]))
    return spans


def _merge_spans(
    spans: list[tuple[int, int, str]],
) -> list[tuple[int, int, list[str]]]:
    """Union overlapping tier hits into the widest span, keeping tiers_fired."""
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: (s[0], s[1]))
    merged: list[list[Any]] = []
    for start, end, kind in ordered:
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
            if kind not in merged[-1][2]:
                merged[-1][2].append(kind)
        else:
            merged.append([start, end, [kind]])
    return [(int(m[0]), int(m[1]), list(m[2])) for m in merged]


def _segments_overlapping(
    segments: list[dict[str, Any]],
    start_ms: int,
    end_ms: int,
) -> list[tuple[str, int]]:
    """(segment_id, overlap_ms) for every segment intersecting the span."""
    hits: list[tuple[str, int]] = []
    for seg in segments:
        sid = str(seg.get("segment_id") or "")
        if not sid:
            continue
        s = _ms(seg, "start_ms")
        e = _ms(seg, "end_ms")
        overlap = min(end_ms, e) - max(start_ms, s)
        if overlap > 0:
            hits.append((sid, overlap))
    hits.sort(key=lambda row: row[1], reverse=True)
    return hits


def _failure_mode(*, padded: bool, non_ascii: bool, uncommon: bool) -> str:
    """Narrow demotion — only unpadded spans with zero lexicon signal become noise."""
    if non_ascii:
        return "code_switch"
    if uncommon:
        return "domain_lexicon"
    if not padded:
        return "noise"
    return "uncertain"


def scan_low_conf_islands(
    words: list[dict[str, Any]],
    segments: list[dict[str, Any]] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the four-tier ladder over G0 words; returns the ``low_conf_islands`` doc."""
    conf = low_conf_selection_cfg(cfg)
    cluster = conf["cluster"]
    low = float(cluster["low_confidence_threshold"])
    high = float(cluster["high_confidence_threshold"])
    null_value = _null_conf_value(cluster)
    prepared = _prepare_words(list(words or []), low=low, high=high)
    segs = [s for s in (segments or []) if isinstance(s, dict) and s.get("segment_id")]

    doc: dict[str, Any] = {
        "version": 1,
        "detector": {
            "ladder": list(LADDER),
            "recall_first": bool(conf.get("recall_first", True)),
            "low_confidence_threshold": low,
            "high_confidence_threshold": high,
            "null_confidence_as": str(cluster.get("null_confidence_as") or "mid"),
        },
        "islands": [],
        "word_count": len(prepared),
        "island_count": 0,
        "suspect_count": 0,
    }
    if not prepared:
        doc["skip_reason"] = "no_words"
        return doc

    tiered: list[tuple[int, int, str]] = []
    for start, end in _tier_tight(prepared, cluster=cluster):
        tiered.append((start, end, "tight"))
    for start, end in _tier_loose(prepared, cluster=cluster):
        tiered.append((start, end, "loose"))
    for start, end in _tier_window(prepared, cluster=cluster):
        tiered.append((start, end, "window"))

    islands: list[dict[str, Any]] = []
    for idx, (start, end, tiers) in enumerate(_merge_spans(tiered), start=1):
        member = prepared[start : end + 1]
        if not member:
            continue
        low_idx = [k for k in range(start, end + 1) if prepared[k]["band"] == "low"]
        if not low_idx:
            continue
        lows = [prepared[k] for k in low_idx]
        padded, left_pad, right_pad = _pad_quality(
            prepared, low_idx[0], low_idx[-1], cluster=cluster
        )
        non_ascii = _has_non_ascii(member)
        uncommon = _has_uncommon_english(member)
        kind = max(tiers, key=lambda t: _KIND_RANK.get(t, 0))
        span_start = member[0]["start_ms"]
        span_end = member[-1]["end_ms"]
        overlaps = _segments_overlapping(segs, span_start, span_end)
        islands.append(
            {
                "island_id": f"lci_{idx:03d}",
                "cluster_kind": kind,
                "tiers_fired": sorted(tiers, key=lambda t: _KIND_RANK.get(t, 0)),
                "start_ms": span_start,
                "end_ms": span_end,
                "low_word_count": len(lows),
                "word_count": len(member),
                "sprinkle_high_count": sum(1 for w in member if w["band"] == "high"),
                "low_ratio": round(len(lows) / len(member), 4),
                "mean_confidence": round(_mean_conf(member, null_value=null_value), 4),
                "padded": padded,
                "left_pad_text": " ".join(left_pad)[:160],
                "right_pad_text": " ".join(right_pad)[:160],
                "island_text": " ".join(w["text"] for w in member)[:400],
                "non_ascii": non_ascii,
                "uncommon_english": uncommon,
                "failure_mode": _failure_mode(
                    padded=padded, non_ascii=non_ascii, uncommon=uncommon
                ),
                "straddles_segment_ids": [sid for sid, _ in overlaps],
                "primary_segment_id": overlaps[0][0] if overlaps else None,
            }
        )

    # Tier 4 — whole-segment soft density flags (fail-open safety net).
    soft_density = float(cluster["segment_soft_density"])
    hard_ids = {sid for isl in islands for sid in isl["straddles_segment_ids"]}
    soft_rows: list[dict[str, Any]] = []
    for seg in segs:
        sid = str(seg["segment_id"])
        s, e = _ms(seg, "start_ms"), _ms(seg, "end_ms")
        member = [w for w in prepared if w["start_ms"] < e and w["end_ms"] > s]
        if not member:
            continue
        lows = [w for w in member if w["band"] == "low"]
        if not lows:
            continue
        ratio = len(lows) / len(member)
        if ratio < soft_density:
            continue
        soft_rows.append(
            {
                "island_id": f"lcs_{sid}",
                "cluster_kind": "segment_soft",
                "tiers_fired": ["segment_soft"],
                "start_ms": s,
                "end_ms": e,
                "low_word_count": len(lows),
                "word_count": len(member),
                "sprinkle_high_count": sum(1 for w in member if w["band"] == "high"),
                "low_ratio": round(ratio, 4),
                "mean_confidence": round(_mean_conf(member, null_value=null_value), 4),
                "padded": True,
                "left_pad_text": "",
                "right_pad_text": "",
                "island_text": "",
                "non_ascii": _has_non_ascii(member),
                "uncommon_english": _has_uncommon_english(member),
                "failure_mode": "uncertain",
                "straddles_segment_ids": [sid],
                "primary_segment_id": sid,
                "soft": True,
                "superseded_by_hard_island": sid in hard_ids,
            }
        )

    all_islands = [*islands, *soft_rows]
    doc["islands"] = all_islands
    doc["island_count"] = len(all_islands)
    doc["suspect_count"] = len([i for i in all_islands if i["failure_mode"] != "noise"])
    doc["tier_counts"] = {
        kind: len([i for i in all_islands if kind in (i.get("tiers_fired") or [])])
        for kind in LADDER
    }
    return doc


def run_low_conf_island_scan(ctx: RunContext, *, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load G0 words + manifest, run the ladder, write ``analysis/low_conf_islands.json``."""
    conf = low_conf_selection_cfg(cfg)
    if not conf.get("enabled", True):
        doc = {
            "version": 1,
            "detector": {"ladder": list(LADDER), "recall_first": False},
            "islands": [],
            "island_count": 0,
            "suspect_count": 0,
            "skip_reason": "disabled",
        }
        ctx.write_json(ISLANDS_PATH, doc)
        return doc

    if not ctx.artifact_exists("transcript/full.json"):
        doc = {
            "version": 1,
            "detector": {"ladder": list(LADDER), "recall_first": True},
            "islands": [],
            "island_count": 0,
            "suspect_count": 0,
            "skip_reason": "missing_transcript",
        }
        ctx.write_json(ISLANDS_PATH, doc)
        return doc

    transcript = ctx.read_json("transcript/full.json")
    words = (transcript.get("words") or []) if isinstance(transcript, dict) else []
    segments: list[dict[str, Any]] = []
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        if isinstance(manifest, dict):
            segments = [s for s in (manifest.get("segments") or []) if isinstance(s, dict)]

    doc = scan_low_conf_islands(words, segments, cfg)
    ctx.write_json(ISLANDS_PATH, doc)
    return doc


def load_islands(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(ISLANDS_PATH):
        return {"version": 1, "islands": []}
    try:
        doc = ctx.read_json(ISLANDS_PATH)
    except Exception:
        return {"version": 1, "islands": []}
    return doc if isinstance(doc, dict) else {"version": 1, "islands": []}


def islands_for_span(
    islands_doc: dict[str, Any],
    start_ms: int,
    end_ms: int,
    *,
    include_noise: bool = False,
    include_soft: bool = True,
) -> list[dict[str, Any]]:
    """Islands intersecting a time span (suspect-only by default)."""
    out: list[dict[str, Any]] = []
    for isl in islands_doc.get("islands") or []:
        if not isinstance(isl, dict):
            continue
        if not include_noise and isl.get("failure_mode") == "noise":
            continue
        if not include_soft and isl.get("soft"):
            continue
        if min(int(end_ms), _ms(isl, "end_ms")) - max(int(start_ms), _ms(isl, "start_ms")) <= 0:
            continue
        out.append(isl)
    return out


def _island_density_credit(island: dict[str, Any], overlap_ratio: float) -> float:
    kind = str(island.get("cluster_kind") or "tight")
    weight = _KIND_WEIGHT.get(kind, 0.5)
    lows = float(island.get("low_word_count") or 0) * max(0.0, min(1.0, overlap_ratio))
    mean_conf = island.get("mean_confidence")
    inverse = 1.0 - float(mean_conf if mean_conf is not None else 0.875)
    # Sprinkle never dilutes eligibility — low_ratio only modulates mildly.
    ratio_mod = 0.75 + 0.25 * float(island.get("low_ratio") or 0.0)
    return weight * lows * max(inverse, 0.05) * ratio_mod


def compute_density_ranking(
    ctx: RunContext,
    islands_doc: dict[str, Any] | None = None,
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rank every native segment by low-conf cluster density (per-minute normalized)."""
    conf = low_conf_selection_cfg(cfg)
    doc = islands_doc if isinstance(islands_doc, dict) else load_islands(ctx)
    segments: list[dict[str, Any]] = []
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        if isinstance(manifest, dict):
            segments = [s for s in (manifest.get("segments") or []) if isinstance(s, dict)]

    rows: list[dict[str, Any]] = []
    for seg in segments:
        sid = str(seg.get("segment_id") or "")
        if not sid:
            continue
        start, end = _ms(seg, "start_ms"), _ms(seg, "end_ms")
        duration_ms = max(0, end - start)
        hits = islands_for_span(doc, start, end)
        hard_hits = [i for i in hits if not i.get("soft")]
        # segment_soft only contributes when no hard island already covers the segment.
        usable = hard_hits or [i for i in hits if i.get("soft")]
        raw = 0.0
        low_words = 0
        island_ids: list[str] = []
        kinds: list[str] = []
        for isl in usable:
            span = max(1, _ms(isl, "end_ms") - _ms(isl, "start_ms"))
            overlap = max(0, min(end, _ms(isl, "end_ms")) - max(start, _ms(isl, "start_ms")))
            ratio = overlap / span
            raw += _island_density_credit(isl, ratio)
            low_words += int(round(float(isl.get("low_word_count") or 0) * ratio))
            island_ids.append(str(isl.get("island_id")))
            kinds.append(str(isl.get("cluster_kind")))
        minutes = max(duration_ms / 60000.0, 1 / 60.0)
        density = raw / minutes if raw > 0 else 0.0
        rows.append(
            {
                "segment_id": sid,
                "start_ms": start,
                "end_ms": end,
                "duration_ms": duration_ms,
                "density": round(density, 6),
                "raw_credit": round(raw, 6),
                "low_word_count": low_words,
                "island_ids": island_ids,
                "cluster_kinds": sorted(set(kinds)),
            }
        )

    rows.sort(key=lambda r: (-float(r["density"]), str(r["segment_id"])))
    total = len(rows)
    for idx, row in enumerate(rows):
        row["rank"] = idx + 1
        row["percentile"] = round((total - idx) / total, 6) if total else 0.0

    out = {
        "version": 1,
        "segment_count": total,
        "positive_count": len([r for r in rows if float(r["density"]) > 0]),
        "top_percentile": float(conf.get("top_percentile") or 0.10),
        "min_positive_density": float(conf.get("min_positive_density") or 0.0),
        "ranking": rows,
    }
    ctx.write_json(DENSITY_PATH, out)
    return out


def write_low_conf_must_keep(
    ctx: RunContext,
    ranking: dict[str, Any] | None = None,
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Hard-include the densest decile of positive-density natives."""
    conf = low_conf_selection_cfg(cfg)
    doc = ranking if isinstance(ranking, dict) else None
    if doc is None:
        if ctx.artifact_exists(DENSITY_PATH):
            raw = ctx.read_json(DENSITY_PATH)
            doc = raw if isinstance(raw, dict) else None
        if doc is None:
            doc = compute_density_ranking(ctx, cfg=cfg)

    rows = [r for r in (doc.get("ranking") or []) if isinstance(r, dict)]
    floor = float(conf.get("min_positive_density") or 0.0)
    positives = [r for r in rows if float(r.get("density") or 0.0) > floor]
    total = len(rows)
    top_k = max(1, math.ceil(float(conf.get("top_percentile") or 0.10) * total)) if total else 0
    picked = positives[: min(top_k, len(positives))]

    out = {
        "version": 1,
        "enabled": bool(conf.get("enabled", True)),
        "enforcement_mode": str(conf.get("enforcement_mode") or "authoritative"),
        "top_percentile": float(conf.get("top_percentile") or 0.10),
        "top_k": top_k,
        "segment_count": total,
        "positive_count": len(positives),
        "must_keep_segment_ids": [str(r["segment_id"]) for r in picked],
        "scores": [
            {
                "segment_id": str(r["segment_id"]),
                "density": r.get("density"),
                "rank": r.get("rank"),
                "percentile": r.get("percentile"),
                "cluster_kinds": r.get("cluster_kinds") or [],
            }
            for r in picked
        ],
    }
    ctx.write_json(MUST_KEEP_PATH, out)
    _write_soft_boosts_for_non_decile(ctx, positives, must_keep=set(out["must_keep_segment_ids"]), cfg=conf)
    return out


def _write_soft_boosts_for_non_decile(
    ctx: RunContext,
    positives: list[dict[str, Any]],
    *,
    must_keep: set[str],
    cfg: dict[str, Any],
) -> None:
    """Retain soft prefer-include for positive-density natives outside the hard top decile."""
    soft_rows: list[dict[str, Any]] = []
    strength = 0.12
    for row in positives:
        sid = str(row.get("segment_id") or "")
        if not sid or sid in must_keep:
            continue
        density = float(row.get("density") or 0.0)
        soft_rows.append(
            {
                "segment_id": sid,
                "soft_boost": round(min(0.35, strength + 0.05 * density), 4),
                "importance_score": round(min(1.0, 0.55 + 0.1 * density), 4),
                "source": "low_conf_density_non_decile",
                "cluster_kinds": row.get("cluster_kinds") or [],
                "density": row.get("density"),
            }
        )
    if not soft_rows:
        return
    # Merge into the soft-boost artifact if present so ranking/pack still see them.
    path = "analysis/stt_lexicon_island_boosts.json"
    existing: dict[str, Any] = {"version": 1, "mode": "soft_prefer_include_only", "priors": []}
    if ctx.artifact_exists(path):
        try:
            loaded = ctx.read_json(path)
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:
            pass
    by_sid = {
        str(r.get("segment_id")): dict(r)
        for r in (existing.get("priors") or [])
        if isinstance(r, dict) and r.get("segment_id")
    }
    for row in soft_rows:
        sid = str(row["segment_id"])
        prev = by_sid.get(sid)
        if prev is None or float(row["soft_boost"]) > float(prev.get("soft_boost") or 0):
            by_sid[sid] = {**(prev or {}), **row}
    existing["priors"] = sorted(
        by_sid.values(), key=lambda r: float(r.get("soft_boost") or 0), reverse=True
    )
    existing["mode"] = existing.get("mode") or "soft_prefer_include_only"
    existing["version"] = 1
    ctx.write_json(path, existing)


def low_conf_must_keep_ids(ctx: RunContext) -> set[str]:
    """Soft advisory ids (available regardless of enforcement mode)."""
    if not ctx.artifact_exists(MUST_KEEP_PATH):
        return set()
    try:
        doc = ctx.read_json(MUST_KEEP_PATH)
    except Exception:
        return set()
    if not isinstance(doc, dict):
        return set()
    return {str(sid) for sid in (doc.get("must_keep_segment_ids") or []) if sid}


def authoritative_low_conf_must_keep_ids(
    ctx: RunContext,
    *,
    cfg: dict[str, Any] | None = None,
) -> set[str]:
    """Hard must_keep only when ``low_conf_selection.enforcement_mode=authoritative``."""
    conf = low_conf_selection_cfg(cfg)
    if not conf.get("enabled", True):
        return set()
    if str(conf.get("enforcement_mode") or "").lower() != "authoritative":
        return set()
    if ctx.artifact_exists(MUST_KEEP_PATH):
        try:
            doc = ctx.read_json(MUST_KEEP_PATH)
        except Exception:
            doc = None
        if isinstance(doc, dict) and str(doc.get("enforcement_mode") or "").lower() != "authoritative":
            return set()
    return low_conf_must_keep_ids(ctx)


__all__ = [
    "DENSITY_PATH",
    "ISLANDS_PATH",
    "LADDER",
    "MUST_KEEP_PATH",
    "authoritative_low_conf_must_keep_ids",
    "compute_density_ranking",
    "enabled",
    "islands_for_span",
    "load_islands",
    "low_conf_must_keep_ids",
    "low_conf_selection_cfg",
    "run_low_conf_island_scan",
    "scan_low_conf_islands",
    "word_band",
    "write_low_conf_must_keep",
]
