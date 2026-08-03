"""OpenAI Images client for War Room episode covers (multi-candidate + optional style ref)."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from openai import OpenAI

from interview_mux.config import merged_config, repo_root, require_secret
from interview_mux.podcast_rss.cover_prompt import cover_image_cfg

logger = logging.getLogger(__name__)

# Context7 pin (developers.openai.com Images API, 2026-08):
# - Generations models: gpt-image-1, gpt-image-1.5, gpt-image-1-mini (non-mini flagship: gpt-image-1)
# - quality: low | medium | high | auto — we lock high
# - size: square practical default 1024x1024; upscale to min_output_px locally
# - n: try n=candidate_count; fall back to sequential calls if unsupported
# - edits + input_fidelity: low|high on gpt-image-1 family (not gpt-image-2)
DEFAULT_COVER_IMAGE = {
    "provider": "openai",
    "model": "gpt-image-1",
    "size": "1024x1024",
    "quality": "high",
    "candidate_count": 3,
    "min_output_px": 1400,
    "prompt_max_chars": 32000,
}


def _client() -> OpenAI:
    return OpenAI(api_key=require_secret("OPENAI_API_KEY"))


def resolve_cover_image_settings(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cov = cover_image_cfg(cfg)
    out = dict(DEFAULT_COVER_IMAGE)
    out.update({k: v for k, v in cov.items() if v is not None})
    return out


def _decode_b64_to_path(b64: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(base64.b64decode(b64))
    return dest


def ensure_square_min(path: Path, *, min_size: int) -> None:
    try:
        from PIL import Image

        with Image.open(path) as im:
            w, h = im.size
            if w != h:
                side = min(w, h)
                left = (w - side) // 2
                top = (h - side) // 2
                im = im.crop((left, top, left + side, top + side))
                w = h = side
            if w < min_size:
                im = im.resize((min_size, min_size), Image.Resampling.LANCZOS)
            im.save(path, format="PNG")
    except ImportError:
        logger.warning("Pillow missing — skip cover upscale for %s", path)


def _style_ref_path(settings: dict[str, Any]) -> Path | None:
    ref = settings.get("style_reference") if isinstance(settings.get("style_reference"), dict) else {}
    if not ref.get("enabled", True):
        return None
    rel = str(ref.get("path") or "")
    if not rel:
        podcast = (merged_config().get("podcast") or {}) if isinstance(merged_config().get("podcast"), dict) else {}
        rel = str(podcast.get("show_artwork_path") or "config/podcast/the-war-room-cover.png")
    p = Path(rel)
    if not p.is_absolute():
        p = repo_root() / p
    return p if p.is_file() else None


def _generate_one(
    client: OpenAI,
    *,
    prompt: str,
    settings: dict[str, Any],
    dest: Path,
    seed: int | None = None,
) -> Path:
    model = str(settings.get("model") or DEFAULT_COVER_IMAGE["model"])
    size = str(settings.get("size") or DEFAULT_COVER_IMAGE["size"])
    quality = str(settings.get("quality") or "high")
    style_path = _style_ref_path(settings)
    ref = settings.get("style_reference") if isinstance(settings.get("style_reference"), dict) else {}
    use_edits = bool(style_path) and str(ref.get("mode") or "edits") == "edits"

    if use_edits and style_path is not None:
        kwargs: dict[str, Any] = {
            "model": model,
            "image": open(style_path, "rb"),  # noqa: SIM115 — closed after call
            "prompt": (
                prompt
                + " Use the reference only for palette, grain, and mood. "
                "Do not copy emblems, lettering, or logos from the reference."
            ),
        }
        fidelity = str(ref.get("input_fidelity") or "low")
        # gpt-image-1 family supports input_fidelity; ignore failures below.
        try:
            kwargs["input_fidelity"] = fidelity
            result = client.images.edit(**kwargs)
        except TypeError:
            kwargs.pop("input_fidelity", None)
            result = client.images.edit(**kwargs)
        finally:
            img_handle = kwargs.get("image")
            if hasattr(img_handle, "close"):
                img_handle.close()
    else:
        kwargs = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "quality": quality,
            "n": 1,
        }
        if seed is not None:
            try:
                result = client.images.generate(**kwargs, seed=seed)
            except TypeError:
                result = client.images.generate(**kwargs)
        else:
            result = client.images.generate(**kwargs)

    data = getattr(result, "data", None) or []
    if not data:
        raise RuntimeError("OpenAI Images returned no data")
    b64 = getattr(data[0], "b64_json", None)
    if not b64:
        # URL-only responses — fetch not implemented; require b64
        raise RuntimeError("OpenAI Images response missing b64_json")
    _decode_b64_to_path(b64, dest)
    ensure_square_min(dest, min_size=int(settings.get("min_output_px") or 1400))
    return dest


def generate_cover_candidates(
    *,
    prompt: str,
    dest_dir: Path,
    count: int | None = None,
    settings: dict[str, Any] | None = None,
) -> list[Path]:
    """Generate exactly `count` candidates from the same prompt. Prefer n=count; else sequential."""
    settings = settings or resolve_cover_image_settings()
    n = int(count if count is not None else settings.get("candidate_count") or 3)
    n = max(1, min(n, 8))
    dest_dir.mkdir(parents=True, exist_ok=True)
    client = _client()
    model = str(settings.get("model") or DEFAULT_COVER_IMAGE["model"])
    size = str(settings.get("size") or DEFAULT_COVER_IMAGE["size"])
    quality = str(settings.get("quality") or "high")
    style_path = _style_ref_path(settings)
    ref = settings.get("style_reference") if isinstance(settings.get("style_reference"), dict) else {}
    use_edits = bool(style_path) and str(ref.get("mode") or "edits") == "edits"

    paths: list[Path] = []

    if not use_edits:
        try:
            result = client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
                quality=quality,
                n=n,
            )
            data = getattr(result, "data", None) or []
            if len(data) >= n:
                for i in range(n):
                    b64 = getattr(data[i], "b64_json", None)
                    if not b64:
                        raise RuntimeError(f"candidate {i} missing b64_json")
                    dest = dest_dir / f"{i}.png"
                    _decode_b64_to_path(b64, dest)
                    ensure_square_min(dest, min_size=int(settings.get("min_output_px") or 1400))
                    paths.append(dest)
                return paths
        except Exception as exc:
            logger.info("images.generate n=%s unavailable (%s); sequential calls", n, exc)

    # Sequential (edits path always sequential; also diversity seeds when n unsupported)
    for i in range(n):
        dest = dest_dir / f"{i}.png"
        _generate_one(client, prompt=prompt, settings=settings, dest=dest, seed=1000 + i)
        paths.append(dest)
    return paths
