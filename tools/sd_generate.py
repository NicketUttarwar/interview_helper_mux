#!/usr/bin/env python3
"""Generate a square podcast cover image via local MLX / mflux.

Reads JSON from stdin:
  {prompt, negative_prompt, output_path, width, height, steps, model_id, seed}

Writes JSON to stdout: {ok, output_path, width, height, error?}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    req = json.load(sys.stdin)
    prompt = str(req.get("prompt") or "").strip()
    out = Path(str(req.get("output_path") or "cover.png"))
    width = int(req.get("width") or 1024)
    height = int(req.get("height") or 1024)
    steps = int(req.get("steps") or 4)
    seed = int(req.get("seed") or 42)
    model_id = str(req.get("model_id") or "")
    if width != height:
        print(json.dumps({"ok": False, "error": "width must equal height (square title card)"}))
        return 1
    if not prompt:
        print(json.dumps({"ok": False, "error": "empty prompt"}))
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)

    # Try mflux first
    try:
        from mflux.flux.flux import Flux1
        from mflux.config.config import Config

        flux = Flux1.from_name(
            model_name="schnell",
            quantize=4,
        )
        image = flux.generate_image(
            seed=seed,
            prompt=prompt,
            config=Config(num_inference_steps=steps, width=width, height=height),
        )
        image.save(path=str(out))
        print(json.dumps({"ok": True, "output_path": str(out), "width": width, "height": height, "backend": "mflux"}))
        return 0
    except Exception as mflux_exc:
        mflux_err = str(mflux_exc)

    # Fallback: solid branded placeholder so pipeline can continue (runner may fail-open to show art)
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (width, height), (15, 23, 42))
        draw = ImageDraw.Draw(img)
        # Abstract geometric stand-in (not used if show art fallback preferred)
        margin = width // 8
        draw.ellipse([margin, margin, width - margin, height - margin], outline=(212, 175, 55), width=max(2, width // 128))
        draw.line([width // 2, margin, width // 2, height - margin], fill=(212, 175, 55), width=max(2, width // 256))
        img.save(out)
        print(
            json.dumps(
                {
                    "ok": True,
                    "output_path": str(out),
                    "width": width,
                    "height": height,
                    "backend": "placeholder",
                    "warning": f"mflux unavailable: {mflux_err}",
                    "model_id": model_id,
                }
            )
        )
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"mflux={mflux_err}; pillow={exc}"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
