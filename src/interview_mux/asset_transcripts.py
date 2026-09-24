"""Standardized sidecar transcripts for spoken assets + Apple master VTT assemble.

Sidecars are written as spoken assets appear (native segments, VO, spoken
transitions). ``run_master_transcript_build`` remaps those sidecars onto the
final EDL / master timeline after ``master/master.wav`` exists. It does not
re-transcribe the master.
"""

from __future__ import annotations

import re
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext

SCHEMA_VERSION = 1
INDEX_REL = "transcripts/index.json"
MASTER_JSON_REL = "master/transcript.json"
MASTER_VTT_REL = "master/transcript.vtt"
MASTER_TXT_REL = "master/transcript.txt"

KIND_FOLDERS = {
    "speech": "speech",
    "vo_pickup": "vo",
    "transition": "transition",
}

SPOKEN_EDL_TYPES = frozenset({"speech", "vo_pickup", "transition"})
CUE_MAX_MS = 8000
_SENTENCE_END = re.compile(r"[.!?…][\"')\]]*$")


def sidecar_rel(kind: str, asset_id: str) -> str:
    folder = KIND_FOLDERS[kind]
    return f"transcripts/{folder}/{asset_id}.json"


def _ms(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return default


def wav_duration_ms(path: Path | None) -> int:
    if path is None or not path.is_file():
        return 0
    try:
        with wave.open(str(path), "rb") as wf:
            rate = wf.getframerate() or 48000
            return int(1000 * wf.getnframes() / rate)
    except Exception:
        return 0


def _full_words(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("transcript/full.json"):
        return []
    doc = ctx.read_json("transcript/full.json")
    words = doc.get("words") if isinstance(doc, dict) else None
    if not isinstance(words, list):
        return []
    return [w for w in words if isinstance(w, dict) and str(w.get("text") or "").strip()]


def slice_words(
    words: list[dict[str, Any]],
    start_ms: int,
    end_ms: int,
) -> list[dict[str, Any]]:
    """Words overlapping [start_ms, end_ms) in source time."""
    out: list[dict[str, Any]] = []
    for word in words:
        ws = _ms(word.get("start_ms"), _ms(word.get("start_time")))
        we = _ms(word.get("end_ms"), _ms(word.get("end_time"), ws))
        if we <= start_ms or ws >= end_ms:
            continue
        out.append(
            {
                "text": str(word.get("text") or "").strip(),
                "start_ms": ws,
                "end_ms": max(we, ws),
                "speaker_id": str(word.get("speaker_id") or word.get("speaker") or ""),
            }
        )
    return out


def _join_text(words: list[dict[str, Any]]) -> str:
    return " ".join(str(w.get("text") or "").strip() for w in words if str(w.get("text") or "").strip())


def speaker_name_for(ctx: RunContext, speaker_id: str) -> str:
    sid = str(speaker_id or "").strip()
    if ctx.artifact_exists("understanding/speaker_delivery_plan.json"):
        try:
            plan = ctx.read_json("understanding/speaker_delivery_plan.json")
            labels = (plan or {}).get("address_labels") if isinstance(plan, dict) else {}
            if isinstance(labels, dict) and sid and str(labels.get(sid) or "").strip():
                return str(labels[sid]).strip()
        except Exception:
            pass
    rows: list[dict[str, Any]] = []
    if ctx.artifact_exists("understanding/speakers.json"):
        doc = ctx.read_json("understanding/speakers.json")
        raw = doc.get("speakers") if isinstance(doc, dict) else None
        if isinstance(raw, list):
            rows = [r for r in raw if isinstance(r, dict)]
    for row in rows:
        if str(row.get("speaker_id") or "") != sid:
            continue
        for key in ("display_name", "name", "label", "full_name"):
            val = str(row.get(key) or "").strip()
            if val and val.lower() not in {"unknown", "speaker", "spk"}:
                return val
        role = str(row.get("role") or "").strip()
        if role and role.lower() not in {"unknown"}:
            return role.replace("_", " ").title()
    return sid or "Speaker"


def vo_speaker_id(ctx: RunContext, line: dict[str, Any] | None = None) -> str:
    if isinstance(line, dict):
        for key in ("voice_speaker_id", "speaker_id", "clone_speaker_id"):
            val = str(line.get(key) or "").strip()
            if val:
                return val
    if ctx.artifact_exists("understanding/speaker_delivery_plan.json"):
        try:
            plan = ctx.read_json("understanding/speaker_delivery_plan.json")
            if isinstance(plan, dict):
                clone = str(plan.get("clone_speaker_id") or "").strip()
                if clone:
                    return clone
        except Exception:
            pass
    try:
        from interview_mux.source_topology import pickup_eligible_speaker_id

        eligible = pickup_eligible_speaker_id(ctx)
        if eligible:
            return str(eligible)
    except Exception:
        pass
    return "host"


def _remap_stage_write_kwargs() -> dict[str, Any]:
    """Fuse/hitch/overlap remap writers must stamp mutation_class on index/sidecars.

    ``transcripts/index.json`` is on SEGMENT_ID_REMAP_PATHS; without
    ``mutation_class=segment_id_remap`` remap stages hit authority_denied before
    the operational allow (pre_ranking soft-fail / desync).
    """
    try:
        from interview_mux.artifact_ownership import SEGMENT_ID_REMAP_STAGES
        from interview_mux.write_staging import active_stage_id

        stage = str(active_stage_id() or "").strip()
    except Exception:
        return {}
    if not stage or stage not in SEGMENT_ID_REMAP_STAGES:
        return {}
    return {"stage_key": stage, "mutation_class": "segment_id_remap"}


def _write_sidecar(ctx: RunContext, doc: dict[str, Any]) -> str:
    kind = str(doc["kind"])
    asset_id = str(doc["asset_id"])
    rel = sidecar_rel(kind, asset_id)
    parent = ctx.path(rel).parent
    parent.mkdir(parents=True, exist_ok=True)
    ctx.write_json(rel, doc, skip_handoff=True, **_remap_stage_write_kwargs())
    return rel


def _unlink_rel(ctx: RunContext, rel: str) -> None:
    for resolver in (ctx.path, ctx.read_path):
        try:
            path = resolver(*rel.split("/")) if resolver is ctx.read_path else ctx.path(rel)
        except Exception:
            continue
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass
    try:
        final = ctx.final_path(*rel.split("/"))
        if final.is_file():
            final.unlink()
    except Exception:
        pass


def write_speech_sidecar(
    ctx: RunContext,
    *,
    segment_id: str,
    start_ms: int,
    end_ms: int,
    speaker_id: str = "",
    source_path: str | None = None,
) -> dict[str, Any]:
    words = slice_words(_full_words(ctx), start_ms, end_ms)
    sid = str(speaker_id or (words[0].get("speaker_id") if words else "") or "")
    doc = {
        "schema_version": SCHEMA_VERSION,
        "kind": "speech",
        "asset_id": str(segment_id),
        "speaker_id": sid,
        "speaker_name": speaker_name_for(ctx, sid),
        "timebase": "source",
        "start_ms": int(start_ms),
        "end_ms": int(end_ms),
        "text": _join_text(words),
        "source_path": source_path,
        "words": words,
    }
    _write_sidecar(ctx, doc)
    return doc


def write_script_sidecar(
    ctx: RunContext,
    *,
    kind: str,
    asset_id: str,
    text: str,
    duration_ms: int,
    speaker_id: str = "",
    source_path: str | None = None,
) -> dict[str, Any]:
    sid = str(speaker_id or vo_speaker_id(ctx))
    dur = max(0, int(duration_ms))
    body = str(text or "").strip()
    words = [
        {
            "text": body,
            "start_ms": 0,
            "end_ms": dur,
            "speaker_id": sid,
        }
    ] if body else []
    doc = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "asset_id": str(asset_id),
        "speaker_id": sid,
        "speaker_name": speaker_name_for(ctx, sid),
        "timebase": "asset",
        "start_ms": 0,
        "end_ms": dur,
        "text": body,
        "source_path": source_path,
        "words": words,
    }
    _write_sidecar(ctx, doc)
    return doc


def write_vo_sidecar(
    ctx: RunContext,
    *,
    line_id: str,
    text: str,
    duration_ms: int,
    speaker_id: str = "",
    source_path: str | None = None,
) -> dict[str, Any]:
    return write_script_sidecar(
        ctx,
        kind="vo_pickup",
        asset_id=line_id,
        text=text,
        duration_ms=duration_ms,
        speaker_id=speaker_id,
        source_path=source_path,
    )


def write_transition_sidecar(
    ctx: RunContext,
    *,
    clip_id: str,
    text: str,
    duration_ms: int,
    speaker_id: str = "",
    source_path: str | None = None,
) -> dict[str, Any]:
    return write_script_sidecar(
        ctx,
        kind="transition",
        asset_id=clip_id,
        text=text,
        duration_ms=duration_ms,
        speaker_id=speaker_id,
        source_path=source_path,
    )


def delete_sidecar(ctx: RunContext, kind: str, asset_id: str) -> None:
    _unlink_rel(ctx, sidecar_rel(kind, asset_id))


def _iter_sidecar_paths(ctx: RunContext) -> list[tuple[str, str, Path]]:
    found: list[tuple[str, str, Path]] = []
    for kind, folder in KIND_FOLDERS.items():
        seen: set[str] = set()
        for root in (ctx.path("transcripts", folder), ctx.read_path("transcripts", folder)):
            try:
                if not root.is_dir():
                    continue
            except Exception:
                continue
            for path in sorted(root.glob("*.json")):
                if path.name in seen:
                    continue
                seen.add(path.name)
                found.append((kind, path.stem, path))
    return found


def rewrite_index(ctx: RunContext) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for kind, asset_id, path in _iter_sidecar_paths(ctx):
        try:
            from interview_mux.file_store import read_json as fs_read_json

            doc = fs_read_json(path)
        except Exception:
            doc = {}
        if not isinstance(doc, dict):
            doc = {}
        entries.append(
            {
                "kind": kind,
                "asset_id": asset_id,
                "path": sidecar_rel(kind, asset_id),
                "start_ms": _ms(doc.get("start_ms")),
                "end_ms": _ms(doc.get("end_ms")),
            }
        )
    index = {"schema_version": SCHEMA_VERSION, "entries": entries}
    ctx.path("transcripts").mkdir(parents=True, exist_ok=True)
    ctx.write_json(INDEX_REL, index, skip_handoff=True, **_remap_stage_write_kwargs())
    return index


def load_sidecar(ctx: RunContext, kind: str, asset_id: str) -> dict[str, Any] | None:
    rel = sidecar_rel(kind, asset_id)
    if not ctx.artifact_exists(rel):
        return None
    try:
        doc = ctx.read_json(rel)
    except Exception:
        return None
    return doc if isinstance(doc, dict) else None


def _manifest_segments(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return []
    doc = ctx.read_json("segments/manifest.json")
    rows = doc.get("segments") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict) and r.get("segment_id")]


