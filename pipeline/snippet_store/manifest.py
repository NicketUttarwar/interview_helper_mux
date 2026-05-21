from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.common import assets_root


def build_snippet_manifest(
    interview_id: str,
    segments: list[dict[str, Any]],
    *,
    ordered_ids: list[str] | None = None,
    transcript_revision_id: str | None = None,
) -> dict[str, Any]:
    order = ordered_ids or [s["segment_id"] for s in segments]
    by_id = {s["segment_id"]: s for s in segments}
    return {
        "interview_id": interview_id,
        "transcript_revision_id": transcript_revision_id,
        "ordered_segment_ids": order,
        "segments": [by_id[sid] for sid in order if sid in by_id],
    }


def write_snippet_manifest(manifest: dict[str, Any]) -> Path:
    root = assets_root()
    iid = manifest["interview_id"]
    out_dir = root / iid / "snippets"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out_path
