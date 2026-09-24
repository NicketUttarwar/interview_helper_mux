"""Real-execution regression: Cluster D / i9 EDL survivors after orientation.

Uses the previous Mohan full-auto tape ``exec_13183_d19c15b58ab4_20260924T001619Z``
(and the committed fixture slice derived from it) to prove that:

1. Rebuilding EDL from the real gap + selection + segments still seats
   orientation **and** both later nugget_layup lines (``vo_layup_seg_007``,
   ``vo_layup_seg_037``) after opening VO — the wipe that caused ``phantom_vo``.
2. The reconstituted bug-state EDL (layup seats stripped, WAVs on disk) is
   detected as ``edl_survivor_wipe`` / ``vo_audibility_drift`` at ``pre_mix``.
3. Rebuilding clears phantoms; missing ``assembly_ledger`` is auto-restored on
   the sanitary path (the heal blocker from forensics).
4. Heal classification for the real forensics fingerprint pins ``edl`` rebuild,
   not remint / narrative audit.

pytest normally sandboxes ``ASSETS/executions``. Mark
``real_executions_root`` so live WAV bytes can be copied when present.
"""

from __future__ import annotations

import json
import os
import shutil
import wave
from pathlib import Path
from typing import Any

import pytest

os.environ["MUX_FORENSICS"] = "0"

from interview_mux.artifact_sanitize.edl import LEDGER_REL, edl_sanitary_errors
from interview_mux.heal_routing import classify_heal_error
from interview_mux.nle_state import segments_by_id_with_nle
from interview_mux.publishability_boundary import validate_publishability
from interview_mux.run_context import RunContext
from interview_mux.stages.assembly import build_flow1_edl
from run_fixtures import init_run_meta_for_test, isolated_run_ctx, write_fixture_vo_wav

REPO_ROOT = Path(__file__).resolve().parents[1]
EXECUTIONS_ROOT = REPO_ROOT / "ASSETS" / "executions"
SOURCE_RUN_ID = "exec_13183_d19c15b58ab4_20260924T001619Z"
SOURCE_RUN = EXECUTIONS_ROOT / SOURCE_RUN_ID
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "exec_13183_i9_edl_survivors"

EXPECTED_LINE_IDS = (
    "vo_preface_episode_orientation",
    "vo_layup_seg_007",
    "vo_layup_seg_037",
)
LAYUP_LINE_IDS = ("vo_layup_seg_007", "vo_layup_seg_037")

pytestmark = pytest.mark.real_executions_root


def _require_fixture_package() -> Path:
    required = (
        "gap_report.json",
        "selection.json",
        "segments_manifest.json",
        "edl_seated.json",
        "edl_wiped_phantoms.json",
        "forensics_excerpt.json",
    )
    missing = [name for name in required if not (FIXTURE_DIR / name).is_file()]
    if missing:
        pytest.fail(
            f"i9 fixture package incomplete under {FIXTURE_DIR}: missing {missing}. "
            "Regenerate from ASSETS/executions/exec_13183_… (see fixture README)."
        )
    excerpt = json.loads((FIXTURE_DIR / "forensics_excerpt.json").read_text(encoding="utf-8"))
    assert excerpt.get("source_run") == SOURCE_RUN_ID
    assert list(excerpt.get("expected_line_ids") or []) == list(EXPECTED_LINE_IDS)
    return FIXTURE_DIR


def _wav_duration_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as wf:
        rate = float(wf.getframerate() or 1)
        return max(1, int(wf.getnframes() / rate * 1000))


def _install_wavs(ctx: RunContext) -> dict[str, str]:
    """Prefer live exec_13183 synth WAVs; else mint stand-ins with the same names."""
    provenance: dict[str, str] = {}
    dest_dir = ctx.path("vo_pickup", "synthesized")
    dest_dir.mkdir(parents=True, exist_ok=True)
    live_dir = SOURCE_RUN / "vo_pickup" / "synthesized"
    for lid in EXPECTED_LINE_IDS:
        dest = dest_dir / f"{lid}.wav"
        live = live_dir / f"{lid}.wav"
        if live.is_file() and live.stat().st_size > 1000:
            shutil.copy2(live, dest)
            provenance[lid] = f"live:{live}"
        else:
            write_fixture_vo_wav(dest, duration_sec=0.8)
            provenance[lid] = f"standin:{dest}"
    return provenance


