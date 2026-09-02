"""Homunculus brain registry. 0.0.0 is the original linear pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from interview_mux.config import merged_config, repo_root

# Config alias: pick the highest registered brain (currently 0.1.0).
DEFAULT_VERSION = "latest"
_LATEST_ALIASES = frozenset({"", "latest", "highest", "default"})


@dataclass(frozen=True)
class HomunculusBrain:
    id: str
    label: str
    summary: str
    kind: str  # original_pipeline | homunculus
    prompt_tree: str | None = None


_BUILTIN: tuple[HomunculusBrain, ...] = (
    HomunculusBrain(
        id="0.0.0",
        label="Original",
        summary=(
            "Progress through the steps iteratively as they were created and "
            "originally intended. Linear analysis and delivery, existing gates, "
            "per-stage LLMs."
        ),
        kind="original_pipeline",
    ),
    HomunculusBrain(
        id="0.1.0",
        label="Homunculus",
        summary=(
            "Authoritative conductor: skip/reorder/rerun, dynamic packing, "
            "KB, MusicGen ladder, source-relative ears."
        ),
        kind="homunculus",
        prompt_tree="docs/prompts/homunculus/",
    ),
)


def _yaml_brains() -> tuple[HomunculusBrain, ...]:
    path = repo_root() / "docs" / "homunculus" / "versions.yaml"
    if not path.is_file():
        return ()
    try:
        import yaml  # type: ignore
    except Exception:
        return ()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = raw.get("brains") or raw.get("versions") or []
    out: list[HomunculusBrain] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        out.append(
            HomunculusBrain(
                id=str(row["id"]),
                label=str(row.get("label") or row["id"]),
                summary=str(row.get("summary") or ""),
                kind=str(row.get("kind") or "homunculus"),
                prompt_tree=row.get("prompt_tree"),
            )
        )
    return tuple(out)


def list_brains() -> tuple[HomunculusBrain, ...]:
    extra = {b.id: b for b in _yaml_brains()}
    merged: list[HomunculusBrain] = []
    seen: set[str] = set()
    for b in _BUILTIN:
        merged.append(extra.pop(b.id, b))
        seen.add(b.id)
    for b in extra.values():
        if b.id not in seen:
            merged.append(b)
    return tuple(sorted(merged, key=lambda x: _version_key(x.id)))


def _version_key(vid: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in vid.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts) or (0,)


def highest_version() -> str:
    brains = list_brains()
    if not brains:
        return "0.0.0"
    return max((b.id for b in brains), key=_version_key)


def default_version() -> str:
    """Highest registered brain unless config pins a specific id."""
    cfg = merged_config().get("mastering") or {}
    hom = cfg.get("homunculus") or {}
    raw = str(hom.get("default_version") or DEFAULT_VERSION).strip()
    if raw.lower() in _LATEST_ALIASES:
        return highest_version()
    return normalize_version(raw)


def normalize_version(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text or text.lower() in _LATEST_ALIASES:
        return highest_version()
    brains = {b.id: b for b in list_brains()}
    if text not in brains:
        raise ValueError(
            f"Unknown homunculus version {text!r}. "
            f"Registered: {', '.join(sorted(brains))}"
        )
    return text


def resolve_brain(version: str | None) -> HomunculusBrain:
    vid = normalize_version(version)
    for b in list_brains():
        if b.id == vid:
            return b
    raise ValueError(f"Unknown homunculus version {version!r}")


def is_homunculus_brain(version: str | None) -> bool:
    try:
        return resolve_brain(version).kind == "homunculus"
    except ValueError:
        return False


def brains_public() -> list[dict[str, Any]]:
    current = default_version()
    return [
        {
            "id": b.id,
            "label": b.label,
            "summary": b.summary,
            "kind": b.kind,
            "prompt_tree": b.prompt_tree,
            "is_default": b.id == current,
        }
        for b in list_brains()
    ]


def stamp_build_identity(ctx: Any) -> None:
    """Stamp git_sha and driver_build_id for forensics correlation."""
    import os
    import subprocess

    git_sha = os.environ.get("MUX_GIT_SHA", "").strip()
    if not git_sha:
        try:
            git_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(ctx.root),
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except Exception:
            git_sha = ""
    driver_build = os.environ.get("MUX_DRIVER_BUILD_ID", "").strip() or git_sha[:12]

    def _mut(meta: dict[str, Any]) -> None:
        if git_sha:
            meta["git_sha"] = git_sha
        if driver_build:
            meta["driver_build_id"] = driver_build

    ctx.mutate_run_meta(_mut)


def stamp_run_meta(ctx: Any, raw: str | None = None) -> str:
    """Persist homunculus_version on a new run. Never overwrite mid-run."""
    import os

    if ctx.artifact_exists("run_meta.json"):
        existing = (ctx.read_json("run_meta.json") or {}).get("homunculus_version")
        if existing:
            return str(existing)
    text = (raw or os.environ.get("MUX_HOMUNCULUS_VERSION") or "").strip() or None
    vid = normalize_version(text)
    brain = resolve_brain(vid)

    def _mut(meta: dict[str, Any]) -> None:
        meta.setdefault("homunculus_version", vid)
        meta.setdefault("homunculus_kind", brain.kind)

    ctx.mutate_run_meta(_mut)
    if is_homunculus_brain(vid):
        from interview_mux.homunculus.persona import write_persona

        write_persona(ctx)
    return vid
