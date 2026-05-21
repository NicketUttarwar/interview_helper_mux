from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.common import assets_root


def assemble_highlight_reel(
    source_wav: Path,
    segments: list[dict[str, Any]],
    ordered_ids: list[str],
    *,
    interview_id: str,
    crossfade_ms: int = 300,
) -> Path:
    """pydub cuts + crossfades for preset A."""
    try:
        from pydub import AudioSegment
    except ImportError as e:
        raise ImportError("Install deps: pip install -r requirements.txt") from e

    audio = AudioSegment.from_file(source_wav)
    by_id = {s["segment_id"]: s for s in segments}
    combined: AudioSegment | None = None
    fade = crossfade_ms

    for sid in ordered_ids:
        seg = by_id.get(sid)
        if not seg:
            continue
        clip = audio[seg["t_start_ms"] : seg["t_end_ms"]]
        if combined is None:
            combined = clip
        else:
            combined = combined.append(clip, crossfade=fade)

    if combined is None:
        raise ValueError("No segments to assemble")

    out_dir = assets_root() / interview_id / "mux"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "highlight_reel.wav"
    combined.export(out_path, format="wav")
    return out_path


def write_edl(conn: Any, run_id: str, interview_id: str, ordered_ids: list[str], segments: list[dict[str, Any]]) -> None:
    by_id = {s["segment_id"]: s for s in segments}
    for i, sid in enumerate(ordered_ids):
        seg = by_id.get(sid)
        if not seg:
            continue
        conn.execute(
            """
            INSERT INTO edl_clip (run_id, order_index, segment_id, interview_id, in_ms, out_ms, meta_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, order_index) DO UPDATE SET
              segment_id = excluded.segment_id,
              in_ms = excluded.in_ms,
              out_ms = excluded.out_ms
            """,
            (
                run_id,
                i,
                sid,
                interview_id,
                seg["t_start_ms"],
                seg["t_end_ms"],
                json.dumps({"preset": "A"}, sort_keys=True),
            ),
        )
    conn.commit()
