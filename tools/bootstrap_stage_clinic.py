#!/usr/bin/env python3
"""Bootstrap Stage Clinic packs for all 72 pipeline stages.

Idempotent: does not overwrite non-empty maps/targets/notes.
Creates empty dossiers (always refreshed from template if still skeleton),
queue, ledger stubs, defaults_inventory, cross_stage_patterns.

Usage (repo root, venv optional):
  python tools/bootstrap_stage_clinic.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER  # noqa: E402

CLINIC = ROOT / ".cursor" / "stage-clinic"
TEMPLATES = CLINIC / "templates"
CONTRACTS = ROOT / "docs" / "cross-cutting" / "stage-contracts"

GATE_ADJACENCY = {
    "transcript_review_build": "G0",
    "framing_posture_decide": "G-Framing",
    "audio_preclean": "preclean",
    "vo_synthesize": "G1",
    "gap_framing_compose": "G1",
    "missing_framing": "G-Framing",
    "podcast_publish": "G-Publish",
    "master_transcript_build": "G-Publish",
    "listen_delight_audit": "listen_delight",
}


def _read_template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def _tier_and_primary(stage_id: str) -> tuple[str, str]:
    path = CONTRACTS / f"{stage_id}.yaml"
    tier = "unknown"
    primary = ""
    if not path.is_file():
        return tier, primary
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^tier:\s*(\S+)", text, re.M)
    if m:
        tier = m.group(1).strip()
    # first outputs path
    m2 = re.search(r"^outputs:\s*\n-\s*path:\s*(\S+)", text, re.M)
    if m2:
        primary = m2.group(1).strip()
    return tier, primary


def _is_empty_or_stub(path: Path) -> bool:
    if not path.exists():
        return True
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return True
    # treat unfilled templates as stubs
    if "discovery_status: not_started" in text and "Case | Outcome" in text.replace("|", "|"):
        # already has structure; if no IN_CODE tags filled, still stub for overwrite? Plan says do not overwrite non-empty maps
        # Non-empty means any content beyond whitespace — so once written, keep.
        return False
    return False


def _render(template: str, stage_id: str, seed_position: int, seed_phase: str) -> str:
    tier, primary = _tier_and_primary(stage_id)
    gate = GATE_ADJACENCY.get(stage_id, "none")
    out = template
    out = out.replace("{{STAGE_ID}}", stage_id)
    out = out.replace("{{SEED_POSITION}}", str(seed_position))
    out = out.replace("{{SEED_PHASE}}", seed_phase)
    out = out.replace("{{TIER}}", tier)
    out = out.replace("{{PRIMARY_PATH}}", primary or "(unset)")
    # dossier gate hint
    if "gate_adjacency:" in out and gate != "none":
        out = out.replace(
            "gate_adjacency: none | G0 | G-Framing | G1 | preclean | G-Publish | other:",
            f"gate_adjacency: {gate}",
        )
    return out


def _write_if_absent(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def _write_dossier(path: Path, content: str) -> None:
    """Dossiers may be refreshed while still not_started skeletons."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if "L1_map: not_started" not in existing or "Module (fill in L1)" not in existing:
            # operator/agent has progressed — do not clobber
            if "discovery_status: complete" in existing or "L1_map: complete" in existing:
                return
            if "IN_CODE" in existing and "Code pointer" not in existing[:500]:
                return
    path.write_text(content, encoding="utf-8")


def build_queue(stages: list[tuple[str, str, int]]) -> str:
    lines = [
        "# Stage Clinic queue — brain 0.2.0 / analysis walk",
        "",
        "Order = ANALYSIS_ORDER then DELIVERY_ORDER. Mark `[x]` when L1 map complete or waived.",
        "",
        "## Analysis",
        "",
    ]
    for stage_id, phase, pos in stages:
        if phase != "analysis":
            continue
        gate = GATE_ADJACENCY.get(stage_id)
        suffix = f" — gate:{gate}" if gate else ""
        lines.append(f"- [ ] `{pos:02d}` `{stage_id}`{suffix}")
    lines.extend(["", "## Delivery", ""])
    for stage_id, phase, pos in stages:
        if phase != "delivery":
            continue
        gate = GATE_ADJACENCY.get(stage_id)
        suffix = f" — gate:{gate}" if gate else ""
        lines.append(f"- [ ] `{pos:02d}` `{stage_id}`{suffix}")
    lines.append("")
    return "\n".join(lines)


