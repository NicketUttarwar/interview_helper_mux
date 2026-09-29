"""Junction owed a recut, mix held on it, junction held on mix's assembly (ISSUES 75)."""

from __future__ import annotations

import json

from run_fixtures import isolated_run_ctx

from interview_mux import delivery_guardrails as dg


def _stale_assembly(monkeypatch, exempt: str | None) -> None:
    monkeypatch.setattr("interview_mux.homunculus.agenda.assembly_stale_versus_edl", lambda c: True)
    monkeypatch.setattr(
        "interview_mux.ordering_authority.ordering_exempt", lambda c, s, p: exempt
    )


def test_junction_that_owes_a_recut_is_not_held_on_the_stale_assembly(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_junction_deadlock")
    _stale_assembly(monkeypatch, "junction_recut_precedes_mix")
    assert "assembly_stale_versus_edl" not in dg.upstream_stale_blockers(ctx, "junction_snip_qa")


def test_junction_without_an_owed_recut_still_waits_for_mix(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_junction_waits")
    _stale_assembly(monkeypatch, None)
    assert "assembly_stale_versus_edl" in dg.upstream_stale_blockers(ctx, "junction_snip_qa")


def test_finalize_still_waits_for_a_fresh_assembly(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_finalize_waits")
    _stale_assembly(monkeypatch, "junction_recut_precedes_mix")
    assert "assembly_stale_versus_edl" in dg.upstream_stale_blockers(ctx, "master_finalize")


def test_a_code_change_clears_every_inherited_halt(tmp_path, monkeypatch) -> None:
    """The x6 'complete junction before mix' halt outlived two fixes on exec_055."""
    from interview_mux import identical_failures as idf

    monkeypatch.delenv("MUX_FORENSICS", raising=False)
    ctx = isolated_run_ctx(tmp_path, "exec_halt_inherited")
    (ctx.run_dir / "run_meta.json").write_text(
        json.dumps({idf.PRODUCT_FINGERPRINT_META_KEY: "old-code"}), encoding="utf-8"
    )
    monkeypatch.setattr(idf, "product_code_fingerprint", lambda **kw: "new-code")
    reason = "complete junction_snip_qa before running mix (recovery:incomplete_cut_unresolved)"
    sig = idf.failure_signature(failed_stage="mix", producer="", reason=reason)
    for _ in range(idf.halt_after() + 1):
        idf.record_identical_failure(ctx, failed_stage="mix", producer="", reason=reason)
    stored = json.loads((ctx.run_dir / "operator" / "identical_failures.json").read_text(encoding="utf-8"))
    assert stored["signatures"][sig]["halt"] is True
    result = idf.sync_identical_halts_with_product(ctx, forensics=False)
    assert result["cleared"] >= 1
    assert idf.is_halted(ctx, sig) is False
