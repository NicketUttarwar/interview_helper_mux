"""OpenAI Images client for War Room episode covers (multi-candidate + optional style ref)."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from openai import OpenAI

from interview_mux.config import repo_root, require_secret
from interview_mux.podcast_rss.cover_prompt import cover_image_cfg
from interview_mux.podcast_rss.settings import show_artwork_source_rel

logger = logging.getLogger(__name__)

# Context7 pin (developers.openai.com Images API):
# - Generations models: gpt-image-1, gpt-image-1.5, gpt-image-1-mini
# - quality: low | medium | high | auto — we lock high
# - size: square 1024x1024 then LANCZOS upscale to min_output_px (Apple max preferred: 3000)
# - output: JPEG for Apple/Spotify feed objects
DEFAULT_COVER_IMAGE = {
    "provider": "openai",
    "model": "gpt-image-1",
    "size": "1024x1024",
    "quality": "high",
    "candidate_count": 3,
    "min_output_px": 3000,
    "output_format": "jpeg",
    "jpeg_quality": 90,
    "prompt_max_chars": 32000,
}

APPLE_MIN_COVER_PX = 1400


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


def ensure_square_cover(
    path: Path,
    *,
    min_size: int,
    output_format: str = "jpeg",
    jpeg_quality: int = 90,
    dest: Path | None = None,
) -> Path:
    """Crop square, upscale to min_size, save as JPEG (default) or PNG."""
    out_path = dest or path
    fmt = (output_format or "jpeg").lower()
    if fmt in {"jpg", "jpeg"}:
        if out_path.suffix.lower() not in {".jpg", ".jpeg"}:
            out_path = out_path.with_suffix(".jpg")
        save_format = "JPEG"
    else:
        if out_path.suffix.lower() != ".png":
            out_path = out_path.with_suffix(".png")
        save_format = "PNG"

    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow missing — skip cover upscale for %s", path)
        if dest and dest != path and path.is_file():
            dest.write_bytes(path.read_bytes())
            return dest
        return path

    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        if w != h:
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            im = im.crop((left, top, left + side, top + side))
            w = h = side
        target = max(int(min_size), APPLE_MIN_COVER_PX)
        if w != target:
            im = im.resize((target, target), Image.Resampling.LANCZOS)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if save_format == "JPEG":
            q = max(60, min(95, int(jpeg_quality)))
            im.save(out_path, format="JPEG", quality=q, optimize=True)
        else:
            im.save(out_path, format="PNG")
    # Remove stale other-extension sibling when converting in place conceptually
    if dest is None and path != out_path and path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
    return out_path


# Back-compat alias used by older call sites / tests
def ensure_square_min(path: Path, *, min_size: int) -> None:
    ensure_square_cover(path, min_size=min_size, output_format="png")


def cover_dimensions(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as im:
        return im.size


def require_cover_min_size(path: Path, *, min_px: int = APPLE_MIN_COVER_PX) -> None:
    w, h = cover_dimensions(path)
    if w < min_px or h < min_px:
        raise RuntimeError(
            f"Cover art {path.name} is {w}x{h}; need at least {min_px}x{min_px} (Apple minimum)"
        )


def _style_ref_path(settings: dict[str, Any]) -> Path | None:
    ref = settings.get("style_reference") if isinstance(settings.get("style_reference"), dict) else {}
    if not ref.get("enabled", True):
        return None
    rel = str(ref.get("path") or "")
    if not rel:
        rel = show_artwork_source_rel()
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

    # Generate to a temp PNG path then finalize to JPEG dest
    raw_dest = dest.with_suffix(".png") if dest.suffix.lower() in {".jpg", ".jpeg"} else dest

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
        raise RuntimeError("OpenAI Images response missing b64_json")
    _decode_b64_to_path(b64, raw_dest)
    finalized = ensure_square_cover(
        raw_dest,
        min_size=int(settings.get("min_output_px") or 3000),
        output_format=str(settings.get("output_format") or "jpeg"),
        jpeg_quality=int(settings.get("jpeg_quality") or 90),
        dest=dest if dest.suffix.lower() in {".jpg", ".jpeg"} else None,
    )
    if finalized != dest and dest.suffix.lower() in {".jpg", ".jpeg"}:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(finalized.read_bytes())
        if finalized.is_file() and finalized.resolve() != dest.resolve():
            try:
                finalized.unlink()
            except OSError:
                pass
        return dest
    return finalized


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
    out_ext = ".jpg" if str(settings.get("output_format") or "jpeg").lower() in {"jpg", "jpeg"} else ".png"

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
                    raw = dest_dir / f"{i}.png"
                    _decode_b64_to_path(b64, raw)
                    finalized = ensure_square_cover(
                        raw,
                        min_size=int(settings.get("min_output_px") or 3000),
                        output_format=str(settings.get("output_format") or "jpeg"),
                        jpeg_quality=int(settings.get("jpeg_quality") or 90),
                        dest=dest_dir / f"{i}{out_ext}",
                    )
                    paths.append(finalized)
                return paths
        except Exception as exc:
            logger.info("images.generate n=%s unavailable (%s); sequential calls", n, exc)

    for i in range(n):
        dest = dest_dir / f"{i}{out_ext}"
        paths.append(
            _generate_one(client, prompt=prompt, settings=settings, dest=dest, seed=1000 + i)
        )
    return paths
