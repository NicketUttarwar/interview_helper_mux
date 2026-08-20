"""Post-G0 speaker_id flip detect → local-speech YES/NO → relabel or absorb.

Idempotent host pass at the start of interview_spine_build. Fail-open keeps
original labels. Syntax hang still blocks a novel-style keeper end if verify
misses or says NO. Nested um/uh islands are absorbed into the enclosing
monologue for cuts (word speaker_id stays truthful).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from interview_mux.audio_clips import extract_clip
from interview_mux.config import merged_config
from interview_mux.gap_vo_prior_context import (
    CLAUSE_CONTINUE_MAX_GAP_MS,
    ends_hanging_setup,
    is_filled_pause_only_text,
)
from interview_mux.local_runtime import LocalRuntimeUnavailable, run_runtime_json
from interview_mux.run_context import RunContext

REPAIRS_REL = "transcript/diarization_repairs.json"
PROBE_ID = "vprobe.same_speaker_pair"
DEFAULT_MAX_PAIRS = 200
DEFAULT_MICRO_OTHER_MAX_MS = 700
DEFAULT_MICRO_OTHER_MAX_WORDS = 2
DEFAULT_DOMINANT_SPEAKER_MIN_SHARE = 0.98

VerifyFn = Callable[[Path, Path], str | None]


def _speech_cfg() -> dict[str, Any]:
    return dict((merged_config().get("local_speech") or {}))


def micro_island_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    speech = dict(cfg) if cfg else _speech_cfg()
    return {
        "micro_other_max_ms": int(
            speech.get("micro_other_max_ms") or DEFAULT_MICRO_OTHER_MAX_MS
        ),
        "micro_other_max_words": int(
            speech.get("micro_other_max_words") or DEFAULT_MICRO_OTHER_MAX_WORDS
        ),
        "dominant_speaker_min_share": float(
            speech.get("dominant_speaker_min_share") or DEFAULT_DOMINANT_SPEAKER_MIN_SHARE
        ),
    }


def _word_text(w: dict[str, Any]) -> str:
    return str(w.get("text") or w.get("word") or "").strip()


def _ordered_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = [w for w in words if isinstance(w, dict) and _word_text(w)]
    ordered.sort(key=lambda w: int(w.get("start_ms") or 0))
    return ordered


def detect_speaker_flips(
    words: list[dict[str, Any]],
    *,
    max_gap_ms: int = CLAUSE_CONTINUE_MAX_GAP_MS,
) -> list[dict[str, Any]]:
    """Adjacent word pairs where speaker_id changes and 0 < gap ≤ max_gap_ms.

    Hanging-setup flips sort first, then remaining by gap then time.
    """
    ordered = _ordered_words(words)
    out: list[dict[str, Any]] = []
    for i in range(len(ordered) - 1):
        a, b = ordered[i], ordered[i + 1]
        a_id = str(a.get("speaker_id") or "")
        b_id = str(b.get("speaker_id") or "")
        if not a_id or not b_id or a_id == b_id:
            continue
        a_end = int(a.get("end_ms") or 0)
        b_start = int(b.get("start_ms") or 0)
        gap = b_start - a_end
        if gap <= 0 or gap > max_gap_ms:
            continue
        before = [
            w
            for w in ordered[: i + 1]
            if int(w.get("end_ms") or 0) >= a_end - 12_000
        ]
        close = " ".join(_word_text(w) for w in before[-24:])
        out.append(
            {
                "index": i,
                "from_speaker_id": a_id,
                "to_speaker_id": b_id,
                "end_ms": a_end,
                "next_start_ms": b_start,
                "gap_ms": gap,
                "hanging_setup": ends_hanging_setup(close),
                "close_text": close[-120:],
                "next_text": _word_text(b),
            }
        )
    out.sort(key=lambda row: (not row["hanging_setup"], row["gap_ms"], row["end_ms"]))
    return out


def _later_island(
    words: list[dict[str, Any]],
    *,
    from_end_ms: int,
    speaker_id: str,
) -> list[dict[str, Any]]:
    island: list[dict[str, Any]] = []
    in_run = False
    prev_end = from_end_ms
    for w in _ordered_words(words):
        start = int(w.get("start_ms") or 0)
        if start < from_end_ms:
            continue
        sid = str(w.get("speaker_id") or "")
        gap = start - prev_end
        if not in_run:
            if sid != speaker_id:
                continue
            in_run = True
        elif gap > CLAUSE_CONTINUE_MAX_GAP_MS or sid != speaker_id:
            break
        island.append(w)
        prev_end = int(w.get("end_ms") or start)
    return island


def _speaker_runs(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = _ordered_words(words)
    runs: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    prev_end = 0
    for idx, w in enumerate(ordered):
        sid = str(w.get("speaker_id") or "")
        start = int(w.get("start_ms") or 0)
        end = int(w.get("end_ms") or start)
        gap = start - prev_end if cur is not None else 0
        if (
            cur is None
            or sid != cur["speaker_id"]
            or gap > CLAUSE_CONTINUE_MAX_GAP_MS
        ):
            if cur is not None:
                runs.append(cur)
            cur = {
                "speaker_id": sid,
                "start_idx": idx,
                "end_idx": idx,
                "start_ms": start,
                "end_ms": end,
                "words": [w],
            }
        else:
            cur["end_idx"] = idx
            cur["end_ms"] = end
            cur["words"].append(w)
        prev_end = end
    if cur is not None:
        runs.append(cur)
    return runs


def _run_is_filled_pause_micro(run: dict[str, Any], cfg: dict[str, Any]) -> bool:
    toks = [_word_text(w) for w in run.get("words") or [] if _word_text(w)]
    if not toks:
        return False
    if len(toks) > int(cfg["micro_other_max_words"]):
        return False
    dur = max(0, int(run.get("end_ms") or 0) - int(run.get("start_ms") or 0))
    if dur > int(cfg["micro_other_max_ms"]):
        return False
    return is_filled_pause_only_text(" ".join(toks))


def _enclosing_span(
    runs: list[dict[str, Any]],
    micro_i: int,
    cfg: dict[str, Any],
) -> tuple[list[dict[str, Any]], str] | None:
    """Expand around a micro run until a non-micro other-speaker turn.

    Requires the same primary speaker on both sides (nested island).
    """
    left_primary = ""
    j = micro_i - 1
    while j >= 0:
        if _run_is_filled_pause_micro(runs[j], cfg):
            j -= 1
            continue
        left_primary = str(runs[j].get("speaker_id") or "")
        break
    right_primary = ""
    k = micro_i + 1
    while k < len(runs):
        if _run_is_filled_pause_micro(runs[k], cfg):
            k += 1
            continue
        right_primary = str(runs[k].get("speaker_id") or "")
        break
    if not left_primary or not right_primary or left_primary != right_primary:
        return None
    start = j if j >= 0 else micro_i
    end = k if k < len(runs) else micro_i
    return runs[start : end + 1], left_primary


def _duration_share(span_runs: list[dict[str, Any]], primary: str) -> float:
    total = 0
    primary_ms = 0
    for run in span_runs:
        dur = max(0, int(run.get("end_ms") or 0) - int(run.get("start_ms") or 0))
        total += dur
        if str(run.get("speaker_id") or "") == primary:
            primary_ms += dur
    if total <= 0:
        return 0.0
    return primary_ms / total


def absorbable_micro_runs(
    words: list[dict[str, Any]],
    *,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Filled-pause other-speaker islands nested in a ≥98% dominant-speaker run."""
    resolved = micro_island_cfg(cfg)
    runs = _speaker_runs(words)
    out: list[dict[str, Any]] = []
    for i, run in enumerate(runs):
        if not _run_is_filled_pause_micro(run, resolved):
            continue
        enclosed = _enclosing_span(runs, i, resolved)
        if enclosed is None:
            continue
        span, primary = enclosed
        if str(run.get("speaker_id") or "") == primary:
            continue
        share = _duration_share(span, primary)
        if share < float(resolved["dominant_speaker_min_share"]):
            continue
        out.append(
            {
                "start_ms": int(run["start_ms"]),
                "end_ms": int(run["end_ms"]),
                "speaker_id": str(run["speaker_id"]),
                "primary_speaker_id": primary,
                "dominant_share": share,
                "word_count": len(run.get("words") or []),
            }
        )
    return out