def _clone_real_world_ctx(tmp_path: Path, *, wiped_edl: bool = False) -> RunContext:
    """Build an isolated run dir with accurate exec_13183 inputs for EDL rebuild."""
    fixture = _require_fixture_package()
    ctx = isolated_run_ctx(tmp_path, f"i9_real_{'wiped' if wiped_edl else 'rebuild'}")
    init_run_meta_for_test(ctx)

    gap = json.loads((fixture / "gap_report.json").read_text(encoding="utf-8"))
    selection = json.loads((fixture / "selection.json").read_text(encoding="utf-8"))
    segments_doc = json.loads(
        (fixture / "segments_manifest.json").read_text(encoding="utf-8")
    )
    edl_name = "edl_wiped_phantoms.json" if wiped_edl else "edl_seated.json"
    edl = json.loads((fixture / edl_name).read_text(encoding="utf-8"))

    ctx.write_json("understanding/gap_report.json", gap)
    ctx.write_json("master/selection.json", selection)
    ctx.write_json("segments/manifest.json", {"segments": segments_doc.get("segments") or []})
    ctx.write_json("master/edl.json", edl)

    provenance = _install_wavs(ctx)
    ctx.write_json(
        "operator/i9_fixture_provenance.json",
        {
            "source_run": SOURCE_RUN_ID,
            "fixture_dir": str(fixture),
            "wav_provenance": provenance,
            "live_run_present": SOURCE_RUN.is_dir(),
            "wiped_edl": wiped_edl,
        },
    )

    # Sufficiency gate: every expected line must exist in gap + have a WAV.
    lines = {
        str(ln.get("line_id") or ""): ln
        for ln in (gap.get("interviewer_lines") or [])
        if isinstance(ln, dict)
    }
    for lid in EXPECTED_LINE_IDS:
        assert lid in lines, f"gap_report missing {lid}"
        assert not lines[lid].get("skipped_optional")
        assert not lines[lid].get("air_script_omit")
        wav = ctx.path("vo_pickup", "synthesized", f"{lid}.wav")
        assert wav.is_file() and wav.stat().st_size > 44, f"WAV missing/empty for {lid}"

    ordered = list(selection.get("ordered_segment_ids") or [])
    assert ordered, "selection.ordered_segment_ids empty"
    by_id = segments_by_id_with_nle(ctx)
    missing_segs = [sid for sid in ordered if sid not in by_id]
    assert not missing_segs, f"segments/manifest incomplete for ordered keeps: {missing_segs}"

    return ctx


def _rebuild_edl(ctx: RunContext) -> dict[str, Any]:
    selection = ctx.read_json("master/selection.json")
    gap = ctx.read_json("understanding/gap_report.json")
    by_id = segments_by_id_with_nle(ctx)

    def resolve(line: dict) -> Path | None:
        lid = str(line.get("line_id") or "")
        path = ctx.path("vo_pickup", "synthesized", f"{lid}.wav")
        return path if path.is_file() else None

    return build_flow1_edl(
        selection=selection if isinstance(selection, dict) else {},
        segments_by_id=by_id,
        gap_report=gap if isinstance(gap, dict) else None,
        resolve_vo_path=resolve,
        vo_duration_ms=_wav_duration_ms,
        vo_relpath=lambda p: f"vo_pickup/synthesized/{p.name}",
        ctx=ctx,
    )


def _vo_line_ids(edl: dict[str, Any]) -> list[str]:
    return [
        str(c.get("line_id") or "")
        for c in (edl.get("clips") or [])
        if isinstance(c, dict) and c.get("type") == "vo_pickup" and c.get("line_id")
    ]


