"""i8: do not omit orientation when EDL/WAV already seats it."""

from __future__ import annotations

import json
import os

os.environ["MUX_FORENSICS"] = "0"

from interview_mux.opening_orientation import ORIENTATION_LINE_ID, ensure_episode_orientation
from run_fixtures import init_run_meta_for_test, isolated_run_ctx


def _write(ctx, rel: str, data: dict | bytes, binary: bool = False) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    if binary:
        path.write_bytes(data)  # type: ignore[arg-type]
    else:
        path.write_text(json.dumps(data), encoding="utf-8")


def test_i8_keep_orientation_when_wav_seated(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_i8_orient")
    init_run_meta_for_test(ctx)
    monkeypatch.setattr(
        "interview_mux.opening_orientation.native_open_already_orients",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    # Fake seated WAV
    wav = ctx.path("vo_pickup", "synthesized", f"{ORIENTATION_LINE_ID}.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"0" * 2000)
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_007",
                "text": "Host asks a substantive follow-up about the guest's work.",
                "delivery": "synthesize",
                "targets_segment_id": "seg_007",
            }
        ],
        "opening_orientation": {"omitted": True, "omit_reason": "native_open_self_orients"},
    }
    out, actions = ensure_episode_orientation(ctx, gap, ["seg_002", "seg_007"])
    ids = [ln.get("line_id") for ln in (out.get("interviewer_lines") or []) if isinstance(ln, dict)]
    assert ORIENTATION_LINE_ID in ids, actions
    assert not (out.get("opening_orientation") or {}).get("omitted")