def _nle_live_windows(ctx: RunContext) -> dict[str, dict[str, Any]]:
    """Child windows from NLE splits; excluded parents are omitted."""
    if not ctx.artifact_exists("segments/nle_edits.json"):
        return {}
    try:
        nle = ctx.read_json("segments/nle_edits.json")
    except Exception:
        return {}
    if not isinstance(nle, dict):
        return {}
    overrides = nle.get("segment_overrides") or {}
    if not isinstance(overrides, dict):
        return {}
    live: dict[str, dict[str, Any]] = {}
    for sid, row in overrides.items():
        if not isinstance(row, dict):
            continue
        if row.get("excluded"):
            continue
        if "start_ms" in row and "end_ms" in row:
            live[str(sid)] = {
                "segment_id": str(sid),
                "start_ms": _ms(row.get("start_ms")),
                "end_ms": _ms(row.get("end_ms")),
                "speaker_id": str(row.get("speaker_id") or ""),
                "parent_id": str(row.get("parent_id") or ""),
            }
    return live


def sync_speech_sidecars(ctx: RunContext) -> dict[str, Any]:
    """Rewrite speech sidecars for every live segment; prune absorbed / split parents."""
    segments = _manifest_segments(ctx)
    live: dict[str, dict[str, Any]] = {}
    for row in segments:
        sid = str(row.get("segment_id"))
        live[sid] = row
    nle_live = _nle_live_windows(ctx)
    excluded_parents: set[str] = set()
    if ctx.artifact_exists("segments/nle_edits.json"):
        try:
            nle = ctx.read_json("segments/nle_edits.json")
            overrides = (nle or {}).get("segment_overrides") or {}
            if isinstance(overrides, dict):
                for sid, row in overrides.items():
                    if isinstance(row, dict) and row.get("excluded"):
                        excluded_parents.add(str(sid))
                        live.pop(str(sid), None)
        except Exception:
            pass
    for sid, row in nle_live.items():
        live[sid] = {**live.get(sid, {}), **row}

    written = 0
    for sid, row in live.items():
        start_ms = _ms(row.get("start_ms"))
        end_ms = _ms(row.get("end_ms"))
        if end_ms <= start_ms:
            continue
        write_speech_sidecar(
            ctx,
            segment_id=sid,
            start_ms=start_ms,
            end_ms=end_ms,
            speaker_id=str(row.get("speaker_id") or row.get("speaker") or ""),
        )
        written += 1

    pruned = 0
    keep = set(live)
    for kind, asset_id, _path in _iter_sidecar_paths(ctx):
        if kind != "speech":
            continue
        if asset_id not in keep:
            delete_sidecar(ctx, "speech", asset_id)
            pruned += 1
    rewrite_index(ctx)
    return {"written": written, "pruned": pruned, "live": sorted(keep)}