def test_i9_fixture_package_is_complete_and_matches_forensics() -> None:
    fixture = _require_fixture_package()
    gap = json.loads((fixture / "gap_report.json").read_text(encoding="utf-8"))
    lines = gap.get("interviewer_lines") or []
    ids = [str(ln.get("line_id") or "") for ln in lines if isinstance(ln, dict)]
    assert ids == list(EXPECTED_LINE_IDS)

    orient = lines[0]
    assert orient.get("episode_orientation") is True
    assert orient.get("targets_segment_id") == "seg_002"

    for ln in lines[1:]:
        assert ln.get("origin") == "nugget_layup"
        assert ln.get("delivery") == "synthesize"
        assert ln.get("placement") == "before"

    wiped = json.loads((fixture / "edl_wiped_phantoms.json").read_text(encoding="utf-8"))
    seated = json.loads((fixture / "edl_seated.json").read_text(encoding="utf-8"))
    assert set(wiped.get("_stripped_line_ids") or []) == set(LAYUP_LINE_IDS)
    seated_ids = set(_vo_line_ids(seated))
    wiped_ids = set(_vo_line_ids(wiped))
    assert set(EXPECTED_LINE_IDS).issubset(seated_ids)
    assert "vo_preface_episode_orientation" in wiped_ids
    assert not set(LAYUP_LINE_IDS) & wiped_ids


def test_i9_real_exec_sufficiency_report(tmp_path: Path) -> None:
    """Document whether live ASSETS bytes are available; still clone from fixtures."""
    ctx = _clone_real_world_ctx(tmp_path, wiped_edl=False)
    prov = ctx.read_json("operator/i9_fixture_provenance.json")
    assert prov.get("source_run") == SOURCE_RUN_ID
    assert ctx.artifact_exists("understanding/gap_report.json")
    assert ctx.artifact_exists("master/selection.json")
    assert ctx.artifact_exists("segments/manifest.json")
    assert ctx.artifact_exists("master/edl.json")
    live_wavs = sum(
        1 for v in (prov.get("wav_provenance") or {}).values() if str(v).startswith("live:")
    )
    # Soft report — seating tests must pass either way; prefer live when present.
    assert live_wavs in {0, 3}
    if SOURCE_RUN.is_dir() and live_wavs != 3:
        pytest.fail(
            f"{SOURCE_RUN} exists but live synth WAVs were not copied "
            f"(provenance={prov.get('wav_provenance')}). Fixture WAV paths incomplete."
        )


def test_i9_rebuild_from_real_gap_seats_orientation_and_both_layups(
    tmp_path: Path,
) -> None:
    """Core real-world fix: post-orientation stacking must not wipe layup seats."""
    ctx = _clone_real_world_ctx(tmp_path, wiped_edl=False)
    edl = _rebuild_edl(ctx)
    vo_ids = _vo_line_ids(edl)
    for lid in EXPECTED_LINE_IDS:
        assert lid in vo_ids, f"{lid} missing after rebuild; got {vo_ids}"

    # Orientation must precede later layups on the timeline.
    starts = {
        str(c.get("line_id")): int(c.get("timeline_start_ms") or 0)
        for c in (edl.get("clips") or [])
        if isinstance(c, dict) and c.get("type") == "vo_pickup"
    }
    assert starts["vo_preface_episode_orientation"] < starts["vo_layup_seg_007"]
    assert starts["vo_layup_seg_007"] < starts["vo_layup_seg_037"]


def test_i9_wiped_edl_matches_forensics_phantom_then_rebuild_clears(
    tmp_path: Path,
) -> None:
    """Reconstitute the exact pre_mix failure, then prove rebuild heals it."""
    ctx = _clone_real_world_ctx(tmp_path, wiped_edl=True)

    # Bug state: WAVs on disk, layups absent from EDL.
    report = validate_publishability(ctx, checkpoint="pre_mix")
    assert not report.ok
    wipe_by_line = {
        v.line_id: v
        for v in report.violations
        if v.line_id and v.code in {"edl_survivor_wipe", "phantom_vo"}
    }
    for lid in LAYUP_LINE_IDS:
        assert lid in wipe_by_line, (
            f"expected phantom/survivor wipe for {lid}; "
            f"got {[(v.code, v.line_id, v.error_class) for v in report.violations]}"
        )
        v = wipe_by_line[lid]
        assert v.error_class == "vo_audibility_drift"
        assert v.code == "edl_survivor_wipe"
        assert "rebuild edl" in v.detail.lower() or "do not remint" in v.detail.lower()

    # Heal fingerprint from the real forensics tape must pin edl.
    excerpt = json.loads(
        (FIXTURE_DIR / "forensics_excerpt.json").read_text(encoding="utf-8")
    )
    fingerprint = str(excerpt["fingerprints"][0]["detail"])
    route = classify_heal_error(fingerprint, ctx, stage="mix")
    assert route is not None
    assert route.family == "vo_audibility_drift"
    assert route.from_stage == "edl"
    assert "rebuild" in route.action

    survivor_route = classify_heal_error(
        wipe_by_line["vo_layup_seg_007"].detail, ctx, stage="mix"
    )
    assert survivor_route is not None
    assert survivor_route.from_stage == "edl"
    assert survivor_route.action == "rebuild_edl"

    # Rebuild with current survivor SSOT → phantoms gone.
    fixed = _rebuild_edl(ctx)
    ctx.write_json("master/edl.json", fixed)
    assert set(LAYUP_LINE_IDS).issubset(set(_vo_line_ids(fixed)))

    report2 = validate_publishability(ctx, checkpoint="pre_mix")
    phantoms = [
        v
        for v in report2.violations
        if v.code in {"phantom_vo", "edl_survivor_wipe"}
        and v.line_id in LAYUP_LINE_IDS
    ]
    assert phantoms == [], [(v.code, v.line_id, v.detail) for v in phantoms]


