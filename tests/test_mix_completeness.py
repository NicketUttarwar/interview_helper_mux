from __future__ import annotations

import pytest

from interview_mux.mix_completeness import enforce_mix_completeness
from run_fixtures import isolated_run_ctx


def test_enforce_mix_completeness_warn_mode(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "run_mix_warn")
    monkeypatch.setattr("interview_mux.first_try.first_try_mode_enabled", lambda cfg=None: False)

    def fake_cfg():
        return {
            "mix": {
                "completeness_gate": {
                    "enabled": True,
                    "mode": "warn",
                    "hard_fail_missing_blocking_vo": True,
                },
            }
        }

    monkeypatch.setattr("interview_mux.mix_completeness.merged_config", fake_cfg)
    enforce_mix_completeness(
        ctx,
        flow="podcast",
        stage="mix",
        missing_vo=["line_001"],
    )


def test_enforce_mix_completeness_block_mode(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "run_mix_block")
    monkeypatch.setattr("interview_mux.first_try.first_try_mode_enabled", lambda cfg=None: False)
    monkeypatch.setattr("interview_mux.first_try.allow_placeholder_mix", lambda cfg=None: False)

    def fake_cfg():
        return {
            "mix": {
                "completeness_gate": {
                    "enabled": True,
                    "mode": "block",
                    "soft_fail_sfx_placeholder": False,
                },
            }
        }

    monkeypatch.setattr("interview_mux.mix_completeness.merged_config", fake_cfg)
    with pytest.raises(RuntimeError, match="missing mix assets"):
        enforce_mix_completeness(
            ctx,
            flow="podcast",
            stage="mix",
            missing_sfx=["stinger_intro"],
        )