def write_vo_sidecar_for_line(
    ctx: RunContext,
    line: dict[str, Any],
    *,
    wav_path: Path | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any] | None:
    line_id = str(line.get("line_id") or "").strip()
    if not line_id:
        return None
    dur = duration_ms if duration_ms is not None else wav_duration_ms(wav_path)
    source = None
    if wav_path is not None:
        try:
            source = wav_path.relative_to(ctx.run_dir).as_posix()
        except Exception:
            source = str(wav_path)
    doc = write_vo_sidecar(
        ctx,
        line_id=line_id,
        text=str(line.get("text") or ""),
        duration_ms=dur,
        speaker_id=vo_speaker_id(ctx, line),
        source_path=source,
    )
    rewrite_index(ctx)
    return doc


def write_vo_sidecar_from_pickup(ctx: RunContext, line_id: str, wav_path: Path | None = None) -> None:
    line: dict[str, Any] = {"line_id": line_id}
    if ctx.artifact_exists("understanding/gap_report.json"):
        report = ctx.read_json("understanding/gap_report.json")
        for row in (report or {}).get("interviewer_lines") or []:
            if isinstance(row, dict) and str(row.get("line_id") or "") == str(line_id):
                line = dict(row)
                break
    path = wav_path
    if path is None:
        try:
            from interview_mux.stages.assembly import resolve_vo_pickup_path

            path = resolve_vo_pickup_path(ctx, line)
        except Exception:
            path = ctx.read_path("vo_pickup", f"{line_id}.wav")
            if not path.is_file():
                path = None
    write_vo_sidecar_for_line(ctx, line, wav_path=path)