def test_i9_missing_ledger_no_longer_blocks_sanitary_on_real_edl(
    tmp_path: Path,
) -> None:
    """Forensics: edl_unsanitary missing assembly_ledger blocked heal rebuild."""
    ctx = _clone_real_world_ctx(tmp_path, wiped_edl=False)
    # Ensure EDL present without ledger (the stuck heal state).
    if ctx.artifact_exists(LEDGER_REL):
        (ctx.run_dir / LEDGER_REL).unlink()
    assert not ctx.artifact_exists(LEDGER_REL)

    errs = edl_sanitary_errors(ctx)
    joined = " ".join(errs)
    assert "assembly_ledger" not in joined, errs
    assert ctx.artifact_exists(LEDGER_REL)


def test_i9_live_exec_seated_edl_has_no_layup_phantoms(tmp_path: Path) -> None:
    """If the prior ship EDL is present, it must already seat both layups (post-fix)."""
    ctx = _clone_real_world_ctx(tmp_path, wiped_edl=False)
    edl = ctx.read_json("master/edl.json")
    assert isinstance(edl, dict)
    assert set(EXPECTED_LINE_IDS).issubset(set(_vo_line_ids(edl)))
    report = validate_publishability(ctx, checkpoint="pre_mix")
    phantoms = [
        v
        for v in report.violations
        if v.code in {"phantom_vo", "edl_survivor_wipe"}
        and v.line_id in EXPECTED_LINE_IDS
    ]
    assert phantoms == [], [(v.code, v.line_id, v.detail) for v in phantoms]


def test_i9_prefer_live_assets_bytes_when_campaign_tree_present() -> None:
    """Guard: when ASSETS still holds exec_13183, required tape files must exist."""
    if not SOURCE_RUN.is_dir():
        pytest.skip(f"live run absent: {SOURCE_RUN}")
    required = [
        "understanding/gap_report.json",
        "master/selection.json",
        "master/edl.json",
        "segments/manifest.json",
        "vo_pickup/synthesized/vo_preface_episode_orientation.wav",
        "vo_pickup/synthesized/vo_layup_seg_007.wav",
        "vo_pickup/synthesized/vo_layup_seg_037.wav",
        "operator/forensics_errors.json",
    ]
    missing = [rel for rel in required if not (SOURCE_RUN / rel).is_file()]
    assert not missing, f"live exec_13183 incomplete for i9 real-world tests: {missing}"

    # Fixture gap must match live gap line ids (drift detector).
    live_gap = json.loads(
        (SOURCE_RUN / "understanding/gap_report.json").read_text(encoding="utf-8")
    )
    fixture_gap = json.loads((FIXTURE_DIR / "gap_report.json").read_text(encoding="utf-8"))
    live_ids = [
        str(ln.get("line_id") or "")
        for ln in (live_gap.get("interviewer_lines") or [])
        if isinstance(ln, dict)
    ]
    fixture_ids = [
        str(ln.get("line_id") or "")
        for ln in (fixture_gap.get("interviewer_lines") or [])
        if isinstance(ln, dict)
    ]
    assert live_ids == fixture_ids == list(EXPECTED_LINE_IDS)
