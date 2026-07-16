from __future__ import annotations

from interview_mux.downstream_probe import downstream_probe_enabled, probe_consumers


from pathlib import Path


class _Ctx:
    def artifact_exists(self, rel: str) -> bool:
        return rel == "understanding/content_brief.json"

    def read_json(self, rel: str):
        return {"thesis": "long enough thesis here", "topics": [{"name": "a"}], "key_claims": []}

    def path(self, rel: str):
        return Path("/tmp/nonexistent") / rel


def test_probe_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr(
        "interview_mux.downstream_probe.downstream_probe_enabled",
        lambda cfg=None: False,
    )
    assert probe_consumers(_Ctx(), "content_context", {}, staged=True) == []


def test_probe_enabled_runs():
    assert downstream_probe_enabled() is True
    findings = probe_consumers(
        _Ctx(),
        "content_context",
        {"thesis": "long enough thesis", "topics": [{"name": "x"}], "key_claims": []},
        staged=True,
    )
    assert isinstance(findings, list)


def test_boundary_probe_does_not_apply_consumer_output_rules():
    """segment_classification sufficiency (segments[]) must not run on boundaries.json."""
    artifact = {
        "boundaries": [
            {
                "segment_id": "seg_001",
                "start_ms": 0,
                "end_ms": 1000,
                "speaker_id": "spk_0",
                "proposed_split_reason": "pause",
            }
        ]
    }
    findings = probe_consumers(_Ctx(), "boundary_detection", artifact, staged=True)
    messages = [f.message for f in findings]
    assert not any("segments needs at least" in m for m in messages)