def sync_vo_sidecars_from_gap_report(ctx: RunContext) -> int:
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return 0
    report = ctx.read_json("understanding/gap_report.json")
    n = 0
    for row in (report or {}).get("interviewer_lines") or []:
        if not isinstance(row, dict):
            continue
        line_id = str(row.get("line_id") or "").strip()
        if not line_id:
            continue
        delivery = str(row.get("delivery") or "").lower()
        if delivery not in {"record", "synthesize"}:
            continue
        if row.get("skipped_optional"):
            continue
        write_vo_sidecar_from_pickup(ctx, line_id)
        n += 1
    return n


def _transition_clip_id(after_id: str, before_id: str) -> str:
    return f"tr_{after_id}_{before_id}"


def write_transition_sidecar_for_item(
    ctx: RunContext,
    item: dict[str, Any],
    *,
    wav_path: Path | None = None,
) -> dict[str, Any] | None:
    after_id = str(item.get("after_segment_id") or "")
    before_id = str(item.get("before_segment_id") or "")
    if not after_id or not before_id:
        return None
    clip_id = _transition_clip_id(after_id, before_id)
    path = wav_path
    if path is None:
        try:
            from interview_mux.transition_vo import transition_wav_path

            candidate = transition_wav_path(ctx, after_id, before_id)
            if candidate.is_file():
                path = candidate
        except Exception:
            path = None
    source = None
    if path is not None:
        try:
            source = path.relative_to(ctx.run_dir).as_posix()
        except Exception:
            source = str(path)
    doc = write_transition_sidecar(
        ctx,
        clip_id=clip_id,
        text=str(item.get("text") or ""),
        duration_ms=wav_duration_ms(path),
        speaker_id=vo_speaker_id(ctx),
        source_path=source,
    )
    rewrite_index(ctx)
    return doc


