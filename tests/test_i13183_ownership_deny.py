"""exec_13183 ownership DENY → ALLOW owner pin (listen_delight under mix)."""

from __future__ import annotations

import os

os.environ["MUX_FORENSICS"] = "0"

from interview_mux.artifact_ownership import (
    parse_authority_denied_resume,
    row_for_path,
    write_permitted,
)
from interview_mux.heal_routing import classify_heal_error
from run_fixtures import init_run_meta_for_test, isolated_run_ctx

DELIGHT = "mastering/listen_delight_audit.json"


def test_mix_is_not_allow_writer_for_delight(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "delight_own")
    init_run_meta_for_test(ctx)
    ok_mix, reason_mix = write_permitted(ctx, DELIGHT, "mix")
    assert not ok_mix, reason_mix
    ok_ld, reason_ld = write_permitted(ctx, DELIGHT, "listen_delight_audit")
    assert ok_ld, reason_ld
    row = row_for_path(DELIGHT)
    assert row is not None
    assert "mix" not in row.producers
    assert "listen_delight_audit" in row.producers


def test_parse_authority_denied_delight_under_mix() -> None:
    blob = (
        "authority_denied:persist:mastering/listen_delight_audit.json:"
        "mix:mix_seated:listen_delight_audit"
    )
    pin = parse_authority_denied_resume(blob, denied_stage="mix")
    assert pin == "listen_delight_audit"


def test_classify_heal_error_authority_denied_pins_allow_owner(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "deny_pin")
    init_run_meta_for_test(ctx)
    blob = (
        "authority_denied:persist:mastering/listen_delight_audit.json:"
        "mix:mix_seated:listen_delight_audit"
    )
    route = classify_heal_error(blob, ctx, stage="mix")
    assert route is not None
    assert route.family == "authority_denied"
    assert route.from_stage == "listen_delight_audit"
    assert route.from_stage != "mix"


def test_classify_never_repins_denied_writer_for_delight(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "deny_no_repin")
    init_run_meta_for_test(ctx)
    # Malformed / missing suggested — still must not land on mix.
    blob = "authority_denied:persist:mastering/listen_delight_audit.json:mix:mix_seated"
    route = classify_heal_error(blob, ctx, stage="mix")
    assert route is not None
    assert route.from_stage == "listen_delight_audit"