def absorbable_micro_word_indexes(
    words: list[dict[str, Any]],
    *,
    cfg: dict[str, Any] | None = None,
) -> set[int]:
    """Indexes into time-sorted content words that belong to absorbable micro islands."""
    ordered = _ordered_words(words)
    islands = absorbable_micro_runs(ordered, cfg=cfg)
    if not islands:
        return set()
    ranges = [(int(r["start_ms"]), int(r["end_ms"])) for r in islands]
    idxs: set[int] = set()
    for i, w in enumerate(ordered):
        start = int(w.get("start_ms") or 0)
        end = int(w.get("end_ms") or start)
        for a, b in ranges:
            if start >= a - 5 and end <= b + 5:
                idxs.add(i)
                break
    return idxs


def island_is_absorbable_micro(
    words: list[dict[str, Any]],
    island: list[dict[str, Any]],
    *,
    cfg: dict[str, Any] | None = None,
) -> bool:
    if not island:
        return False
    start = int(island[0].get("start_ms") or 0)
    end = int(island[-1].get("end_ms") or start)
    for row in absorbable_micro_runs(words, cfg=cfg):
        if abs(int(row["start_ms"]) - start) <= 20 and abs(int(row["end_ms"]) - end) <= 20:
            return True
    return False


def _clip_window(words: list[dict[str, Any]], center_ms: int, *, before: bool, span_ms: int = 4000) -> tuple[int, int]:
    if before:
        start = max(0, center_ms - span_ms)
        return start, center_ms
    return center_ms, center_ms + span_ms