def group_words_into_cues(
    words: list[dict[str, Any]],
    *,
    speaker_id: str,
    speaker_name: str,
    kind: str,
    asset_id: str,
    max_ms: int = CUE_MAX_MS,
) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    buf: list[dict[str, Any]] = []

    def flush() -> None:
        if not buf:
            return
        start = _ms(buf[0].get("start_ms"))
        end = _ms(buf[-1].get("end_ms"), start)
        cues.append(
            {
                "start_ms": start,
                "end_ms": max(end, start),
                "speaker_id": speaker_id,
                "speaker_name": speaker_name,
                "text": _join_text(buf),
                "kind": kind,
                "asset_id": asset_id,
            }
        )
        buf.clear()

    for word in words:
        text = str(word.get("text") or "").strip()
        if not text:
            continue
        if not buf:
            buf.append(word)
            continue
        span = _ms(word.get("end_ms")) - _ms(buf[0].get("start_ms"))
        prev = str(buf[-1].get("text") or "").strip()
        if span > max_ms or _SENTENCE_END.search(prev):
            flush()
        buf.append(word)
    flush()
    return [c for c in cues if str(c.get("text") or "").strip()]


def vtt_timestamp(ms: int) -> str:
    ms = max(0, int(ms))
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def cues_to_vtt(cues: list[dict[str, Any]]) -> str:
    lines = ["WEBVTT", ""]
    last_speaker = ""
    for cue in cues:
        start = vtt_timestamp(_ms(cue.get("start_ms")))
        end = vtt_timestamp(max(_ms(cue.get("end_ms")), _ms(cue.get("start_ms")) + 1))
        speaker = str(cue.get("speaker_name") or cue.get("speaker_id") or "Speaker").strip()
        text = str(cue.get("text") or "").strip()
        if not text:
            continue
        body = text if speaker == last_speaker else f"<v {speaker}>{text}"
        last_speaker = speaker
        lines.append(f"{start} --> {end}")
        lines.append(body)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def vtt_has_cue_bodies(text: str) -> bool:
    """True when a WEBVTT document has at least one cue timing line."""
    return any("-->" in line for line in str(text or "").splitlines())


def master_transcript_ship_incompleteness(ctx: RunContext) -> str | None:
    """HPUB-3: cue_count 0 / header-only VTT are not ship-complete.

    JSON schema still allows cue_count 0 (hollow pack evidence). Stage contract
    sufficiency documents cues min_rows≥1 (clinic B1).
    """
    if not ctx.artifact_exists(MASTER_JSON_REL):
        return (
            "cue_count_zero — resume master_transcript_build: "
            "master/transcript.json missing"
        )
    try:
        doc = ctx.read_json(MASTER_JSON_REL)
    except Exception:
        return (
            "cue_count_zero — resume master_transcript_build: "
            "master/transcript.json unreadable"
        )
    if not isinstance(doc, dict):
        return (
            "cue_count_zero — resume master_transcript_build: "
            "master/transcript.json unreadable"
        )
    cues = doc.get("cues") if isinstance(doc.get("cues"), list) else []
    try:
        n = int(doc.get("cue_count") if doc.get("cue_count") is not None else len(cues))
    except (TypeError, ValueError):
        n = len(cues)
    nonempty = [
        row
        for row in cues
        if isinstance(row, dict) and str(row.get("text") or "").strip()
    ]
    if n < 1 or not nonempty:
        return (
            "cue_count_zero — resume master_transcript_build: no spoken cues"
        )
    vtt_text = ""
    if ctx.artifact_exists(MASTER_VTT_REL):
        try:
            vtt_text = ctx.read_path(MASTER_VTT_REL).read_text(encoding="utf-8")
        except Exception:
            vtt_text = ""
    if not vtt_has_cue_bodies(vtt_text):
        return (
            "header_only_vtt — resume master_transcript_build: "
            "master/transcript.vtt has no cue bodies"
        )
    return None


