from __future__ import annotations

import importlib.util
from pathlib import Path

from interview_mux.prompt_validation import (
    ARTIFACT_WRITE_VALIDATORS,
    STAGE_ARTIFACT_DISK_PATHS,
    STAGE_ARTIFACT_SCHEMAS,
)

REPO = Path(__file__).resolve().parents[1]


def _load_zod_artifact_schema_files() -> dict[str, str]:
    spec = importlib.util.spec_from_file_location(
        "codegen_zod_schemas",
        REPO / "tools" / "codegen_zod_schemas.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ARTIFACT_SCHEMA_FILES


def test_stage_disk_paths_have_write_validators():
    missing = [
        path
        for path in STAGE_ARTIFACT_DISK_PATHS.values()
        if path not in ARTIFACT_WRITE_VALIDATORS
    ]
    assert missing == [], f"STAGE_ARTIFACT_DISK_PATHS missing write validators: {missing}"


def test_stage_disk_paths_have_zod_schemas():
    zod_files = _load_zod_artifact_schema_files()
    missing = [
        path
        for path in STAGE_ARTIFACT_DISK_PATHS.values()
        if path not in zod_files
    ]
    assert missing == [], f"STAGE_ARTIFACT_DISK_PATHS missing Zod schemas: {missing}"


def test_sfx_prompt_refine_shares_craft_schema_and_disk_path():
    assert STAGE_ARTIFACT_SCHEMAS["sfx_prompt_refine"] == STAGE_ARTIFACT_SCHEMAS["sfx_prompt_craft"]
    assert STAGE_ARTIFACT_DISK_PATHS["sfx_prompt_craft"] == "sound_design/sfx_prompts.json"
