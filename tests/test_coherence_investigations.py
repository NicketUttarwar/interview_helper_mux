from __future__ import annotations

from interview_mux.coherence.investigations import coherence_investigations


def test_investigations_cap_and_shape():
    report = {
        "risks": [
            {
                "risk_id": f"r{i}",
                "kind": "topic_drift",
                "time_ms": i * 1000,
                "window_id": f"w{i}",
                "confidence": 0.9 - i * 0.05,
                "blocking": False,
                "evidence": {"drift_score": 0.7},
                "suggested_action": {"type": "rerun_stage", "stage": "content_brief_reanchor"},
                "status": "open",
            }
            for i in range(12)
        ]
    }
    items = coherence_investigations(report)
    assert len(items) <= 8
    assert items[0]["target"]["window_id"] == "w0"


def test_dedupe_key_includes_window(monkeypatch, tmp_path):
    from interview_mux.analysis_memory import _investigation_dedupe_key, enqueue_investigations
    from interview_mux.run_context import RunContext

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("dedupe", create=True)
    base = {
        "kind": "topic_drift",
        "suggested_action": {"type": "rerun_stage", "stage": "content_brief_reanchor"},
    }
    enqueue_investigations(
        ctx,
        [
            {**base, "target": {"window_id": "w1"}, "question": "a"},
            {**base, "target": {"window_id": "w2"}, "question": "b"},
        ],
        created_by_stage="coherence",
    )
    queue = ctx.read_json("understanding/investigation_queue.json")
    assert len(queue["items"]) == 2
    keys = {_investigation_dedupe_key(it) for it in queue["items"]}
    assert len(keys) == 2