def require_packagable_master_transcript(ctx: RunContext) -> None:
    """HPUB-3 2A: refuse package when captions are empty or header-only."""
    reason = master_transcript_ship_incompleteness(ctx)
    if reason:
        raise RuntimeError(reason)


def cues_to_txt(cues: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for cue in cues:
        speaker = str(cue.get("speaker_name") or cue.get("speaker_id") or "Speaker").strip()
        text = str(cue.get("text") or "").strip()
        if not text:
            continue
        blocks.append(f"{speaker}: {text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _clip_covers_speech(sidecar: dict[str, Any], clip: dict[str, Any]) -> bool:
    src_s = _ms(clip.get("source_start_ms"))
    src_e = _ms(clip.get("source_end_ms"), src_s)
    return _ms(sidecar.get("start_ms")) <= src_s + 5 and _ms(sidecar.get("end_ms")) >= src_e - 5


def _remap_speech_words(
    sidecar: dict[str, Any],
    clip: dict[str, Any],
) -> list[dict[str, Any]]:
    timeline = _ms(clip.get("timeline_start_ms"))
    src_s = _ms(clip.get("source_start_ms"))
    src_e = _ms(clip.get("source_end_ms"), src_s)
    dur = _ms(clip.get("duration_ms"), max(0, src_e - src_s))
    out: list[dict[str, Any]] = []
    for word in sidecar.get("words") or []:
        if not isinstance(word, dict):
            continue
        ws = _ms(word.get("start_ms"))
        we = _ms(word.get("end_ms"), ws)
        if we <= src_s or ws >= src_e:
            continue
        ws = max(ws, src_s)
        we = min(we, src_e)
        master_s = timeline + (ws - src_s)
        master_e = timeline + (we - src_s)
        master_e = min(master_e, timeline + dur)
        out.append(
            {
                **word,
                "start_ms": master_s,
                "end_ms": max(master_e, master_s),
            }
        )
    return out


def _remap_asset_words(sidecar: dict[str, Any], clip: dict[str, Any]) -> list[dict[str, Any]]:
    timeline = _ms(clip.get("timeline_start_ms"))
    dur = _ms(clip.get("duration_ms"), _ms(sidecar.get("end_ms")))
    out: list[dict[str, Any]] = []
    for word in sidecar.get("words") or []:
        if not isinstance(word, dict):
            continue
        ws = _ms(word.get("start_ms"))
        we = _ms(word.get("end_ms"), ws)
        master_s = timeline + ws
        master_e = timeline + we
        master_e = min(master_e, timeline + dur)
        out.append({**word, "start_ms": master_s, "end_ms": max(master_e, master_s)})
    if not out:
        text = str(sidecar.get("text") or "").strip()
        if text:
            out.append(
                {
                    "text": text,
                    "start_ms": timeline,
                    "end_ms": timeline + dur,
                    "speaker_id": str(sidecar.get("speaker_id") or ""),
                }
            )
    return out


def _gap_line(ctx: RunContext, line_id: str) -> dict[str, Any]:
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return {"line_id": line_id}
    report = ctx.read_json("understanding/gap_report.json")
    for row in (report or {}).get("interviewer_lines") or []:
        if isinstance(row, dict) and str(row.get("line_id") or "") == str(line_id):
            return dict(row)
    return {"line_id": line_id}


def _repair_speech_sidecar(ctx: RunContext, clip: dict[str, Any]) -> dict[str, Any]:
    sid = str(clip.get("segment_id") or "")
    start_ms = _ms(clip.get("source_start_ms"))
    end_ms = _ms(clip.get("source_end_ms"), start_ms)
    speaker_id = ""
    for row in _manifest_segments(ctx):
        if str(row.get("segment_id")) == sid:
            start_ms = _ms(row.get("start_ms"), start_ms)
            end_ms = _ms(row.get("end_ms"), end_ms)
            speaker_id = str(row.get("speaker_id") or "")
            break
    return write_speech_sidecar(
        ctx,
        segment_id=sid or "speech",
        start_ms=start_ms,
        end_ms=end_ms,
        speaker_id=speaker_id,
    )


def _repair_vo_sidecar(ctx: RunContext, clip: dict[str, Any]) -> dict[str, Any]:
    line_id = str(clip.get("line_id") or "")
    line = _gap_line(ctx, line_id)
    dur = _ms(clip.get("duration_ms"))
    path = None
    source = clip.get("source_path")
    if source:
        try:
            candidate = ctx.read_path(str(source))
            if candidate.is_file():
                path = candidate
                dur = dur or wav_duration_ms(path)
        except Exception:
            path = None
    return write_vo_sidecar(
        ctx,
        line_id=line_id or "vo",
        text=str(line.get("text") or clip.get("text") or ""),
        duration_ms=dur,
        speaker_id=vo_speaker_id(ctx, line),
        source_path=str(source) if source else None,
    )


def _repair_transition_sidecar(ctx: RunContext, clip: dict[str, Any]) -> dict[str, Any]:
    after_id = str(clip.get("after_segment_id") or "")
    before_id = str(clip.get("before_segment_id") or "")
    clip_id = _transition_clip_id(after_id, before_id) if after_id and before_id else "transition"
    text = str(clip.get("text") or "")
    if not text and ctx.artifact_exists("master/transitions.json"):
        doc = ctx.read_json("master/transitions.json")
        for row in (doc or {}).get("transitions") or []:
            if (
                isinstance(row, dict)
                and str(row.get("after_segment_id") or "") == after_id
                and str(row.get("before_segment_id") or "") == before_id
            ):
                text = str(row.get("text") or "")
                break
    return write_transition_sidecar(
        ctx,
        clip_id=clip_id,
        text=text,
        duration_ms=_ms(clip.get("duration_ms")),
        speaker_id=vo_speaker_id(ctx),
        source_path=str(clip.get("source_path") or "") or None,
    )


def _sidecar_for_clip(ctx: RunContext, clip: dict[str, Any]) -> dict[str, Any]:
    kind = str(clip.get("type") or "")
    if kind == "speech":
        sid = str(clip.get("segment_id") or "")
        sidecar = load_sidecar(ctx, "speech", sid)
        if sidecar and _clip_covers_speech(sidecar, clip):
            return sidecar
        return _repair_speech_sidecar(ctx, clip)
    if kind == "vo_pickup":
        line_id = str(clip.get("line_id") or "")
        sidecar = load_sidecar(ctx, "vo_pickup", line_id)
        if sidecar and _ms(sidecar.get("end_ms")) >= max(0, _ms(clip.get("duration_ms")) - 50):
            return sidecar
        return _repair_vo_sidecar(ctx, clip)
    after_id = str(clip.get("after_segment_id") or "")
    before_id = str(clip.get("before_segment_id") or "")
    clip_id = _transition_clip_id(after_id, before_id)
    sidecar = load_sidecar(ctx, "transition", clip_id)
    if sidecar and str(sidecar.get("text") or "").strip():
        return sidecar
    return _repair_transition_sidecar(ctx, clip)


def assemble_master_cues(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("master/edl.json"):
        return []
    edl = ctx.read_json("master/edl.json")
    clips = edl.get("clips") if isinstance(edl, dict) else None
    if not isinstance(clips, list):
        return []
    cues: list[dict[str, Any]] = []
    for clip in clips:
        if not isinstance(clip, dict):
            continue
        kind = str(clip.get("type") or "")
        if kind not in SPOKEN_EDL_TYPES:
            continue
        sidecar = _sidecar_for_clip(ctx, clip)
        speaker_id = str(sidecar.get("speaker_id") or "")
        speaker_name = str(sidecar.get("speaker_name") or speaker_name_for(ctx, speaker_id))
        asset_id = str(sidecar.get("asset_id") or "")
        if kind == "speech":
            words = _remap_speech_words(sidecar, clip)
            cues.extend(
                group_words_into_cues(
                    words,
                    speaker_id=speaker_id,
                    speaker_name=speaker_name,
                    kind=kind,
                    asset_id=asset_id,
                )
            )
        else:
            words = _remap_asset_words(sidecar, clip)
            cues.extend(
                group_words_into_cues(
                    words,
                    speaker_id=speaker_id,
                    speaker_name=speaker_name,
                    kind=kind,
                    asset_id=asset_id,
                    max_ms=10**9,
                )
            )
    cues.sort(key=lambda c: (_ms(c.get("start_ms")), _ms(c.get("end_ms"))))
    return cues


def write_master_transcript_files(ctx: RunContext, cues: list[dict[str, Any]]) -> dict[str, Any]:
    doc = {
        "schema_version": SCHEMA_VERSION,
        "timebase": "master",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_edl": "master/edl.json",
        "cue_count": len(cues),
        "cues": cues,
    }
    ctx.write_json(MASTER_JSON_REL, doc)
    vtt = cues_to_vtt(cues)
    txt = cues_to_txt(cues)
    ctx.path(MASTER_VTT_REL).parent.mkdir(parents=True, exist_ok=True)
    ctx.path(MASTER_VTT_REL).write_text(vtt, encoding="utf-8")
    ctx.path(MASTER_TXT_REL).write_text(txt, encoding="utf-8")
    try:
        ctx.final_path("master").mkdir(parents=True, exist_ok=True)
        ctx.final_path(*MASTER_VTT_REL.split("/")).write_text(vtt, encoding="utf-8")
        ctx.final_path(*MASTER_TXT_REL.split("/")).write_text(txt, encoding="utf-8")
    except Exception:
        pass
    return doc


def run_master_transcript_build(ctx: RunContext) -> dict[str, Any]:
    """Assemble Apple-ready master transcript after master.wav exists."""
    stage = "master_transcript_build"
    if not ctx.artifact_exists("master/master.wav"):
        raise FileNotFoundError("master/master.wav missing — run master_finalize first")
    if not ctx.artifact_exists("master/edl.json"):
        raise FileNotFoundError("master/edl.json missing — cannot assemble master transcript")
    cues = assemble_master_cues(ctx)
    rewrite_index(ctx)
    doc = write_master_transcript_files(ctx, cues)
    hollow = master_transcript_ship_incompleteness(ctx)
    if hollow:
        ctx.log(
            f"Master transcript incomplete — {hollow}",
            level="warning",
            stage=stage,
            detail={"cue_count": len(cues)},
        )
        raise RuntimeError(hollow)
    ctx.mark_done(stage)
    ctx.log(
        f"Master transcript: {len(cues)} cue(s) → {MASTER_VTT_REL}",
        level="success",
        stage=stage,
        detail={"cue_count": len(cues)},
    )
    return doc


__all__ = [
    "INDEX_REL",
    "MASTER_JSON_REL",
    "MASTER_TXT_REL",
    "MASTER_VTT_REL",
    "assemble_master_cues",
    "cues_to_txt",
    "cues_to_vtt",
    "delete_sidecar",
    "group_words_into_cues",
    "load_sidecar",
    "run_master_transcript_build",
    "sidecar_rel",
    "slice_words",
    "sync_speech_sidecars",
    "sync_vo_sidecars_from_gap_report",
    "vtt_timestamp",
    "write_speech_sidecar",
    "write_transition_sidecar_for_item",
    "write_vo_sidecar",
    "write_vo_sidecar_for_line",
    "write_vo_sidecar_from_pickup",
    "write_master_transcript_files",
    "vtt_has_cue_bodies",
    "master_transcript_ship_incompleteness",
    "require_packagable_master_transcript",
]
