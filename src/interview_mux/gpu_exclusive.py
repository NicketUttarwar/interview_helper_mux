"""Serialize GPU-heavy local subprocesses so only one runs at a time.

On ~16GB Apple Silicon, overlapping MusicGen / Chatterbox / MMAudio / MLX /
DeepFilter jobs thrash unified memory and can abort Metal. Pipeline stages are
already sequential; this gate also covers:

- concurrent runs / stray workers
- back-to-back gens inside one stage (palette stems, SFX assets, VO lines)
- a post-exit cooldown so Metal/unified memory can settle before the next consumer
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_DEFAULT_CONSUMERS = frozenset(
    {
        "musicgen",
        "mmaudio",
        "chatterbox",
        "speech",
        "mlx",
        "llm",
        "deepfilter",
        "image",
    }
)


def local_gpu_cfg() -> dict[str, Any]:
    from interview_mux.config import merged_config

    block = merged_config().get("local_gpu") or {}
    return block if isinstance(block, dict) else {}


def gpu_serialize_enabled() -> bool:
    raw = os.environ.get("INTERVIEW_MUX_GPU_SERIALIZE")
    if raw is not None:
        return raw.strip().lower() not in {"0", "false", "no", "off"}
    return bool(local_gpu_cfg().get("serialize", True))


def gpu_cooldown_sec() -> float:
    raw = os.environ.get("INTERVIEW_MUX_GPU_COOLDOWN_SEC")
    if raw is not None and str(raw).strip() != "":
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    try:
        return max(0.0, float(local_gpu_cfg().get("cooldown_sec", 5)))
    except (TypeError, ValueError):
        return 5.0


def gpu_lock_timeout_sec() -> float:
    try:
        return max(60.0, float(local_gpu_cfg().get("lock_timeout_sec", 7200)))
    except (TypeError, ValueError):
        return 7200.0


def gpu_consumers() -> frozenset[str]:
    raw = local_gpu_cfg().get("consumers")
    if isinstance(raw, list) and raw:
        return frozenset(str(x).strip() for x in raw if str(x).strip())
    return _DEFAULT_CONSUMERS


def _lock_path():
    from interview_mux.config import repo_root

    path = repo_root() / "ASSETS" / ".gpu_exclusive.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def gpu_exclusive(
    consumer: str,
    *,
    ctx: Any | None = None,
    stage: str | None = None,
) -> Iterator[None]:
    """Hold the machine-wide GPU gate for one heavy local consumer, then cooldown.

    The subprocess must fully exit before this context exits; cooldown runs in
    ``finally`` so the next waiter cannot start until settle completes.
    """
    name = str(consumer or "unknown").strip().lower() or "unknown"
    if not gpu_serialize_enabled() or name not in gpu_consumers():
        yield
        return

    from filelock import FileLock, Timeout

    cooldown = gpu_cooldown_sec()
    lock = FileLock(str(_lock_path()), timeout=gpu_lock_timeout_sec())
    detail = {"consumer": name, "cooldown_sec": cooldown}
    if ctx is not None:
        try:
            ctx.log(
                f"GPU gate waiting: {name}",
                level="info",
                stage=stage or name,
                detail={**detail, "journey_kind": "execute"},
            )
        except Exception:
            pass
    else:
        logger.info("gpu_exclusive wait consumer=%s", name)

    from interview_mux.heavy_task_policy import wait_abort_backoff

    wait_abort_backoff(ctx, name)

    try:
        lock.acquire()
    except Timeout as exc:
        raise RuntimeError(
            f"GPU exclusive lock timed out waiting for consumer={name} "
            f"(another MusicGen/Chatterbox/MMAudio/MLX job still running?)"
        ) from exc

    if ctx is not None:
        try:
            ctx.log(
                f"GPU gate acquired: {name}",
                level="info",
                stage=stage or name,
                detail={**detail, "journey_kind": "execute"},
            )
        except Exception:
            pass
    try:
        yield
    finally:
        if cooldown > 0:
            if ctx is not None:
                try:
                    ctx.log(
                        f"GPU gate cooldown {cooldown:.0f}s after {name}",
                        level="info",
                        stage=stage or name,
                        detail={**detail, "journey_kind": "execute"},
                    )
                except Exception:
                    pass
            time.sleep(cooldown)
        try:
            lock.release()
        except Exception:
            pass
        if ctx is not None:
            try:
                ctx.log(
                    f"GPU gate released: {name}",
                    level="info",
                    stage=stage or name,
                    detail={**detail, "journey_kind": "execute"},
                )
            except Exception:
                pass
