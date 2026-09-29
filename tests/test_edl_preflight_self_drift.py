"""edl is not blocked by its own output drifting from the selection (ISSUES 65)."""

from __future__ import annotations

from interview_mux.artifact_sanitize import preflight


def test_edl_ignores_its_own_order_drift(monkeypatch) -> None:
    class _Ctx:
        def artifact_exists(self, rel):
            return rel == "master/edl.json"

    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.config.block_consumers_on_unsanitary", lambda: True
    )
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.registry.edl_sanitary_errors",
        lambda c: ["selection_edl_order_drift", "phantom_vo_clip:vo_x"],
    )
    monkeypatch.setattr("interview_mux.artifact_sanitize.registry.vo_sanitary_errors", lambda c: [])
    errs = preflight.sanitary_preflight_errors(_Ctx(), "edl")
    assert not any("order_drift" in e for e in errs)
    assert any("phantom_vo_clip" in e for e in errs)
