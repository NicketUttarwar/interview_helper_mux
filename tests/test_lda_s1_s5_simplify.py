"""listen_delight_audit S1–S5 simplify pins (high-risk audit MODE=fix)."""

from __future__ import annotations

import inspect

from interview_mux.artifact_ownership import row_for_path, write_permitted
from interview_mux.listen_delight import (
    AUDIT_REL,
    _handle_listen_delight_failure,
    rerun_listen_delight_after_mix,
    run_listen_delight_audit,
)
from interview_mux.listen_delight_remutate import apply_listen_delight_remutate
from run_fixtures import init_run_meta_for_test, isolated_run_ctx


def test_s1_stage_and_handle_never_apply_remutate() -> None:
    handle_src = inspect.getsource(_handle_listen_delight_failure)
    assert "apply_listen_delight_remutate" not in handle_src
    assert "deferred_to_recovery" in handle_src
    stage_src = inspect.getsource(run_listen_delight_audit)
    assert "apply_listen_delight_remutate" not in stage_src


def test_s2_post_mix_does_not_write_audit_ssot(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "lda_s2_post_mix")
    init_run_meta_for_test(ctx)
    src = inspect.getsource(rerun_listen_delight_after_mix)
    assert "write_json" not in src
    assert "AUDIT_REL" not in src
    out = rerun_listen_delight_after_mix(ctx)
    assert out.get("pass") == "post_mix"
    assert out.get("advisory") is True
    assert not ctx.artifact_exists(AUDIT_REL)


def test_s3_remutate_apply_never_packs_selection() -> None:
    src = inspect.getsource(apply_listen_delight_remutate)
    assert "enforce_creative_selection_edit" not in src
    assert 'write_json("master/selection.json"' not in src
    assert "nugget_retention_remutate_no_selection_pack" in src


def test_s4_fail_early_branch_deleted_from_stage() -> None:
    src = inspect.getsource(run_listen_delight_audit)
    assert "_fail_early_at_audit_stage" not in src
    assert "raise_loud_failure" not in src
    assert 'pass_phase="pre_mix"' in src
    assert "blocking = False" in src


def test_s5_ownership_mix_denied_delight_and_finalize_allow(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "lda_s5_own")
    init_run_meta_for_test(ctx)
    ok_mix, _ = write_permitted(ctx, AUDIT_REL, "mix")
    assert not ok_mix
    ok_ld, reason_ld = write_permitted(ctx, AUDIT_REL, "listen_delight_audit")
    assert ok_ld, reason_ld
    ok_fin, reason_fin = write_permitted(ctx, AUDIT_REL, "master_finalize")
    assert ok_fin, reason_fin
    row = row_for_path(AUDIT_REL)
    assert row is not None
    assert "mix" not in row.producers
    assert set(row.producers) >= {"listen_delight_audit", "master_finalize"}
