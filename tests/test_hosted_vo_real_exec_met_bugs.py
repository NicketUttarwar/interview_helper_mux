"""Targeted real-execution tests for hosted VO SSOT (Cluster C).

Uses previous ``ASSETS/executions`` snapshots where the hosted VO floor is **not**
hollow and **not** low (``have >= need`` → ``MET``). Exercises the live
authority against real artifacts to surface residual bugs (stale aspirational
stamps, HEARD_KEEP remint thrash) without a full pipeline run.

Important: pytest autouse redirects ``executions_root`` to a sandbox. These tests
bind ``ctx.run_dir`` to the absolute prior-exec path (or a tmp clone of that
slice) so they actually read the previous files.

Sufficiency is reported by ``test_real_exec_hosted_vo_sufficiency_report``.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

os.environ["MUX_FORENSICS"] = "0"

from interview_mux.gap_fill_eligibility import synthetic_vo_incompleteness
from interview_mux.hosted_vo_authority import (
    ORIENTATION_LINE_ID,
    assert_books_agree,
    decide_orientation,
    floor_snapshot,
    have,
    have_edl,
    have_gap,
    identify_hosted_vo_floor,
    may_aspirational_proceed,
    need,
    reconcile_escalations,
)
from interview_mux.opening_orientation import ensure_episode_orientation
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import _gap_framing_compose_hosted_floor_incompleteness
from run_fixtures import isolated_run_ctx

REPO_ROOT = Path(__file__).resolve().parents[1]
EXECUTIONS_ROOT = REPO_ROOT / "ASSETS" / "executions"

# pytest normally sandboxes ASSETS/executions — opt out so probes can resolve.
pytestmark = pytest.mark.real_executions_root

CANDIDATE_RUN_IDS = (
    "exec_13183_d19c15b58ab4_20260924T001619Z",  # Cluster C dig
    "exec_13181_d19c15b58ab4_20260923T185720Z",
    "exec_13177_d19c15b58ab4_20260923T001031Z",
    "exec_13170_d19c15b58ab4_20260922T004948Z",
)

# Slice must include topology or hosted floor is UNWARRANTED (no floor law).
_SLICE_RELS = (
    "understanding/gap_report.json",
    "understanding/source_topology.json",
    "understanding/nugget_layup_plan.json",
    "master/edl.json",
    "master/selection.json",
    "run_meta.json",
    f"vo_pickup/synthesized/{ORIENTATION_LINE_ID}.wav",
    "operator/escalations/nugget_layup_compose.json",
)


@dataclass(frozen=True)
class ExecFloorProbe:
    run_id: str
    path: Path
    have: int
    need: int
    status: str
    gap: int
    edl: int
    has_gap: bool
    has_edl: bool
    has_orient_wav: bool
    has_topology: bool
    warranted: bool
    sufficient_met: bool
    missing: tuple[str, ...]
    note: str = ""


def _bind_live(run_id: str) -> RunContext | None:
    """RunContext pointed at the absolute prior-exec directory (read-only)."""
    path = EXECUTIONS_ROOT / run_id
    if not path.is_dir():
        return None
    ctx = RunContext(run_id, create=False)
    ctx.run_dir = path
    return ctx


def _probe_live(run_id: str) -> ExecFloorProbe | None:
    path = EXECUTIONS_ROOT / run_id
    if not path.is_dir():
        return None
    missing: list[str] = []
    for rel in (
        "understanding/gap_report.json",
        "understanding/source_topology.json",
        "run_meta.json",
        "master/edl.json",
    ):
        if not (path / rel).is_file():
            missing.append(rel)
    has_gap = (path / "understanding/gap_report.json").is_file()
    has_edl = (path / "master/edl.json").is_file()
    has_wav = (path / "vo_pickup/synthesized" / f"{ORIENTATION_LINE_ID}.wav").is_file()
    has_topo = (path / "understanding/source_topology.json").is_file()
    if not has_gap:
        return ExecFloorProbe(
            run_id=run_id,
            path=path,
            have=0,
            need=0,
            status="NO_GAP",
            gap=0,
            edl=0,
            has_gap=False,
            has_edl=has_edl,
            has_orient_wav=has_wav,
            has_topology=has_topo,
            warranted=False,
            sufficient_met=False,
            missing=tuple(missing),
            note="gap_report missing",
        )
    ctx = _bind_live(run_id)
    assert ctx is not None
    try:
        from interview_mux.gap_fill_eligibility import hosted_framing_requires_synthetic_vo

        warranted = bool(hosted_framing_requires_synthetic_vo(ctx))
        ident = identify_hosted_vo_floor(ctx, persist=False)
        sufficient = (
            ident.status == "MET"
            and int(ident.have) >= 1
            and int(ident.have) >= int(ident.need)
            and has_edl
            and has_topo
            and warranted
        )
        return ExecFloorProbe(
            run_id=run_id,
            path=path,
            have=int(ident.have),
            need=int(ident.need),
            status=str(ident.status),
            gap=int(ident.have_gap),
            edl=int(ident.have_edl),
            has_gap=True,
            has_edl=has_edl,
            has_orient_wav=has_wav,
            has_topology=has_topo,
            warranted=warranted,
            sufficient_met=sufficient,
            missing=tuple(missing),
            note=ident.prose,
        )
    except Exception as exc:
        return ExecFloorProbe(
            run_id=run_id,
            path=path,
            have=0,
            need=0,
            status=f"ERROR:{type(exc).__name__}",
            gap=0,
            edl=0,
            has_gap=has_gap,
            has_edl=has_edl,
            has_orient_wav=has_wav,
            has_topology=has_topo,
            warranted=False,
            sufficient_met=False,
            missing=tuple(missing) + (str(exc),),
            note=str(exc),
        )


def _met_probes() -> list[ExecFloorProbe]:
    if not EXECUTIONS_ROOT.is_dir():
        return []
    return [p for rid in CANDIDATE_RUN_IDS if (p := _probe_live(rid)) and p.sufficient_met]


def _require_met_runs() -> list[ExecFloorProbe]:
    if not EXECUTIONS_ROOT.is_dir():
        pytest.skip(f"ASSETS executions root missing: {EXECUTIONS_ROOT}")
    mets = _met_probes()
    if not mets:
        inventory = []
        for rid in CANDIDATE_RUN_IDS:
            p = _probe_live(rid)
            if p is None:
                inventory.append(f"{rid}=ABSENT")
            else:
                inventory.append(
                    f"{rid}=status:{p.status} have:{p.have} need:{p.need} "
                    f"warranted:{p.warranted} topo:{p.has_topology} edl:{p.has_edl} "
                    f"wav:{p.has_orient_wav} missing={list(p.missing)}"
                )
        pytest.skip(
            "No MET (have≥need, have≥1, warranted, EDL+topology) candidate executions. "
            "Previous files insufficient for non-hollow/non-low hosted VO tests. "
            + "; ".join(inventory)
        )
    return mets


def _clone_slice(tmp_path: Path, src: Path, run_id: str) -> RunContext:
    """Copy a slice into tmp so apply/ensure cannot mutate ASSETS."""
    ctx = isolated_run_ctx(tmp_path, run_id)
    for rel in _SLICE_RELS:
        sp = src / rel
        if not sp.exists():
            continue
        dp = ctx.run_dir / rel
        dp.parent.mkdir(parents=True, exist_ok=True)
        if sp.is_file():
            shutil.copy2(sp, dp)
    # Sanity: warrant must survive the clone or the test is invalid.
    from interview_mux.gap_fill_eligibility import hosted_framing_requires_synthetic_vo

    if not hosted_framing_requires_synthetic_vo(ctx):
        pytest.fail(
            f"clone of {run_id} lost hosted floor warrant — expand _SLICE_RELS "
            f"(need source_topology + gap_framing_enabled meta). "
            f"topo={ctx.artifact_exists('understanding/source_topology.json')} "
            f"meta_gap={((ctx.read_json('run_meta.json') or {}).get('gap_framing_enabled') if ctx.artifact_exists('run_meta.json') else None)}"
        )
    return ctx


def _ordered_ids(ctx: RunContext) -> list[str]:
    if not ctx.artifact_exists("master/selection.json"):
        return ["seg_002"]
    sel = ctx.read_json("master/selection.json")
    ids = [str(x) for x in ((sel or {}).get("ordered_segment_ids") or []) if x]
    return ids or ["seg_002"]


_METS_AT_IMPORT = _met_probes()
_PARAM_METS = _METS_AT_IMPORT or [
    ExecFloorProbe(
        run_id="_none_",
        path=Path("."),
        have=0,
        need=0,
        status="NONE",
        gap=0,
        edl=0,
        has_gap=False,
        has_edl=False,
        has_orient_wav=False,
        has_topology=False,
        warranted=False,
        sufficient_met=False,
        missing=(),
        note="placeholder — skipped at runtime",
    )
]


# ---------------------------------------------------------------------------
# Sufficiency
# ---------------------------------------------------------------------------


def test_real_exec_hosted_vo_sufficiency_report() -> None:
    """Inventory whether previous executions can support MET-floor SSOT tests."""
    if not EXECUTIONS_ROOT.is_dir():
        pytest.fail(
            f"ASSETS/executions missing at {EXECUTIONS_ROOT} — cannot use prior runs."
        )
    rows: list[str] = []
    met = 0
    for rid in CANDIDATE_RUN_IDS:
        p = _probe_live(rid)
        if p is None:
            rows.append(f"{rid}: ABSENT")
            continue
        flag = "MET-OK" if p.sufficient_met else "INSUFFICIENT"
        if p.sufficient_met:
            met += 1
        rows.append(
            f"{rid}: {flag} status={p.status} have={p.have} need={p.need} "
            f"warranted={p.warranted} gap={p.gap} edl={p.edl} "
            f"topo={p.has_topology} wav={p.has_orient_wav} "
            f"missing={list(p.missing)} note={p.note!r}"
        )
    report = "\n".join(rows)
    assert met >= 1, (
        "Previous execution files are NOT sufficient: need ≥1 run with "
        "hosted VO MET (have≥need, have≥1, warranted, EDL+topology).\n" + report
    )
    assert any("exec_13183" in r and "MET-OK" in r for r in rows), (
        "exec_13183 should be MET with non-zero/non-low floor after dig freeze.\n"
        + report
    )


# ---------------------------------------------------------------------------
# Healthy-floor invariants (count not low / not zero)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("probe", _PARAM_METS, ids=lambda p: p.run_id)
def test_real_exec_met_floor_identity_not_hollow_or_partial(
    tmp_path: Path, probe: ExecFloorProbe
) -> None:
    if not probe.sufficient_met:
        _require_met_runs()
        pytest.skip("no MET probes at collection")
    ctx = _clone_slice(tmp_path, probe.path, probe.run_id)
    ident = identify_hosted_vo_floor(ctx, persist=False)
    assert ident.have >= 1, f"{probe.run_id}: have must not be zero"
    assert ident.have >= ident.need, (
        f"{probe.run_id}: have must not be low (have={ident.have} need={ident.need})"
    )
    assert ident.status == "MET"
    assert have(ctx) == ident.have
    assert have_gap(ctx) == ident.have_gap
    assert have_edl(ctx) == ident.have_edl
    assert need(ctx) == ident.need


@pytest.mark.parametrize("probe", _PARAM_METS, ids=lambda p: p.run_id)
def test_real_exec_met_floor_no_incompleteness_or_aspirational(
    tmp_path: Path, probe: ExecFloorProbe
) -> None:
    if not probe.sufficient_met:
        _require_met_runs()
        pytest.skip("no MET probes at collection")
    ctx = _clone_slice(tmp_path, probe.path, probe.run_id)
    assert identify_hosted_vo_floor(ctx, persist=False).status == "MET"
    assert not may_aspirational_proceed(ctx)
    snap = floor_snapshot(ctx, persist=False)
    assert snap.aspirational_ok is False
    assert snap.escalation_should_block is False
    assert synthetic_vo_incompleteness(ctx, "nugget_layup_compose") is None
    assert _gap_framing_compose_hosted_floor_incompleteness(ctx) is None


@pytest.mark.parametrize("probe", _PARAM_METS, ids=lambda p: p.run_id)
def test_real_exec_met_floor_books_agree(tmp_path: Path, probe: ExecFloorProbe) -> None:
    if not probe.sufficient_met:
        _require_met_runs()
        pytest.skip("no MET probes at collection")
    ctx = _clone_slice(tmp_path, probe.path, probe.run_id)
    errs = assert_books_agree(ctx)
    assert errs == [], f"{probe.run_id}: books disagree while MET: {errs}"


@pytest.mark.parametrize("probe", _PARAM_METS, ids=lambda p: p.run_id)
def test_real_exec_ensure_orientation_does_not_drop_have(
    tmp_path: Path, probe: ExecFloorProbe
) -> None:
    if not probe.sufficient_met:
        _require_met_runs()
        pytest.skip("no MET probes at collection")
    ctx = _clone_slice(tmp_path, probe.path, probe.run_id)
    before = identify_hosted_vo_floor(ctx, persist=False)
    assert before.have >= before.need >= 1
    gap = ctx.read_json("understanding/gap_report.json")
    out, actions = ensure_episode_orientation(ctx, gap, _ordered_ids(ctx))
    # Prefer persist, but hard-freeze ownership may deny writes on older runs —
    # still validate the returned gap document so we do not mutate ASSETS.
    try:
        ctx.write_json("understanding/gap_report.json", out)
        after = identify_hosted_vo_floor(ctx, persist=False)
        after_have = after.have
        after_status = after.status
    except Exception as exc:
        # Hard-freeze ownership may deny writes on older sealed runs — validate
        # the returned gap document instead of mutating ASSETS.
        active = 0
        for ln in out.get("interviewer_lines") or []:
            if not isinstance(ln, dict):
                continue
            if ln.get("skipped_optional") or ln.get("air_script_omit"):
                continue
            if not str(ln.get("text") or "").strip():
                continue
            delivery = str(ln.get("delivery") or "synthesize").lower()
            if delivery in {"synthesize", "chatterbox", "record", "mlx_audio", ""}:
                active += 1
        after_have = active
        after_status = "MET" if active >= before.need else ("PARTIAL" if active >= 1 else "HOLLOW_ZERO")
        assert active >= before.need, (
            f"{probe.run_id}: ensure returned hollow/low gap active={active} "
            f"(before have={before.have} need={before.need}); "
            f"persist denied ({type(exc).__name__}: {exc}); actions={actions}"
        )
    assert after_have >= before.need, (
        f"{probe.run_id}: ensure dropped floor have {before.have}→{after_have} "
        f"(need={before.need}); actions={actions}"
    )
    assert after_status == "MET"
    assert after_have >= 1


# ---------------------------------------------------------------------------
# Bug-finding diagnostics
# ---------------------------------------------------------------------------


def test_real_exec_13183_detect_stale_aspirational_meta_while_met(tmp_path: Path) -> None:
    """MET floor reconcile clears aspirational@0 / have=0 advisories from hollow era."""
    rid = "exec_13183_d19c15b58ab4_20260924T001619Z"
    src = EXECUTIONS_ROOT / rid
    if not src.is_dir():
        pytest.skip(f"missing {rid}")
    probe = _probe_live(rid)
    assert probe is not None and probe.sufficient_met, (
        f"{rid} must be MET for this probe (got {probe})"
    )
    ctx = _clone_slice(tmp_path, src, rid)
    # Precondition: tape still carries hollow-era stamps before reconcile.
    meta0 = ctx.read_json("run_meta.json")
    assert meta0.get("floor_aspirational_proceeded") is True or any(
        isinstance(a, dict)
        and str(a.get("gate_id") or "") == "hosted_vo_floor"
        and isinstance(a.get("detail"), dict)
        and int((a.get("detail") or {}).get("have") or -1) == 0
        for a in (meta0.get("floor_advisories") or [])
    ), "fixture must still show the stale hollow-era stamps to clear"

    snap = floor_snapshot(ctx, persist=True)
    assert snap.identity.status == "MET" and snap.have >= 3
    assert not may_aspirational_proceed(ctx)
    reconcile_escalations(ctx, snap)

    meta = ctx.read_json("run_meta.json")
    stale_flags = {
        "aspirational_proceeded": meta.get("aspirational_proceeded"),
        "floor_aspirational_proceeded": meta.get("floor_aspirational_proceeded"),
    }
    advisories = meta.get("floor_advisories") or []
    hollow_adv = [
        a
        for a in advisories
        if isinstance(a, dict)
        and str(a.get("gate_id") or "") == "hosted_vo_floor"
        and isinstance(a.get("detail"), dict)
        and int((a.get("detail") or {}).get("have") or -1) == 0
    ]

    problems: list[str] = []
    if stale_flags.get("floor_aspirational_proceeded") is True:
        problems.append(
            "floor_aspirational_proceeded=True while identity MET "
            f"(have={snap.have} need={snap.need})"
        )
    if stale_flags.get("aspirational_proceeded") is True:
        problems.append(
            f"aspirational_proceeded=True while identity MET (have={snap.have})"
        )
    if hollow_adv:
        problems.append(
            f"stale floor_advisories still record have=0 ({len(hollow_adv)} rows) "
            f"while live have={snap.have}"
        )
    assert not problems, (
        "reconcile_escalations failed to clear stale aspirational/hollow advisories "
        "after MET recovery.\n- " + "\n- ".join(problems)
    )


def test_real_exec_13183_heard_keep_force_remint_when_already_live(
    tmp_path: Path,
) -> None:
    """Already-live HEARD_KEEP must not force remint on a MET floor."""
    rid = "exec_13183_d19c15b58ab4_20260924T001619Z"
    src = EXECUTIONS_ROOT / rid
    if not src.is_dir():
        pytest.skip(f"missing {rid}")
    ctx = _clone_slice(tmp_path, src, rid)
    ident = identify_hosted_vo_floor(ctx, persist=False)
    assert ident.status == "MET" and ident.have >= 1

    gap = ctx.read_json("understanding/gap_report.json")
    orient_live = any(
        isinstance(ln, dict)
        and str(ln.get("line_id") or "") == ORIENTATION_LINE_ID
        and str(ln.get("text") or "").strip()
        and not ln.get("skipped_optional")
        for ln in (gap.get("interviewer_lines") or [])
    )
    assert orient_live, "fixture must already seat orientation in gap"
    assert (gap.get("opening_orientation") or {}).get("required") is True
    assert (gap.get("opening_orientation") or {}).get("omitted") is not True

    d = decide_orientation(ctx, gap, _ordered_ids(ctx))
    assert d.disposition == "HEARD_KEEP"
    assert d.force_remint is False, (
        "decide_orientation(HEARD_KEEP) must not force_remint when orientation "
        f"is already live in gap on {rid} (MET have={ident.have})."
    )


def test_real_exec_met_reconcile_does_not_reopen_escalation(tmp_path: Path) -> None:
    mets = _require_met_runs()
    probe = next((p for p in mets if "13183" in p.run_id), mets[0])
    ctx = _clone_slice(tmp_path, probe.path, probe.run_id)
    snap = floor_snapshot(ctx, persist=False)
    assert snap.identity.status == "MET"
    reconcile_escalations(ctx, snap)
    if ctx.artifact_exists("operator/escalations/nugget_layup_compose.json"):
        esc = ctx.read_json("operator/escalations/nugget_layup_compose.json")
        status = str((esc or {}).get("status") or "").lower()
        assert status in {"cleared", "closed", ""}, (
            f"{probe.run_id}: reconcile left escalation open={esc!r}"
        )
    meta = ctx.read_json("run_meta.json")
    assert not meta.get("hosted_vo_floor_unsatisfiable")
    assert not meta.get("hosted_vo_floor_unmet")


def test_real_exec_cross_run_met_authority_stable(tmp_path: Path) -> None:
    mets = _require_met_runs()
    summaries: list[dict[str, Any]] = []
    for probe in mets:
        ctx = _clone_slice(tmp_path / probe.run_id, probe.path, probe.run_id)
        ident = identify_hosted_vo_floor(ctx, persist=False)
        summaries.append(
            {
                "run_id": probe.run_id,
                "status": ident.status,
                "have": ident.have,
                "need": ident.need,
                "may_asp": may_aspirational_proceed(ctx),
                "books": assert_books_agree(ctx),
                "incompleteness": synthetic_vo_incompleteness(
                    ctx, "nugget_layup_compose"
                ),
            }
        )
    bad = [
        s
        for s in summaries
        if s["status"] != "MET"
        or s["have"] < 1
        or s["have"] < s["need"]
        or s["may_asp"]
        or s["books"]
        or s["incompleteness"]
    ]
    assert not bad, f"MET prior runs violated healthy SSOT invariants: {bad}"
