"""EDL file contract: never persist a source_path whose file is not on disk.

Ghost paths (paperwork naming a WAV that was never written) used to survive
junction remaster, segment-id remap, listenability, omit-ledger, and mix
rewrites because only ``run_edl`` linted. Every JSON persist of
``master/edl.json`` must run through ``sanitize_edl_source_paths``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext

EDL_REL = "master/edl.json"
_VO_EMPTY_SEAT_TYPES = frozenset({"vo_pickup", "transition"})
_MIN_AUDIO_BYTES = 1000


def is_edl_rel(rel: str | None) -> bool:
    if not rel:
        return False
    return str(rel).replace("\\", "/").strip("/") == EDL_REL


def _norm_rel(rel: str) -> str:
    return str(rel).replace("\\", "/").lstrip("./")


def run_dir_for_edl_path(path: Path) -> Path | None:
    """Return the execution root for a committed or staged ``master/edl.json`` path."""
    resolved = Path(path)
    if resolved.name != "edl.json" or resolved.parent.name != "master":
        return None
    parts = resolved.parts
    try:
        idx = parts.index(".pending_writes")
    except ValueError:
        return resolved.parent.parent
    if idx <= 0:
        return None
    return Path(*parts[:idx])


def clip_audio_exists_in_run(run_dir: Path, rel: str | None) -> bool:
    if rel is None:
        return False
    raw = str(rel).strip()
    if not raw or raw.lower() in {"null", "none"}:
        return False
    candidates: list[Path] = []
    absolute = Path(raw)
    if absolute.is_absolute():
        candidates.append(absolute)
    norm = _norm_rel(raw)
    candidates.append(run_dir.joinpath(*norm.split("/")))
    pending = run_dir / ".pending_writes"
    if pending.is_dir():
        try:
            for stage_dir in pending.iterdir():
                if stage_dir.is_dir():
                    candidates.append(stage_dir.joinpath(*norm.split("/")))
        except OSError:
            pass
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        try:
            if candidate.is_file() and candidate.stat().st_size > _MIN_AUDIO_BYTES:
                return True
        except OSError:
            continue
    return False


def clip_audio_exists(ctx: RunContext, rel: str | None) -> bool:
    """True when ``rel`` resolves to a committed or staged audio file with bytes."""
    if rel is None:
        return False
    raw = str(rel).strip()
    if not raw or raw.lower() in {"null", "none"}:
        return False
    try:
        if clip_audio_exists_in_run(ctx.run_dir, raw):
            return True
    except Exception:
        pass
    norm = _norm_rel(raw)
    for resolver in (
        lambda: ctx.read_path(norm),
        lambda: ctx.path(*norm.split("/")),
        lambda: ctx.final_path(*norm.split("/")),
    ):
        try:
            path = resolver()
            if path.is_file() and path.stat().st_size > _MIN_AUDIO_BYTES:
                return True
        except Exception:
            continue
    return False


def edl_source_path_ghosts(ctx: RunContext, edl: dict[str, Any] | None) -> list[str]:
    """``source_path`` values on clips whose files are missing (empty/null omitted)."""
    ghosts: list[str] = []
    if not isinstance(edl, dict):
        return ghosts
    for clip in edl.get("clips") or []:
        if not isinstance(clip, dict):
            continue
        src = clip.get("source_path")
        if src is None:
            continue
        text = str(src).strip()
        if not text or text.lower() in {"null", "none"}:
            ghosts.append(f"{clip.get('type') or '?'}:empty")
            continue
        if not clip_audio_exists(ctx, text):
            ghosts.append(text)
    return ghosts


def _strip_missing_source_paths(
    edl: dict[str, Any] | None,
    *,
    exists,
) -> tuple[dict[str, Any], list[str]]:
    out = dict(edl) if isinstance(edl, dict) else {"clips": []}
    clips: list[Any] = []
    cleared: list[str] = []
    for clip in out.get("clips") or []:
        if not isinstance(clip, dict):
            clips.append(clip)
            continue
        src = clip.get("source_path")
        if "source_path" not in clip:
            clips.append(clip)
            continue
        text = "" if src is None else str(src).strip()
        if text and text.lower() not in {"null", "none"} and exists(text):
            clips.append(clip)
            continue
        row = dict(clip)
        row.pop("source_path", None)
        ctype = str(clip.get("type") or "")
        if ctype in _VO_EMPTY_SEAT_TYPES:
            row["duration_ms"] = 0
        label = str(clip.get("line_id") or "") or (
            f"{clip.get('after_segment_id')}->{clip.get('before_segment_id')}"
        )
        if not label or label == "->":
            label = str(clip.get("segment_id") or ctype or "clip")
        cleared.append(f"{label}:{text or '(empty)'}")
        clips.append(row)
    out["clips"] = clips
    return out, cleared


def sanitize_edl_against_run_dir(
    run_dir: Path,
    edl: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    """Sanitize using files under ``run_dir`` (no RunContext required)."""
    return _strip_missing_source_paths(
        edl,
        exists=lambda rel: clip_audio_exists_in_run(run_dir, rel),
    )


def sanitize_edl_json_for_path(path: Path, data: Any) -> Any:
    """Drop ghost ``source_path``s when ``path`` is a ``master/edl.json`` write."""
    run_dir = run_dir_for_edl_path(path)
    if run_dir is None or not isinstance(data, dict):
        return data
    cleaned, _cleared = sanitize_edl_against_run_dir(run_dir, data)
    return cleaned


def sanitize_edl_source_paths(
    ctx: RunContext,
    edl: dict[str, Any] | None,
    *,
    log: bool = True,
) -> tuple[dict[str, Any], list[str]]:
    """Unset every clip ``source_path`` that does not resolve to a real file.

    ``vo_pickup`` / ``transition`` also zero ``duration_ms`` so the seat is an
    explicit empty (mix last-chance or silence) rather than a claimed file.
    Other clip types only drop the ghost path.
    """
    out, cleared = _strip_missing_source_paths(
        edl,
        exists=lambda rel: clip_audio_exists(ctx, rel),
    )
    if cleared and log:
        stage = "edl"
        try:
            from interview_mux.write_staging import active_stage

            stage = active_stage() or stage
        except Exception:
            pass
        ctx.log(
            f"edl: cleared dangling source_path ({len(cleared)})",
            level="warning",
            stage=stage,
            detail={"cleared": cleared[:8]},
        )
    return out, cleared


def lint_edl_vo_source_paths(ctx: RunContext, edl: dict[str, Any] | None) -> dict[str, Any]:
    """Sanitize and return the EDL (write-path helper; logs when ghosts are dropped)."""
    cleaned, _cleared = sanitize_edl_source_paths(ctx, edl, log=True)
    return cleaned


def prepare_edl_payload_for_disk(ctx: RunContext, rel: str, data: Any) -> Any:
    """Identity unless ``rel`` is ``master/edl.json``."""
    if not is_edl_rel(rel) or not isinstance(data, dict):
        return data
    cleaned, _cleared = sanitize_edl_source_paths(ctx, data, log=True)
    return cleaned


def persist_sanitized_edl(ctx: RunContext, edl: dict[str, Any] | None = None) -> list[str]:
    """Rewrite committed/staged EDL when ghosts are present. Returns cleared labels."""
    doc = edl
    if doc is None:
        if not ctx.artifact_exists(EDL_REL):
            return []
        try:
            loaded = ctx.read_json(EDL_REL)
        except Exception:
            return []
        if not isinstance(loaded, dict):
            return []
        doc = loaded
    cleaned, cleared = sanitize_edl_source_paths(ctx, doc, log=True)
    if not cleared:
        return []
    try:
        from interview_mux.air_order import write_live_edl

        write_live_edl(ctx, cleaned, source="edl_source_contract")
    except Exception:
        from interview_mux.write_staging import write_mirrored_json

        write_mirrored_json(ctx, EDL_REL, cleaned)
    return cleared


def heal_committed_edl_source_paths(ctx: RunContext) -> list[str]:
    """Safety net after flush/promote/archive restore."""
    return persist_sanitized_edl(ctx)


def heal_edl_file_if_present(run_dir: Path) -> list[str]:
    """Rewrite ``run_dir/master/edl.json`` when it still names missing files."""
    path = Path(run_dir) / "master" / "edl.json"
    if not path.is_file():
        return []
    try:
        import json

        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(doc, dict):
        return []
    cleaned, cleared = sanitize_edl_against_run_dir(Path(run_dir), doc)
    if not cleared:
        return []
    from interview_mux.file_store import write_json as fs_write_json

    fs_write_json(path, cleaned)
    return cleared
