"""GC-Q11 — operator_overrides on source acoustic profile."""

from __future__ import annotations

from fastapi.testclient import TestClient

from interview_mux.acoustic_profile import (
    apply_operator_overrides,
    load_profile,
    mix_contract,
    normalize_operator_overrides,
    save_operator_overrides,
)
from interview_mux.session_log import read_log
from interview_mux.web.server import create_app
from run_fixtures import init_run_meta_for_test, isolated_run_ctx, patch_server_ctx


def _write_profile(ctx, *, pace_class: str = "conversational", underscore_policy: str = "normal") -> None:
    ctx.write_json(
        "understanding/source_acoustic_profile.json",
        {
            "schema_version": 1,
            "derived_from": {
                "normalized_wav": "ingest/normalized.wav",
                "transcript": "transcript/full.json",
                "computed_at": "2026-05-29T12:00:00+00:00",
                "stage": "source_acoustic_profile",
            },
            "pacing": {"pace_class": pace_class, "global_wpm": 120, "wpm_by_quartile": [100, 110, 120, 130]},
            "energy": {"room_timbre_hint": "dry_close_mic"},
            "mix_contract": {"underscore_policy": underscore_policy},
            "prompt_tokens": {"bed": "test"},
            "placement_hints": {},
            "operator_overrides": {},
        },
    )


def test_normalize_flat_override_keys() -> None:
    assert normalize_operator_overrides(
        {"pace_class": "dense", "underscore_policy": "skip"}
    ) == {
        "pacing": {"pace_class": "dense"},
        "mix_contract": {"underscore_policy": "skip"},
    }


def test_apply_operator_overrides_merges_nested_fields() -> None:
    raw = {
        "pacing": {"pace_class": "calm", "global_wpm": 90},
        "mix_contract": {"underscore_policy": "normal"},
        "operator_overrides": {
            "pacing": {"pace_class": "brisk"},
            "mix_contract": {"underscore_policy": "sparse"},
        },
    }
    merged = apply_operator_overrides(raw)
    assert merged["pacing"]["pace_class"] == "brisk"
    assert merged["pacing"]["global_wpm"] == 90
    assert merged["mix_contract"]["underscore_policy"] == "sparse"


def test_load_profile_returns_merged_view(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_sap_merge")
    _write_profile(ctx, pace_class="calm")
    save_operator_overrides(ctx, {"pace_class": "dense", "underscore_policy": "skip"})
    profile = load_profile(ctx)
    assert profile is not None
    assert profile["pacing"]["pace_class"] == "dense"
    assert profile["mix_contract"]["underscore_policy"] == "skip"
    on_disk = ctx.read_json("understanding/source_acoustic_profile.json")
    assert on_disk["pacing"]["pace_class"] == "calm"
    assert on_disk["operator_overrides"]["pacing"]["pace_class"] == "dense"


def test_mix_contract_uses_overrides(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_sap_mix")
    _write_profile(ctx, underscore_policy="normal")
    save_operator_overrides(ctx, {"underscore_policy": "skip"})
    contract = mix_contract(ctx)
    assert contract["underscore_policy"] == "skip"


def test_patch_overrides_api_and_log(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_sap_api")
    init_run_meta_for_test(ctx)
    _write_profile(ctx)
    patch_server_ctx(monkeypatch, ctx)

    client = TestClient(create_app())
    res = client.patch(
        f"/api/runs/{ctx.run_id}/acoustic-profile/overrides",
        json={"overrides": {"pace_class": "brisk", "underscore_policy": "sparse"}},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["effective"]["pace_class"] == "brisk"
    assert body["effective"]["underscore_policy"] == "sparse"

    profile = load_profile(ctx)
    assert profile["pacing"]["pace_class"] == "brisk"

    logs = [e for e in read_log(ctx.run_dir) if e.get("detail") == "acoustic_profile_override_saved"]
    assert len(logs) == 1


def test_patch_rejects_invalid_pace_class(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_sap_bad")
    _write_profile(ctx)
    patch_server_ctx(monkeypatch, ctx)

    res = TestClient(create_app()).patch(
        f"/api/runs/{ctx.run_id}/acoustic-profile/overrides",
        json={"overrides": {"pace_class": "turbo"}},
    )
    assert res.status_code == 400


def test_clear_overrides_via_api(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_sap_clear")
    _write_profile(ctx, pace_class="calm")
    save_operator_overrides(ctx, {"pace_class": "dense"})
    patch_server_ctx(monkeypatch, ctx)

    res = TestClient(create_app()).patch(
        f"/api/runs/{ctx.run_id}/acoustic-profile/overrides",
        json={"overrides": {}},
    )
    assert res.status_code == 200
    profile = load_profile(ctx)
    assert profile["pacing"]["pace_class"] == "calm"
