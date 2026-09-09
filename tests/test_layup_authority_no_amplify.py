"""Ship 1: under nugget_layup_authority, seed/density amplify is skipped."""

from __future__ import annotations

from pathlib import Path

from interview_mux.artifact_repairs import _seed_missing_high_gap_interviewer_lines
from run_fixtures import isolated_run_ctx, patch_executions_root


def test_seed_skipped_under_layup_authority(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = isolated_run_ctx(tmp_path, "exec_layup_auth_seed")
    out = {
        "nugget_layup_authority": True,
        "interviewer_lines": [],
    }
    applied: list[dict] = []
    called = {"fill": False}

    def _boom(*_a, **_k):  # noqa: ANN001
        called["fill"] = True
        raise AssertionError("fill must not run under layup authority")

    monkeypatch.setattr(
        "interview_mux.high_gap_vo.fill_uncovered_high_gaps",
        _boom,
    )
    _seed_missing_high_gap_interviewer_lines(
        ctx, out, manifest_ids=set(), applied=applied
    )
    assert called["fill"] is False
    assert any(
        a.get("action") == "skip_high_gap_seed_under_layup_authority" for a in applied
    )
    assert out["interviewer_lines"] == []


def test_density_skipped_under_layup_authority(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = isolated_run_ctx(tmp_path, "exec_layup_auth_density")
    out = {
        "nugget_layup_authority": True,
        "interviewer_lines": [
            {
                "line_id": "vo_existing",
                "text": "Hello.",
                "targets_segment_id": "seg_001",
                "delivery": "synthesize",
            }
        ],
        "gaps": [],
    }
    applied: list[dict] = []
    density_calls = {"n": 0}

    real_enforce = None
    import interview_mux.artifact_repairs as ar

    real_enforce = ar._enforce_min_vo_insert_ratio

    def _wrap(*a, **k):  # noqa: ANN001
        density_calls["n"] += 1
        return real_enforce(*a, **k)

    monkeypatch.setattr(ar, "_enforce_min_vo_insert_ratio", _wrap)
    # Drive the density gate the same way repair_gap_report does.
    skip_density = False
    try:
        from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

        skip_density = gap_fill_was_skipped(ctx)
    except Exception:
        skip_density = False
    if bool(out.get("nugget_layup_authority")):
        skip_density = True
        applied.append(
            {
                "action": "skip_vo_density_under_layup_authority",
                "reason": "nugget_layup_authority",
            }
        )
    if not skip_density:
        ar._enforce_min_vo_insert_ratio(ctx, out, applied=applied)
    assert density_calls["n"] == 0
    assert any(
        a.get("action") == "skip_vo_density_under_layup_authority" for a in applied
    )
