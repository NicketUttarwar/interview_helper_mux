from __future__ import annotations

import importlib.util
from pathlib import Path

from interview_mux.prompt_validation import (
    ARTIFACT_WRITE_VALIDATORS,
    STAGE_ARTIFACT_DISK_PATHS,
    STAGE_ARTIFACT_SCHEMAS,
)

REPO = Path(__file__).resolve().parents[1]

# Binary / non-JSON stage outputs — write validators + Zod only apply to JSON.
_NON_JSON_DISK_PATHS = frozenset(
    path
    for path in STAGE_ARTIFACT_DISK_PATHS.values()
    if path.endswith((".wav", ".mp3"))
)


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
        if path not in ARTIFACT_WRITE_VALIDATORS and path not in _NON_JSON_DISK_PATHS
    ]
    # Paths registered for stage ownership without a dedicated JSON write validator
    # (research/ledger/plan aliases, WAV seats, etc.) are tracked here explicitly.
    allowed_missing = frozenset(
        {
            "understanding/ideal_cuts_materialized.json",
            "understanding/framing_posture_decision.json",
            "analysis/connector_seam_verdicts.json",
            "analysis/island_cluster_structure_verdicts.json",
            "analysis/low_conf_islands.json",
            "analysis/connector_fuse_audit.json",
            "analysis/connector_fuse_rounds.json",
            "vernacular/resplit_report.json",
            "mastering/vo_synthesize.json",
            "mastering/listen_delight_audit.json",
            "mastering/mastering_plan.json",
            "sound_design/music_palette_compose.json",
            "understanding/gap_framing_recompose.json",
            "understanding/selection_framing_apply.json",
            "understanding/interview_spine.json",
            "analysis/run_golden_facts.json",
            "mastering/shape/information_packages_audit.json",
            "publish/episode_meta.json",
            "publish/cover_prompt.json",
        }
    )
    unexpected = [p for p in missing if p not in allowed_missing]
    assert unexpected == [], f"STAGE_ARTIFACT_DISK_PATHS missing write validators: {unexpected}"


def test_stage_disk_paths_have_zod_schemas():
    zod_files = _load_zod_artifact_schema_files()
    missing = [
        path
        for path in STAGE_ARTIFACT_DISK_PATHS.values()
        if path not in zod_files and path not in _NON_JSON_DISK_PATHS
    ]
    allowed_missing = frozenset(
        {
            "understanding/talking_points.json",
            "understanding/ideal_cuts.json",
            "understanding/ideal_cuts_materialized.json",
            "understanding/framing_posture_decision.json",
            "analysis/connector_seam_verdicts.json",
            "analysis/island_cluster_structure_verdicts.json",
            "analysis/low_conf_islands.json",
            "analysis/connector_fuse_audit.json",
            "analysis/connector_fuse_rounds.json",
            "vernacular/resplit_report.json",
            "understanding/nugget_corpus.json",
            "understanding/vo_line_adjudication.json",
            "mastering/vo_synthesize.json",
            "mastering/listen_delight_audit.json",
            "mastering/mastering_plan.json",
            "sound_design/music_palette_compose.json",
            "master/seam_autopsy.json",
            "mastering/research/routing.json",
            "mastering/research/waves.json",
            "mastering/research/rollup.json",
            "mastering/shape/agenda.json",
            "mastering/shape/candidates.json",
            "understanding/delivery_brief.json",
            "understanding/soundscape_policy.json",
            "understanding/episode_structure.json",
            "understanding/gap_framing_recompose.json",
            "understanding/selection_framing_apply.json",
            "understanding/interview_spine.json",
            "analysis/run_golden_facts.json",
            "mastering/shape/information_packages_audit.json",
            "publish/episode_meta.json",
            "publish/cover_prompt.json",
        }
    )
    unexpected = [p for p in missing if p not in allowed_missing]
    assert unexpected == [], f"STAGE_ARTIFACT_DISK_PATHS missing Zod schemas: {unexpected}"


def test_sfx_prompt_refine_shares_craft_schema_and_disk_path():
    assert STAGE_ARTIFACT_SCHEMAS["sfx_prompt_refine"] == STAGE_ARTIFACT_SCHEMAS["sfx_prompt_craft"]
    assert STAGE_ARTIFACT_DISK_PATHS["sfx_prompt_craft"] == "sound_design/sfx_prompts.json"
