"""Same-person listen before clone-adjacency suppress.

Diarization ID remains the candidate filter. When a cloned voice would sit next
to tape labeled as that same speaker, Sortformer pair-verify asks whether the
clip actually sounds like the clone reference. YES (or unavailable) keeps the
suppress; NO means a mislabel and the VO stays.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Literal

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

VerifyFn = Callable[[Path, Path], str | None]
Edge = Literal["start", "end"]

DEFAULT_CLIP_MS = 4000
VERIFY_REL = "master/clone_adjacency_verify.json"


def clone_adjacency_verify_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    root = dict(cfg) if cfg is not None else merged_config()
    mastering = dict(root.get("mastering") or {})
    edl = dict(mastering.get("edl") or {})
    enabled = edl.get("clone_adjacency_verify")
    clip_ms = edl.get("clone_adjacency_verify_clip_ms")
    return {
        "enabled": enabled is not False,
        "clip_ms": int(clip_ms or DEFAULT_CLIP_MS),
    }


def id_matches_clone(speaker_id: str | None, clone_voice_id: str | None) -> bool:
    voice = str(clone_voice_id or "").strip()
    speaker = str(speaker_id or "").strip()
    return bool(voice and speaker and voice == speaker)


def should_suppress_clone_adjacency(
    *,
    id_hit_segment_ids: list[str],
    verdicts: dict[str, str | None] | None,
    verify_enabled: bool,
) -> tuple[bool, str]:
    """Return (suppress, reason).

    Keep only when every ID-matching neighbor listen is NO.
    """
    hits = [sid for sid in id_hit_segment_ids if str(sid or "").strip()]
    if not hits:
        return False, "no_id_match"
    if not verify_enabled:
        return True, "id_match"
    rows = verdicts or {}
    for sid in hits:
        verdict = rows.get(sid)
        if verdict == "NO":
            continue
        if verdict == "YES":
            return True, "same_person"
        return True, "verify_unavailable"
    return False, "id_mismatch_kept"


def tape_window_ms(
    segment: dict[str, Any],
    *,
    edge: Edge,
    clip_ms: int,
) -> tuple[int, int]:
    start = int(segment.get("start_ms") or segment.get("source_start_ms") or 0)
    end = int(segment.get("end_ms") or segment.get("source_end_ms") or 0)
    if end <= start:
        return start, start
    span = min(max(int(clip_ms), 400), end - start)
    if edge == "end":
        return end - span, end
    return start, start + span


def resolve_clone_sample(ctx: RunContext, clone_voice_id: str) -> Path | None:
    rel = f"understanding/speaker_samples/{clone_voice_id}.wav"
    try:
        path = ctx.read_path("understanding", "speaker_samples", f"{clone_voice_id}.wav")
    except Exception:
        path = ctx.run_dir / rel
    return path if path.is_file() else None


def resolve_source_wav(ctx: RunContext) -> Path | None:
    for parts in (("preclean", "isolated.wav"), ("ingest", "normalized.wav")):
        try:
            path = ctx.read_path(*parts)
        except Exception:
            continue
        if path.is_file():
            return path
    return None


class CloneAdjacencySession:
    """Per-EDL cache + seam log for clone-adjacency listens."""

    def __init__(
        self,
        *,
        ctx: RunContext | None = None,
        verify_pair: VerifyFn | None = None,
        enabled: bool | None = None,
        clip_ms: int | None = None,
    ) -> None:
        cfg = clone_adjacency_verify_cfg()
        self.ctx = ctx
        self.verify_pair = verify_pair
        self.enabled = cfg["enabled"] if enabled is None else bool(enabled)
        self.clip_ms = int(clip_ms if clip_ms is not None else cfg["clip_ms"])
        self.cache: dict[tuple[str, str], str | None] = {}
        self.seams: list[dict[str, Any]] = []
        self.unavailable_reason: str | None = None

    def id_hits(self, clone_voice_id: str, *segments: dict[str, Any] | None) -> list[str]:
        hits: list[str] = []
        seen: set[str] = set()
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            sid = str(seg.get("segment_id") or "").strip()
            if not sid or sid in seen:
                continue
            if id_matches_clone(str(seg.get("speaker_id") or ""), clone_voice_id):
                seen.add(sid)
                hits.append(sid)
        return hits

    def verdict_for(
        self,
        clone_voice_id: str,
        segment: dict[str, Any],
        *,
        edge: Edge,
    ) -> str | None:
        sid = str(segment.get("segment_id") or "").strip()
        key = (clone_voice_id, sid)
        if key in self.cache:
            return self.cache[key]
        if not self.enabled:
            self.cache[key] = None
            return None
        verdict = self._listen(clone_voice_id, segment, edge=edge)
        self.cache[key] = verdict
        return verdict

    def decide(
        self,
        *,
        kind: str,
        key: str,
        clone_voice_id: str,
        after: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        target: dict[str, Any] | None = None,
    ) -> bool:
        """Record a seam and return True when the VO/transition should be dropped."""
        neighbors: list[tuple[dict[str, Any], Edge]] = []
        if isinstance(target, dict):
            neighbors.append((target, "start"))
        if isinstance(after, dict):
            neighbors.append((after, "end"))
        if isinstance(before, dict):
            neighbors.append((before, "start"))
        hits = self.id_hits(clone_voice_id, *[seg for seg, _edge in neighbors])
        verdicts: dict[str, str | None] = {}
        if self.enabled:
            for seg, edge in neighbors:
                sid = str(seg.get("segment_id") or "").strip()
                if sid not in hits:
                    continue
                verdicts[sid] = self.verdict_for(clone_voice_id, seg, edge=edge)
        suppress, reason = should_suppress_clone_adjacency(
            id_hit_segment_ids=hits,
            verdicts=verdicts,
            verify_enabled=self.enabled,
        )
        record = {
            "kind": kind,
            "key": key,
            "after": str((after or {}).get("segment_id") or "") or None,
            "before": str((before or {}).get("segment_id") or (target or {}).get("segment_id") or "")
            or None,
            "id_hits": hits,
            "verdicts": verdicts,
            "decision": "suppress" if suppress else "keep",
            "reason": reason,
        }
        self.seams.append(record)
        return suppress

    def report(self) -> dict[str, Any]:
        return {
            "version": 1,
            "enabled": self.enabled,
            "clip_ms": self.clip_ms,
            "unavailable_reason": self.unavailable_reason,
            "seams": list(self.seams),
        }

    def kept_despite_id(self) -> list[str]:
        return [
            str(row.get("key") or "")
            for row in self.seams
            if row.get("decision") == "keep" and row.get("reason") == "id_mismatch_kept"
        ]

    def _listen(self, clone_voice_id: str, segment: dict[str, Any], *, edge: Edge) -> str | None:
        sid = str(segment.get("segment_id") or "").strip() or "segment"
        if self.verify_pair is not None:
            return _normalize_verdict(
                self.verify_pair(Path(clone_voice_id), Path(sid))
            )
        if self.unavailable_reason:
            return None
        ctx = self.ctx
        if ctx is None:
            self.unavailable_reason = "no_run_context"
            return None
        sample = resolve_clone_sample(ctx, clone_voice_id)
        source = resolve_source_wav(ctx)
        if sample is None:
            self.unavailable_reason = f"missing_clone_sample:{clone_voice_id}"
            return None
        if source is None:
            self.unavailable_reason = "missing_source_wav"
            return None
        start_ms, end_ms = tape_window_ms(segment, edge=edge, clip_ms=self.clip_ms)
        if end_ms - start_ms < 400:
            self.unavailable_reason = f"clip_too_short:{sid}"
            return None
        clip_b = ctx.run_dir / "master" / "clone_adjacency_clips" / f"{sid}.wav"
        try:
            from interview_mux.audio_clips import extract_clip
            from interview_mux.diarization_suspicion import _verify_pair_mlx
            from interview_mux.local_runtime import LocalRuntimeUnavailable

            extract_clip(source, clip_b, start_ms, end_ms)
            verdict = _verify_pair_mlx(sample, clip_b, ctx=ctx, stage="edl")
        except LocalRuntimeUnavailable as exc:
            self.unavailable_reason = str(exc)[:300]
            return None
        except Exception as exc:  # noqa: BLE001 — conservative suppress
            self.unavailable_reason = str(exc)[:300]
            return None
        return _normalize_verdict(verdict)


def persist_clone_adjacency_verify(ctx: RunContext, report: dict[str, Any]) -> None:
    ctx.write_json(VERIFY_REL, report)


def _normalize_verdict(raw: str | None) -> str | None:
    text = str(raw or "").strip().upper()
    if text in {"YES", "NO"}:
        return text
    return None
