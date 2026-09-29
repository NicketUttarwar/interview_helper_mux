"""Content-addressed cache for the heavy deterministic local-model stages.

Transcription and the audio probe platform depend only on bytes already on
disk (the normalized audio, the transcript) and on configuration. Rerunning
the same source file, which is how the pipeline is developed and debugged,
paid for both every time: about 8 minutes of probes and 3 to 6 minutes of
STT per run on the one-hour interview (ISSUES 93).

A stage asks ``lookup`` with a key built from the hashes of its inputs and
the configuration that shapes its output. On a hit it writes the cached
documents through ``ctx.write_json`` exactly as it would have written fresh
ones, so staging, ownership and completion see a normal stage run. After a
fresh run the stage calls ``store`` with the same documents.

The cache lives beside the executions (``<executions_root>/../stage_cache``
by default, ``stage_cache.root`` in config to move it) and holds JSON only.
``MUX_STAGE_CACHE=0`` or ``stage_cache.enabled=false`` disables it; a key
that no longer matches (new model, new config, new source) is simply a miss.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config

CACHE_VERSION = 1


def cache_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    block = (cfg or merged_config()).get("stage_cache") or {}
    return {"enabled": True, "root": "", **(block if isinstance(block, dict) else {})}


def cache_enabled() -> bool:
    env = os.environ.get("MUX_STAGE_CACHE")
    if env is not None:
        return env.strip() not in {"0", "false", "no", ""}
    return bool(cache_cfg().get("enabled", True))


def cache_root(ctx: Any | None = None) -> Path:
    raw = str(cache_cfg().get("root") or "").strip()
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            from interview_mux.config import repo_root

            p = repo_root() / p
        return p
    executions = getattr(ctx, "executions_root", None)
    if executions is None:
        from interview_mux.run_context import RunContext

        executions = RunContext._executions_root(merged_config())
    return Path(executions).parent / "stage_cache"


def file_digest(path: Path) -> str:
    """SHA-256 of a file's bytes; the empty digest when it is missing."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return "missing"
    return h.hexdigest()


def config_digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def cache_key(stage: str, *parts: str) -> str:
    joined = "|".join([f"v{CACHE_VERSION}", stage, *[str(p) for p in parts]])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _entry_dir(ctx: Any, stage: str, key: str) -> Path:
    return cache_root(ctx) / stage / key


def lookup(ctx: Any, stage: str, key: str, rels: list[str]) -> dict[str, Any] | None:
    """Return ``{rel: doc}`` for every ``rel`` when all are cached, else None."""
    if not cache_enabled():
        return None
    entry = _entry_dir(ctx, stage, key)
    out: dict[str, Any] = {}
    for rel in rels:
        p = entry / rel
        if not p.is_file():
            return None
        try:
            out[rel] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return out


def store(ctx: Any, stage: str, key: str, docs: dict[str, Any]) -> bool:
    """Write ``docs`` (``{rel: doc}``) under the key; never raises."""
    if not cache_enabled():
        return False
    entry = _entry_dir(ctx, stage, key)
    tmp = entry.with_name(entry.name + ".tmp")
    try:
        if tmp.exists():
            shutil.rmtree(tmp)
        for rel, doc in docs.items():
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        (tmp / "meta.json").write_text(
            json.dumps({"stage": stage, "key": key, "run_id": getattr(ctx, "run_id", "")}),
            encoding="utf-8",
        )
        if entry.exists():
            shutil.rmtree(entry)
        tmp.rename(entry)
        return True
    except Exception:  # noqa: BLE001 - a cache must never fail the stage
        try:
            if tmp.exists():
                shutil.rmtree(tmp)
        except Exception:
            pass
        return False


def restore(ctx: Any, stage: str, key: str, rels: list[str]) -> bool:
    """On a hit, write every cached document through ``ctx.write_json``."""
    cached = lookup(ctx, stage, key, rels)
    if cached is None:
        return False
    for rel in rels:
        ctx.write_json(rel, cached[rel])
    try:
        ctx.log(
            f"{stage}: restored {len(rels)} artifact(s) from the stage cache "
            f"(key {key[:12]}); the model did not run",
            level="info",
            stage=stage,
            detail={"stage_cache_hit": True, "key": key, "artifacts": list(rels)},
        )
    except Exception:
        pass
    return True


__all__ = [
    "cache_cfg",
    "cache_enabled",
    "cache_key",
    "cache_root",
    "config_digest",
    "file_digest",
    "lookup",
    "restore",
    "store",
]
