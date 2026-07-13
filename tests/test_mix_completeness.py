from __future__ import annotations

import pytest

from interview_mux.mix_completeness import enforce_mix_completeness
from run_fixtures import isolated_run_ctx


def test_enforce_mix_completeness_warn_mode(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_mix_warn")
    enforce_mix_completeness(
        ctx,
        flow="podcast",
        stage="mix",
        missing_vo=["line_001"],
    )


def test_enforce_mix_completeness_block_mode(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "run_mix_block")

    def fake_cfg():
        return {
            "mix": {
                "completeness_gate": {"enabled": True, "mode": "block"},
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
