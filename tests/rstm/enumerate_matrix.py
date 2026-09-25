"""Enumerate RSTM matrix from HEAD orders, pins, and Wave-A P0/P1 clusters."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.stage_completion import PRODUCER_PIN_TABLE
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER, SHIP_AFTER_MASTER

try:
    from tests.rstm import CAMPAIGN_ID, CELL_CEILING, WAVE_A_ID
    from tests.rstm.mutations import HIGH_YIELD, MUTATIONS
    from tests.rstm.residual_cluster_scorecard import (
        DONE_WHEN_CATALOG,
        REQUIRED_IDS,
        catalog_surfaces,
    )
except ModuleNotFoundError:
    from rstm import CAMPAIGN_ID, CELL_CEILING, WAVE_A_ID  # type: ignore
    from rstm.mutations import HIGH_YIELD, MUTATIONS  # type: ignore
    from residual_cluster_scorecard import (  # type: ignore
        DONE_WHEN_CATALOG,
        REQUIRED_IDS,
        catalog_surfaces,
    )

ROOT = Path(__file__).resolve().parents[2]
RSTM_DIR = ROOT / "tests" / "rstm"
MATRIX_JSON = RSTM_DIR / "matrix.json"
MATRIX_MD = RSTM_DIR / "matrix.md"

GATES = (
    "G0",
    "G_Framing",
    "G1",
    "G_Listen",
    "G_Publish",
    "preclean_offer",
    "timeline_optimizer",
)

MODES = ("manual", "full_auto", "partial")

# Wave-A P0/P1 surfaces (stage or symbolic) for D3 seeding.
P0_SURFACES: list[tuple[str, str]] = [
    ("XC-HOLLOW-01", "content_context"),
    ("SYN-SHAPE-01", "mastering_plan_synthesize"),
    ("DEEP-RESPLIT-01", "boundary_topic_resplit"),
    ("DEEP-FUSE-01", "connector_fuse_pass"),
    ("DEEP-JUNCTION-01", "junction_snip_qa"),
    ("DEEP-VO-01", "vo_synthesize"),
    ("DEEP-STT-01", "transcribe"),
    ("DEEP-SPINE-01", "interview_spine_build"),
    ("DEEP-PROBE-01", "audio_probe_build"),
    ("DEEP-PRECLEAN-01", "audio_preclean"),
    ("DEEP-MIX-01", "mix"),
    ("STG-nugget_layup-DEPTH", "nugget_layup_compose"),
    ("MTL-CHATTERBOX-01", "vo_synthesize"),
    ("XC-SHIP-02", "master_finalize"),
    ("SYN-DELIGHT-01", "listen_delight_audit"),
]

P1_SURFACES: list[tuple[str, str]] = [
    ("DEEP-CUTS-01", "ideal_cuts_materialize"),
    ("DEEP-VERNACULAR-01", "vernacular_segment_sanitize"),
    ("DEEP-SONIC-01", "sonic_context_build"),
    ("DEEP-HITCH-01", "chapter_close_hitch"),
    ("DEEP-AIR-01", "air_script_compose"),
    ("DEEP-VO-FIN-01", "sound_design_vo_finalize"),
    ("SYN-MIX-01", "mix"),
    ("SYN-GFR-01", "framing_posture_decide"),
    ("SYN-PREPARE-01", "audio_preclean"),
    ("XC-SEED-01", "vo_synthesize"),
    ("XC-SHIP-01", "master_finalize"),
    ("GATE-G1-01", "vo_synthesize"),
]

S4_SURFACES = (
    "boundary_topic_resplit",
    "connector_fuse_pass",
    "junction_snip_qa",
    "vo_synthesize",
)


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _all_stages() -> list[str]:
    seen: list[str] = []
    for s in list(ANALYSIS_ORDER) + list(DELIVERY_ORDER) + list(SHIP_AFTER_MASTER):
        if s not in seen:
            seen.append(s)
    return seen


def _order_pairs(order: tuple[str, ...] | list[str], gap: int = 1) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for i in range(len(order) - gap):
        out.append((order[i], order[i + gap]))
    return out


def _cell(
    *,
    cell_id: str,
    tier: str,
    depth: int,
    stages: list[str],
    mutation: str,
    mode: str,
    formation: str,
    cluster: str = "",
    expect: str = "pass_or_block",
) -> dict[str, Any]:
    return {
        "cell_id": cell_id,
        "tier": tier,
        "depth": depth,
        "stages": stages,
        "mutation": mutation,
        "mode": mode,
        "formation": formation,
        "cluster": cluster,
        "expect": expect,
    }


def _successors(stage: str, limit: int) -> list[str]:
    stages = _all_stages()
    if stage not in stages:
        # pin / analysis-only
        idx = -1
    else:
        idx = stages.index(stage)
    out: list[str] = []
    if 0 <= idx < len(stages) - 1:
        out.append(stages[idx + 1])
    if 0 <= idx < len(stages) - 2:
        out.append(stages[idx + 2])
    # pin consumers that mention stage
    for tok, pin in PRODUCER_PIN_TABLE.items():
        if pin == stage and tok in stages and tok not in out:
            out.append(tok)
        if tok == stage and pin in stages and pin not in out:
            out.append(pin)
    # atypical: walk toward edl / mix for delivery stages
    for prefer in ("edl", "mix", "vo_synthesize", "master_finalize", "transitions"):
        if prefer in stages and prefer != stage and prefer not in out:
            out.append(prefer)
    return out[:limit]


def enumerate_matrix() -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    capped_out: list[str] = []
    stages = _all_stages()
    mut_all = list(MUTATIONS.keys())
    mut_hy = list(HIGH_YIELD)

    # D1
    for s in stages:
        mode = "invariant"
        if s in (
            "audio_preclean",
            "transcript_review_build",
            "framing_posture_decide",
            "missing_framing",
            "vo_synthesize",
            "listen_delight_audit",
            "podcast_publish",
        ):
            for m in MODES:
                cells.append(
                    _cell(
                        cell_id=f"D1|{s}|{m}|M1_none",
                        tier="D1",
                        depth=1,
                        stages=[s],
                        mutation="M1_none",
                        mode=m,
                        formation="F1",
                        cluster="hollow-done-coverage",
                    )
                )
        else:
            cells.append(
                _cell(
                    cell_id=f"D1|{s}|{mode}|M1_none",
                    tier="D1",
                    depth=1,
                    stages=[s],
                    mutation="M1_none",
                    mode=mode,
                    formation="F1",
                    cluster="hollow-done-coverage",
                )
            )

    # D2-SEED
    for a, b in _order_pairs(ANALYSIS_ORDER) + _order_pairs(DELIVERY_ORDER):
        for mut in mut_all:
            cells.append(
                _cell(
                    cell_id=f"D2-SEED|{a}->{b}|invariant|{mut}",
                    tier="D2-SEED",
                    depth=2,
                    stages=[a, b],
                    mutation=mut,
                    mode="invariant",
                    formation="F1",
                )
            )

    # D2-SKIP1
    skip_cells = 0
    skip_cap = 1200
    for order in (ANALYSIS_ORDER, DELIVERY_ORDER):
        for a, b in _order_pairs(order, gap=2):
            for mut in ("M1_none", "M5_stage_done_without_primary", "M6_pending_shadow"):
                if skip_cells >= skip_cap:
                    capped_out.append("D2-SKIP1 remainder")
                    break
                cells.append(
                    _cell(
                        cell_id=f"D2-SKIP1|{a}->{b}|invariant|{mut}",
                        tier="D2-SKIP1",
                        depth=2,
                        stages=[a, b],
                        mutation=mut,
                        mode="invariant",
                        formation="F1",
                        cluster="partial-prepare-order",
                    )
                )
                skip_cells += 1
            else:
                continue
            break

    # D2-ATYP from PRODUCER_PIN_TABLE
    atyp = 0
    atyp_cap = 2500
    for tok, pin in sorted(PRODUCER_PIN_TABLE.items()):
        if pin not in stages:
            continue
        # consumer guess: token if stage else pin's next
        consumer = tok if tok in stages else None
        if consumer is None:
            succ = _successors(pin, 1)
            consumer = succ[0] if succ else "edl"
        if consumer == pin:
            continue
        for mut in mut_hy:
            for mode in MODES:
                if atyp >= atyp_cap:
                    capped_out.append("D2-ATYP remainder")
                    break
                cells.append(
                    _cell(
                        cell_id=f"D2-ATYP|{pin}->{consumer}|{mode}|{mut}|{tok}",
                        tier="D2-ATYP",
                        depth=2,
                        stages=[pin, consumer],
                        mutation=mut,
                        mode=mode,
                        formation="F2",
                        cluster="heal-navigate-pins",
                        expect="block_or_resume",
                    )
                )
                atyp += 1
            else:
                continue
            break
        if atyp >= atyp_cap:
            break

    # D2-RR repeat/rewind
    rr = 0
    rr_cap = 800
    for pin in sorted(set(PRODUCER_PIN_TABLE.values())):
        if pin not in stages:
            continue
        for mut in ("M5_stage_done_without_primary", "M8_seated_vo_no_wav", "M1_none"):
            if rr >= rr_cap:
                capped_out.append("D2-RR remainder")
                break
            cells.append(
                _cell(
                    cell_id=f"D2-RR|{pin}->{pin}|invariant|{mut}",
                    tier="D2-RR",
                    depth=2,
                    stages=[pin, pin],
                    mutation=mut,
                    mode="invariant",
                    formation="F2",
                    cluster="remutate-chain",
                )
            )
            rr += 1
        else:
            continue
        break

    # D2-PC producer→consumer via STAGE paths
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

    pc = 0
    pc_cap = 1500
    primary_stages = [s for s in stages if s in STAGE_ARTIFACT_DISK_PATHS]
    for i, writer in enumerate(primary_stages):
        for reader in primary_stages[i + 2 : i + 8]:
            for mut in ("M2_empty_array", "M5_stage_done_without_primary", "M6_pending_shadow", "M10_id_remap"):
                if pc >= pc_cap:
                    capped_out.append("D2-PC remainder")
                    break
                cells.append(
                    _cell(
                        cell_id=f"D2-PC|{writer}->{reader}|invariant|{mut}",
                        tier="D2-PC",
                        depth=2,
                        stages=[writer, reader],
                        mutation=mut,
                        mode="invariant",
                        formation="F4",
                        cluster="hollow-done-coverage",
                    )
                )
                pc += 1
            else:
                continue
            break
        if pc >= pc_cap:
            break

    # D2-GATE
    gate_n = 0
    gate_cap = 600
    gate_neighbors = {
        "G0": ("transcript_review_build", "audio_probe_build"),
        "G_Framing": ("framing_posture_decide", "missing_framing"),
        "G1": ("vo_line_adjudicate", "vo_synthesize"),
        "G_Listen": ("listen_delight_audit", "music_palette_compose"),
        "G_Publish": ("master_transcript_build", "podcast_publish"),
        "preclean_offer": ("audio_preclean", "ingest"),
        "timeline_optimizer": ("junction_snip_qa", "master_finalize"),
    }
    for gate, (pre, post) in gate_neighbors.items():
        for mode in MODES:
            for mut in ("M1_none", "M5_stage_done_without_primary"):
                if gate_n >= gate_cap:
                    break
                cells.append(
                    _cell(
                        cell_id=f"D2-GATE|{pre}->{gate}|{mode}|{mut}",
                        tier="D2-GATE",
                        depth=2,
                        stages=[pre, gate],
                        mutation=mut,
                        mode=mode,
                        formation="F3",
                        cluster="mode-gate-honesty",
                    )
                )
                cells.append(
                    _cell(
                        cell_id=f"D2-GATE|{gate}->{post}|{mode}|{mut}",
                        tier="D2-GATE",
                        depth=2,
                        stages=[gate, post],
                        mutation=mut,
                        mode=mode,
                        formation="F3",
                        cluster="mode-gate-honesty",
                    )
                )
                gate_n += 2

    def add_d3(surfaces: list[tuple[str, str]], tier: str, n1: int, n2: int, global_budget: list[int]):
        for finding_id, surface in surfaces:
            if global_budget[0] <= 0:
                capped_out.append(f"{tier} global")
                return
            s1 = _successors(surface, n1) or ["edl"]
            for b in s1:
                s2 = _successors(b, n2) or ["mix"]
                for c in s2:
                    for mut in mut_hy[:5]:
                        if global_budget[0] <= 0:
                            return
                        cells.append(
                            _cell(
                                cell_id=f"{tier}|{finding_id}|{surface}->{b}->{c}|{mut}",
                                tier=tier,
                                depth=3,
                                stages=[surface, b, c],
                                mutation=mut,
                                mode="invariant",
                                formation="F1",
                                cluster=finding_id,
                            )
                        )
                        global_budget[0] -= 1

    d3_budget = [4500]
    add_d3(P0_SURFACES, "D3-P0", 12, 8, d3_budget)
    add_d3(P1_SURFACES, "D3-P1", 12, 8, d3_budget)

    # D3-DUALMUT
    dual = 0
    dual_cap = 900
    for finding_id, surface in P0_SURFACES:
        s1 = _successors(surface, 3)
        for b in s1:
            for c in _successors(b, 2) or ["edl"]:
                for m1 in ("M5_stage_done_without_primary", "M6_pending_shadow"):
                    for m2 in ("M8_seated_vo_no_wav", "M10_id_remap"):
                        if dual >= dual_cap:
                            break
                        cells.append(
                            _cell(
                                cell_id=f"D3-DUALMUT|{finding_id}|{surface}->{b}->{c}|{m1}+{m2}",
                                tier="D3-DUALMUT",
                                depth=3,
                                stages=[surface, b, c],
                                mutation=f"{m1}+{m2}",
                                mode="invariant",
                                formation="F5",
                                cluster=finding_id,
                            )
                        )
                        dual += 1
                    else:
                        continue
                    break
                if dual >= dual_cap:
                    break
            if dual >= dual_cap:
                break
        if dual >= 6 * len(P0_SURFACES) and dual >= 90:
            # ensure minimum then continue until cap naturally
            pass
        if dual >= dual_cap:
            capped_out.append("D3-DUALMUT remainder")
            break

    # D3-FANIN
    fanin_specs = [
        ("boundary_detection", "boundary_topic_resplit", "segment_classification"),
        ("content_context", "content_brief_reanchor", "missing_framing"),
        ("nugget_layup_compose", "air_script_seams", "air_contract_sanitize"),
        ("sfx_prompt_craft", "mmaudio_sfx", "mix"),
        ("edl", "junction_snip_qa", "master_finalize"),
    ]
    fi = 0
    for p1, p2, c in fanin_specs:
        for mut in mut_hy:
            for order in ((p1, p2, c), (p2, p1, c)):
                if fi >= 700:
                    break
                cells.append(
                    _cell(
                        cell_id=f"D3-FANIN|{'+'.join(order)}|{mut}",
                        tier="D3-FANIN",
                        depth=3,
                        stages=list(order),
                        mutation=mut,
                        mode="invariant",
                        formation="F4",
                        cluster="invalidation-blast",
                    )
                )
                fi += 1

    # D3-GATEMID
    gm = 0
    for gate, (pre, post) in gate_neighbors.items():
        if gate not in ("G0", "G_Framing", "G1", "G_Listen"):
            continue
        for mode in MODES:
            for mut in ("M1_none", "M5_stage_done_without_primary"):
                if gm >= 800:
                    break
                third = _successors(post, 1)
                c = third[0] if third else post
                cells.append(
                    _cell(
                        cell_id=f"D3-GATEMID|{pre}->{gate}->{post}->{c}|{mode}|{mut}",
                        tier="D3-GATEMID",
                        depth=3,
                        stages=[pre, gate, post],
                        mutation=mut,
                        mode=mode,
                        formation="F3",
                        cluster="mode-gate-honesty",
                    )
                )
                gm += 1

    # D4-S4
    d4 = 0
    for surface in S4_SURFACES:
        chain = [surface]
        cur = surface
        for _ in range(3):
            nxt = _successors(cur, 4)
            if not nxt:
                break
            cur = nxt[0]
            chain.append(cur)
        while len(chain) < 4:
            chain.append(chain[-1])
        for mut in ("M1_none", "M5_stage_done_without_primary"):
            for branch in _successors(surface, 4):
                if d4 >= 400:
                    break
                stages4 = [surface, branch, chain[2], chain[3]]
                cells.append(
                    _cell(
                        cell_id=f"D4-S4|{'->'.join(stages4)}|{mut}",
                        tier="D4-S4",
                        depth=4,
                        stages=stages4,
                        mutation=mut,
                        mode="invariant",
                        formation="F2",
                        cluster="junction-remaster-thrash",
                    )
                )
                d4 += 1

    # GATE + INV dedicated
    for gate in GATES:
        for mode in MODES:
            cells.append(
                _cell(
                    cell_id=f"GATE|{gate}|{mode}|M1_none",
                    tier="GATE",
                    depth=1,
                    stages=[gate],
                    mutation="M1_none",
                    mode=mode,
                    formation="F3",
                    cluster="mode-gate-honesty",
                )
            )
    for inv in (
        "clear_from",
        "chapter_close_hitch",
        "boundary_topic_resplit",
        "connector_fuse_pass",
        "pending_shadow",
        "committed_master",
    ):
        cells.append(
            _cell(
                cell_id=f"INV|{inv}|invariant|M1_none",
                tier="INV",
                depth=1,
                stages=[inv],
                mutation="M1_none",
                mode="invariant",
                formation="F4",
                cluster="invalidation-blast",
            )
        )

    # RC-DW — residual cluster Done-when scorecard (Wave 8)
    surfaces = catalog_surfaces()
    for catalog_id in sorted(REQUIRED_IDS):
        stage = surfaces.get(catalog_id, "scorecard")
        cells.append(
            _cell(
                cell_id=f"RC-DW|{catalog_id}|invariant|M1_none",
                tier="RC-DW",
                depth=1,
                stages=[stage],
                mutation="M1_none",
                mode="invariant",
                formation="F1",
                cluster=catalog_id,
                expect="named_proof",
            )
        )

    # Ceiling trim
    if len(cells) > CELL_CEILING:
        # drop low-priority D2-ATYP then D3-P1 then D4; keep RC-DW
        def priority(c: dict[str, Any]) -> int:
            t = c["tier"]
            order = {
                "RC-DW": 0,
                "D1": 1,
                "D2-SEED": 2,
                "D2-SKIP1": 3,
                "D3-P0": 4,
                "D3-DUALMUT": 5,
                "D3-FANIN": 6,
                "D3-GATEMID": 7,
                "D2-RR": 8,
                "D2-PC": 9,
                "D2-GATE": 10,
                "GATE": 11,
                "INV": 12,
                "D3-P1": 13,
                "D2-ATYP": 14,
                "D4-S4": 15,
            }
            return order.get(t, 50)

        cells.sort(key=priority)
        overflow = cells[CELL_CEILING:]
        cells = cells[:CELL_CEILING]
        capped_out.append(f"GLOBAL_CEILING dropped {len(overflow)} cells")

    # Coverage gate data
    tiers = {c["tier"] for c in cells}
    p0_ok = all(
        any(c["tier"] == "D3-P0" and c["stages"] and c["stages"][0] == surf for c in cells)
        for _, surf in P0_SURFACES
    )
    rc_clusters = {
        c["cluster"]
        for c in cells
        if c["tier"] == "RC-DW" and c.get("cluster") in DONE_WHEN_CATALOG
    }
    residual_donewhen = REQUIRED_IDS.issubset(rc_clusters)
    meta = {
        "campaign_id": CAMPAIGN_ID,
        "wave": "B",
        "generated_at": _now(),
        "git_head": _git_head(),
        "merges_wave_a": WAVE_A_ID,
        "cell_ceiling": CELL_CEILING,
        "cell_count": len(cells),
        "tiers_present": sorted(tiers),
        "capped_out": capped_out,
        "coverage": {
            "d1": any(c["tier"] == "D1" for c in cells),
            "d2_seed": any(c["tier"] == "D2-SEED" for c in cells),
            "d2_skip1": any(c["tier"] == "D2-SKIP1" for c in cells),
            "p0_d3": p0_ok,
            "residual_donewhen": residual_donewhen,
            "formations": sorted({c["formation"] for c in cells}),
        },
        "cells": cells,
    }
    return meta


def write_matrix(meta: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = meta or enumerate_matrix()
    RSTM_DIR.mkdir(parents=True, exist_ok=True)
    MATRIX_JSON.write_text(json.dumps(meta, indent=2) + "\n")
    lines = [
        f"# RSTM matrix — {meta['campaign_id']}",
        "",
        f"- generated_at: `{meta['generated_at']}`",
        f"- git_head: `{meta['git_head']}`",
        f"- cell_count: **{meta['cell_count']}** / ceiling {meta['cell_ceiling']}",
        f"- tiers: {', '.join(meta['tiers_present'])}",
        f"- coverage: `{json.dumps(meta['coverage'])}`",
        f"- capped_out: {meta['capped_out'] or '[]'}",
        "",
        "## Tier counts",
        "",
    ]
    from collections import Counter

    counts = Counter(c["tier"] for c in meta["cells"])
    for tier, n in sorted(counts.items()):
        lines.append(f"- `{tier}`: {n}")
    MATRIX_MD.write_text("\n".join(lines) + "\n")
    return meta


def coverage_gate(meta: dict[str, Any]) -> None:
    cov = meta["coverage"]
    errors = []
    if not cov.get("d1"):
        errors.append("D1 incomplete")
    if not cov.get("d2_seed"):
        errors.append("D2-SEED incomplete")
    if not cov.get("d2_skip1"):
        errors.append("D2-SKIP1 incomplete")
    if not cov.get("p0_d3"):
        errors.append("P0 missing D3 trajectory")
    if not cov.get("residual_donewhen"):
        errors.append("residual_donewhen (RC-DW) incomplete")
    needed = {"F1", "F2", "F3", "F4", "F5"}
    have = set(cov.get("formations") or [])
    if not needed.issubset(have):
        errors.append(f"formations missing {needed - have}")
    if errors:
        raise SystemExit("RSTM coverage gate FAILED: " + "; ".join(errors))


def main() -> None:
    meta = write_matrix()
    coverage_gate(meta)
    print(f"OK cells={meta['cell_count']} tiers={meta['tiers_present']}")


if __name__ == "__main__":
    main()
