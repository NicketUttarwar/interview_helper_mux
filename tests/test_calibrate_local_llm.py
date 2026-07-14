"""Stage-1 calibrate_local_llm offline scorecard."""

from __future__ import annotations

import importlib.util

from interview_mux.config import repo_root
from interview_mux.local_capability_manifest import (
    degraded_manifest,
    validate_fixture_against_schema,
)
from interview_mux.local_llm_config import QUALITY_LOCAL_ALLOWLIST


def _load_calibrate_module():
    path = repo_root() / "scripts" / "calibrate_local_llm.py"
    spec = importlib.util.spec_from_file_location("calibrate_local_llm", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fixtures_validate_against_schemas():
    fixtures = repo_root() / "tests" / "fixtures" / "local_llm"
    pairs = [
        ("framer_ok.json", "local_framer_response.schema.json"),
        ("compressor_ok.json", "local_digest_compressor.schema.json"),
        ("escalate_advisory_ok.json", "local_escalate_advisory.schema.json"),
        ("shard_prep_ok.json", "local_shard_packet_prep.schema.json"),
        ("planner_ok.json", "local_capability_planner.schema.json"),
    ]
    for fname, schema in pairs:
        data = __import__("json").loads((fixtures / fname).read_text(encoding="utf-8"))
        errs = validate_fixture_against_schema(data, schema)
        assert not errs, f"{fname}: {errs}"


def test_offline_scorecard_and_manifest_shape():
    mod = _load_calibrate_module()
    scores = mod.run_offline_scorecard()
    assert scores["framer_verify_rate"] == 1.0
    assert scores["compressor_verify_rate"] == 1.0
    manifest = mod.build_manifest(dry_run=True)
    assert manifest["schema_version"] == 1
    assert "LX-01" in manifest["enabled_caps"]
    assert manifest["calibrate_status"] in ("ok", "warn")
    assert "LX-03" in manifest["enabled_caps"]  # compressor fixture ok + default context


def test_degraded_manifest():
    m = degraded_manifest(model_id="test-model", reason="unit")
    assert m["calibrate_status"] == "warn"
    assert m["enabled_caps"] == ["LX-01"]


def test_quality_allowlist_excludes_housekeeping():
    assert "ingest" not in QUALITY_LOCAL_ALLOWLIST
    assert "mmaudio_sfx" not in QUALITY_LOCAL_ALLOWLIST
    assert "speaker_roles" in QUALITY_LOCAL_ALLOWLIST
    assert "sfx_prompt_craft" in QUALITY_LOCAL_ALLOWLIST