def build_ledger(stages: list[tuple[str, str, int]]) -> str:
    header = (
        "# Stage Clinic ledger\n\n"
        "| stage | phase | wave | L1_map | L2_target | L3_patch | simplified_to_rules | open_questions | blocked_on |\n"
        "|-------|-------|------|--------|-----------|----------|---------------------|----------------|------------|\n"
    )
    rows = []
    for stage_id, phase, _pos in stages:
        rows.append(
            f"| `{stage_id}` | {phase} | analysis | not_started | not_started | not_started | n/a_analysis_only | | |"
        )
    return header + "\n".join(rows) + "\n"


def main() -> int:
    if not TEMPLATES.is_dir():
        print(f"missing templates at {TEMPLATES}", file=sys.stderr)
        return 1

    dossier_t = _read_template("dossier.md")
    map_t = _read_template("possibility_map.md")
    target_t = _read_template("target_spec.md")
    decisions_t = _read_template("decisions.md")
    defaults_t = _read_template("defaults_inventory.md")
    cross_t = _read_template("cross_stage_patterns.md")
    ready_t = _read_template("full_auto_readiness.md")

    stages: list[tuple[str, str, int]] = []
    for i, s in enumerate(ANALYSIS_ORDER, start=1):
        stages.append((s, "analysis", i))
    for i, s in enumerate(DELIVERY_ORDER, start=len(ANALYSIS_ORDER) + 1):
        stages.append((s, "delivery", i))

    assert len(stages) == 72, f"expected 72 stages, got {len(stages)}"

    created = {"dossier": 0, "map": 0, "target": 0, "notes": 0}

    for stage_id, phase, pos in stages:
        d_body = _render(dossier_t, stage_id, pos, phase)
        m_body = _render(map_t, stage_id, pos, phase)
        t_body = _render(target_t, stage_id, pos, phase)
        n_body = _render(decisions_t, stage_id, pos, phase)

        d_path = CLINIC / "dossiers" / f"{stage_id}.md"
        m_path = CLINIC / "maps" / f"{stage_id}.possibility.md"
        t_path = CLINIC / "targets" / f"{stage_id}.target.md"
        n_path = CLINIC / "notes" / f"{stage_id}.decisions.md"

        _write_dossier(d_path, d_body)
        created["dossier"] += 1
        if _write_if_absent(m_path, m_body):
            created["map"] += 1
        if _write_if_absent(t_path, t_body):
            created["target"] += 1
        if _write_if_absent(n_path, n_body):
            created["notes"] += 1

    # Root artifacts — create if missing; do not clobber filled defaults/readiness
    readme = CLINIC / "README.md"
    if not readme.exists() or readme.stat().st_size == 0:
        readme.write_text(
            "# Stage Clinic pack\n\n"
            "Campaign SSOT: [`../plans/stage_clinic.plan.md`](../plans/stage_clinic.plan.md)\n\n"
            "Skill: [`../skills/stage-clinic/SKILL.md`](../skills/stage-clinic/SKILL.md)\n\n"
            "## Waves\n\n"
            "- **Wave 0** — framework (this tree + skill + paste prompts)\n"
            "- **Wave 1** — analysis walk (L1 maps; L2 draft targets). **No product patches.**\n"
            "- **Wave 2** — remediation from targets (`/stage-clinic-implement` only)\n"
            "- **Wave 3** — `full_auto_readiness.md` scorecard\n\n"
            "## Bootstrap\n\n"
            "```bash\npython tools/bootstrap_stage_clinic.py\n```\n",
            encoding="utf-8",
        )

    queue_path = CLINIC / "queue-partial-020.md"
    # refresh queue checkboxes only if file missing or still all unchecked stubs
    if not queue_path.exists() or "[x]" not in queue_path.read_text(encoding="utf-8"):
        queue_path.write_text(build_queue(stages), encoding="utf-8")

    ledger_path = CLINIC / "ledger.md"
    if not ledger_path.exists() or "L1_map: complete" not in ledger_path.read_text(encoding="utf-8"):
        # only rewrite if no completed rows yet
        existing = ledger_path.read_text(encoding="utf-8") if ledger_path.exists() else ""
        if "| complete |" not in existing and "| draft |" not in existing and "| done |" not in existing:
            ledger_path.write_text(build_ledger(stages), encoding="utf-8")

    _write_if_absent(CLINIC / "defaults_inventory.md", defaults_t)
    _write_if_absent(CLINIC / "cross_stage_patterns.md", cross_t)
    _write_if_absent(CLINIC / "full_auto_readiness.md", ready_t)

    print(f"Stage Clinic bootstrap OK — {len(stages)} stages")
    print(f"  dossiers touched: {created['dossier']}")
    print(f"  new maps: {created['map']}, new targets: {created['target']}, new notes: {created['notes']}")
    print(f"  root: {CLINIC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