def _relabel_later_run(words: list[dict[str, Any]], *, from_end_ms: int, old_id: str, new_id: str) -> int:
    """Rewrite the immediate later island of old_id to new_id.

    Stops at a different speaker or a gap larger than the 4s continuation ceiling.
    """
    changed = 0
    in_run = False
    prev_end = from_end_ms
    for w in sorted(
        [x for x in words if isinstance(x, dict)],
        key=lambda row: int(row.get("start_ms") or 0),
    ):
        start = int(w.get("start_ms") or 0)
        if start < from_end_ms:
            continue
        sid = str(w.get("speaker_id") or "")
        gap = start - prev_end
        if not in_run:
            if sid != old_id:
                continue
            in_run = True
        elif gap > CLAUSE_CONTINUE_MAX_GAP_MS or sid != old_id:
            break
        w["speaker_id"] = new_id
        changed += 1
        prev_end = int(w.get("end_ms") or start)
    return changed


def _refresh_speakers_doc(words: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for w in words:
        sid = str(w.get("speaker_id") or "")
        if sid:
            counts[sid] = counts.get(sid, 0) + 1
    return {
        "speakers": [{"id": sid, "role": "unknown", "word_count": counts[sid]} for sid in sorted(counts)]
    }


def _rebuild_speaker_flows(ctx: RunContext, transcript: dict[str, Any]) -> None:
    if not ctx.artifact_exists("transcript/speaker_flows.json"):
        return
    from interview_mux.audio_probe_flows import build_speaker_flows

    ctx.write_json(
        "transcript/speaker_flows.json",
        {"version": 1, "flows": build_speaker_flows(transcript)},
    )


def _verify_pair_mlx(clip_a: Path, clip_b: Path, *, ctx: RunContext | None, stage: str) -> str | None:
    speech = _speech_cfg()
    timeout = int(speech.get("diarization_verify_timeout_sec") or speech.get("interrogate_timeout_sec") or 300)
    try:
        result = run_runtime_json(
            "speech",
            "tools/s2s_interrogate.py",
            {
                "mode": "speaker_pair",
                "clip_a_wav": str(clip_a),
                "clip_b_wav": str(clip_b),
                "probe_id": PROBE_ID,
                "output_contract": "YES_NO",
            },
            timeout_sec=timeout,
            ctx=ctx,
            stage=stage,
        )
    except LocalRuntimeUnavailable:
        return None
    except Exception:
        return None
    verdict = str(result.get("verdict") or result.get("answer") or "").strip().upper()
    if verdict in {"YES", "NO"}:
        return verdict
    text = str(result.get("text") or result.get("stt_text") or "").strip().upper()
    if text.startswith("YES"):
        return "YES"
    if text.startswith("NO"):
        return "NO"
    return None


def _pair_overlaps_micro(cand: dict[str, Any], micros: list[dict[str, Any]]) -> bool:
    start = int(cand.get("next_start_ms") or 0)
    for row in micros:
        if int(row["start_ms"]) - 20 <= start <= int(row["end_ms"]) + 20:
            return True
    return False


def forced_diarization_fuse_verdicts(
    ctx: RunContext,
    segments: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Deterministic fuse verdicts for YES-same seams and leftover micro keepers."""
    if not ctx.artifact_exists(REPAIRS_REL):
        return []
    try:
        doc = ctx.read_json(REPAIRS_REL)
    except Exception:
        return []
    if not isinstance(doc, dict):
        return []
    if segments is None:
        if not ctx.artifact_exists("segments/manifest.json"):
            return []
        try:
            manifest = ctx.read_json("segments/manifest.json")
        except Exception:
            return []
        segments = [
            s
            for s in ((manifest or {}).get("segments") or [])
            if isinstance(s, dict) and s.get("segment_id")
        ]
    rows = sorted(
        [s for s in (segments or []) if isinstance(s, dict)],
        key=lambda s: int(s.get("start_ms") or 0),
    )
    if len(rows) < 2:
        return []

    def _straddle(seam_end: int, next_start: int) -> tuple[str, str] | None:
        eps = 120
        for i in range(len(rows) - 1):
            a, b = rows[i], rows[i + 1]
            a_end = int(a.get("end_ms") or 0)
            b_start = int(b.get("start_ms") or 0)
            a_start = int(a.get("start_ms") or 0)
            b_end = int(b.get("end_ms") or 0)
            covers = a_start < next_start <= a_end + eps and b_start - eps <= seam_end < b_end
            near = abs(a_end - seam_end) <= eps and abs(b_start - next_start) <= eps
            if near or covers:
                return str(a["segment_id"]), str(b["segment_id"])
        return None

    def _adjacent_around(start_ms: int, end_ms: int) -> list[tuple[str, str]]:
        hits: list[tuple[str, str]] = []
        for i in range(len(rows) - 1):
            a, b = rows[i], rows[i + 1]
            a_end = int(a.get("end_ms") or 0)
            b_start = int(b.get("start_ms") or 0)
            a_start = int(a.get("start_ms") or 0)
            b_end = int(b.get("end_ms") or 0)
            a_is_micro = a_start <= start_ms + 80 and a_end >= end_ms - 80
            b_is_micro = b_start <= start_ms + 80 and b_end >= end_ms - 80
            near = abs(a_end - start_ms) <= 120 and abs(b_start - start_ms) <= 120
            if a_is_micro or b_is_micro or near:
                hits.append((str(a["segment_id"]), str(b["segment_id"])))
        return hits

    verdicts: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for pair in doc.get("pairs") or []:
        if not isinstance(pair, dict):
            continue
        action = str(pair.get("action") or "")
        verdict = str(pair.get("verdict") or "")
        if action == "absorb_micro":
            forced_by = "micro_other_absorb"
            reason = "micro_backchannel_island"
        elif action == "relabel" or verdict == "yes_same":
            forced_by = "diarization_yes_same"
            reason = "same_speaker_false_split"
        else:
            continue
        island_start = int(
            pair.get("island_start_ms")
            or pair.get("next_start_ms")
            or pair.get("end_ms")
            or 0
        )
        island_end = int(pair.get("island_end_ms") or island_start)
        seam_end = int(pair.get("seam_end_ms") or pair.get("start_ms") or island_start)
        next_start = int(pair.get("next_start_ms") or pair.get("end_ms") or island_start)
        id_pairs = _adjacent_around(island_start, island_end)
        if not id_pairs:
            fallback = _straddle(seam_end, next_start)
            if fallback:
                id_pairs = [fallback]
        for earlier, later in id_pairs:
            key = (earlier, later)
            if key in seen:
                continue
            seen.add(key)
            verdicts.append(
                {
                    "decision": "fuse",
                    "forced_by": forced_by,
                    "reason_code": reason,
                    "pair_id": f"{earlier}__{later}",
                    "earlier_segment_id": earlier,
                    "later_segment_id": later,
                    "deterministic_hints": {
                        "hanging_setup_end": bool(pair.get("hanging_setup")),
                    },
                    "rationale": f"{forced_by} seam {seam_end}-{next_start}",
                }
            )
    return verdicts


def stamp_fused_segment_ids(ctx: RunContext, id_remap: dict[str, str]) -> None:
    """Record consumed keeper ids on the matching repairs row."""
    if not id_remap or not ctx.artifact_exists(REPAIRS_REL):
        return
    try:
        doc = ctx.read_json(REPAIRS_REL)
    except Exception:
        return
    if not isinstance(doc, dict):
        return
    changed = False
    for pair in doc.get("pairs") or []:
        if not isinstance(pair, dict):
            continue
        if str(pair.get("action") or "") not in {"relabel", "absorb_micro"} and str(
            pair.get("verdict") or ""
        ) != "yes_same":
            continue
        fused = [sid for sid in id_remap if sid]
        if not fused:
            continue
        survivors = sorted({id_remap[s] for s in fused})
        pair["fused_segment_ids"] = list(dict.fromkeys([*survivors, *sorted(fused)]))
        changed = True
    if changed:
        ctx.write_json(REPAIRS_REL, doc)


def run_diarization_verify(
    ctx: RunContext,
    *,
    stage: str = "interview_spine_build",
    verify_pair: VerifyFn | None = None,
    source_wav: Path | None = None,
) -> dict[str, Any]:
    """Detect flips, verify with local speech, relabel YES pairs. Fail-open keeps labels."""
    transcript = ctx.read_json("transcript/full.json")
    words = [w for w in (transcript.get("words") or []) if isinstance(w, dict)]
    speech = _speech_cfg()
    cap = int(speech.get("diarization_verify_max_pairs") or DEFAULT_MAX_PAIRS)
    all_candidates = detect_speaker_flips(words)
    truncated = max(0, len(all_candidates) - max(0, cap))
    candidates = all_candidates[: max(0, cap)]
    micros = absorbable_micro_runs(words)

    wav = source_wav
    if wav is None:
        preclean = ctx.read_path("preclean", "isolated.wav")
        ingest = ctx.read_path("ingest", "normalized.wav")
        if preclean.is_file():
            wav = preclean
        elif ingest.is_file():
            wav = ingest

    pairs: list[dict[str, Any]] = []
    relabeled = 0
    absorbed = 0
    clip_root = ctx.run_dir / "transcript" / "diarization_verify_clips"
    fn = verify_pair
    covered_micro_starts: set[int] = set()
    for n, cand in enumerate(candidates):
        row = {
            "start_ms": cand["end_ms"],
            "end_ms": cand["next_start_ms"],
            "seam_end_ms": cand["end_ms"],
            "next_start_ms": cand["next_start_ms"],
            "from_speaker_id": cand["from_speaker_id"],
            "to_speaker_id": cand["to_speaker_id"],
            "gap_ms": cand["gap_ms"],
            "hanging_setup": cand["hanging_setup"],
            "verdict": "skipped",
            "action": "keep",
            "clip_paths": {},
            "model_id": str(
                speech.get("diarization_model_id")
                or "mlx-community/diar_sortformer_4spk-v1-fp32"
            ),
        }
        island = _later_island(
            words, from_end_ms=cand["end_ms"], speaker_id=cand["to_speaker_id"]
        )
        micro = island_is_absorbable_micro(words, island) or _pair_overlaps_micro(cand, micros)
        if island:
            row["island_start_ms"] = int(island[0].get("start_ms") or cand["next_start_ms"])
            row["island_end_ms"] = int(island[-1].get("end_ms") or row["island_start_ms"])
        a_start, a_end = _clip_window(words, cand["end_ms"], before=True)
        b_start, b_end = _clip_window(words, cand["next_start_ms"], before=False)
        if a_end - a_start < 400 or b_end - b_start < 400:
            row["verdict"] = "skipped"
            row["reason"] = "clip_too_short"
            if micro:
                row["action"] = "absorb_micro"
                absorbed += 1
                covered_micro_starts.add(int(cand["next_start_ms"]))
            pairs.append(row)
            continue
        clip_a = clip_root / f"pair_{n:03d}_a.wav"
        clip_b = clip_root / f"pair_{n:03d}_b.wav"
        row["clip_paths"] = {"a": str(clip_a), "b": str(clip_b)}
        verdict: str | None = None
        try:
            if wav is None or not wav.is_file():
                raise RuntimeError("source wav missing")
            extract_clip(wav, clip_a, a_start, a_end)
            extract_clip(wav, clip_b, b_start, b_end)
            if fn is not None:
                verdict = fn(clip_a, clip_b)
            else:
                verdict = _verify_pair_mlx(clip_a, clip_b, ctx=ctx, stage=stage)
        except Exception as exc:  # noqa: BLE001 — fail-open
            row["reason"] = str(exc)[:300]
            verdict = None
        if micro:
            # Keep word speaker_id truthful; do not relabel a nested um as the main speaker.
            row["verdict"] = (
                "yes_same" if verdict == "YES" else "no_different" if verdict == "NO" else "skipped"
            )
            row["action"] = "absorb_micro"
            absorbed += 1
            covered_micro_starts.add(int(cand["next_start_ms"]))
        elif verdict == "YES":
            changed = _relabel_later_run(
                words,
                from_end_ms=cand["end_ms"],
                old_id=cand["to_speaker_id"],
                new_id=cand["from_speaker_id"],
            )
            row["verdict"] = "yes_same"
            row["action"] = "relabel" if changed else "keep"
            row["words_relabeled"] = changed
            relabeled += changed
        elif verdict == "NO":
            row["verdict"] = "no_different"
            row["action"] = "keep"
        else:
            row["verdict"] = "skipped"
            row["action"] = "keep"
        pairs.append(row)

    for micro_row in micros:
        start = int(micro_row["start_ms"])
        if any(abs(s - start) <= 30 for s in covered_micro_starts):
            continue
        pairs.append(
            {
                "start_ms": start,
                "end_ms": int(micro_row["end_ms"]),
                "seam_end_ms": start,
                "next_start_ms": start,
                "from_speaker_id": str(micro_row["primary_speaker_id"]),
                "to_speaker_id": str(micro_row["speaker_id"]),
                "gap_ms": 0,
                "hanging_setup": False,
                "verdict": "no_different",
                "action": "absorb_micro",
                "clip_paths": {},
                "model_id": str(
                    speech.get("diarization_model_id")
                    or "mlx-community/diar_sortformer_4spk-v1-fp32"
                ),
                "reason": "lexical_micro_island",
                "dominant_share": micro_row.get("dominant_share"),
                "island_start_ms": start,
                "island_end_ms": int(micro_row["end_ms"]),
            }
        )
        absorbed += 1

    if relabeled:
        transcript["words"] = words
        ctx.write_json("transcript/full.json", transcript)
        if ctx.artifact_exists("transcript/speakers.json"):
            ctx.write_json("transcript/speakers.json", _refresh_speakers_doc(words))
        _rebuild_speaker_flows(ctx, transcript)

    doc = {
        "version": 1,
        "applied": bool(relabeled or absorbed),
        "candidate_count": len(all_candidates),
        "candidates_truncated": truncated,
        "pairs": pairs,
    }
    ctx.write_json(REPAIRS_REL, doc)
    return doc
