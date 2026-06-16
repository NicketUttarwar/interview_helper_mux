from __future__ import annotations

import pytest

from interview_mux.coherence.duration_gate import build_gate, coherence_activated
from interview_mux.run_context import RunContext


def _seed_duration(ctx: RunContext, duration_ms: int) -> None:
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "fixture long interview",
            "words": [
                {"text": "start", "start_ms": 0, "end_ms": 1000, "speaker_id": "spk_0"},
                {"text": "end", "start_ms": duration_ms - 1000, "end_ms": duration_ms, "speaker_id": "spk_1"},
            ],
        },
    )


@pytest.mark.parametrize(
    ("duration_ms", "expected"),
    [
        (29 * 60 * 1000, False),
        (31 * 60 * 1000, True),
    ],
)
def test_duration_gate_30m_threshold(tmp_path, monkeypatch, duration_ms, expected):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("dur_gate", create=True)
    _seed_duration(ctx, duration_ms)
    gate = build_gate(ctx)
    assert gate["activated"] is expected
    assert coherence_activated(ctx) is expected
