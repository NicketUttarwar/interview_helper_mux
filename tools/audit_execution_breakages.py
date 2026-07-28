#!/usr/bin/env python3
"""Scan ASSETS/executions for production breakages that yield source-like masters.

Reports Chatterbox/S2S TTS failures, G1 skip cascades, silent transitions,
thin/incomplete SFX, soft mix bypasses, DeepFilter/LLM runtime errors.

Exit 1 when any run that has master/master.wav still has a hard production breaker.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXEC = ROOT / "ASSETS" / "executions"

HARD = "hard"
SOFT = "soft"
ADVISORY = "advisory"

_FROM_PRETRAINED = re.compile(r"from_pretrained.*multiple values|got multiple values for argument 'device'", re.I)
_CHATTERBOX_FAIL = re.compile(r"chatterbox|local_chatterbox|ChatterboxTTS", re.I)
_S2S_FAIL = re.compile(r"s2s_generate|mlx-audio|Local runtime speech failed|S2S failed", re.I)
_SOFT_MIX = re.compile(r"block_mix_without_sfx skipped \(soft_progression\)", re.I)
_DEEPFILTER = re.compile(r"deepfilter|DeepFilterNet|local_deepfilter", re.I)
_LLM_FAIL = re.compile(r"local_llm|mlx-lm|volley framer", re.I)
_TRUE_PEAK = re.compile(r"true.?peak|true_peak", re.I)


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _iter_log_text(run_dir: Path) -> str:
    chunks: list[str] = []
    for rel in ("logs/pipeline.log", "logs/operator.log", "run.log"):
        p = run_dir / rel
        if p.is_file():
            try:
                chunks.append(p.read_text(encoding="utf-8", errors="replace")[-500_000:])
            except OSError:
                pass
    log_dir = run_dir / "logs"
    if log_dir.is_dir():
        for p in sorted(log_dir.glob("*.log"))[-20:]:
            try:
                chunks.append(p.read_text(encoding="utf-8", errors="replace")[-200_000:])
            except OSError:
                pass
    return "\n".join(chunks)


def _vo_wav_count(run_dir: Path) -> int:
    pickup = run_dir / "vo_pickup"
    if not pickup.is_dir():
        return 0
    n = 0
    for p in pickup.rglob("*.wav"):
        if p.name.startswith("."):
            continue
        if "_s2s_context" in p.as_posix():
            continue
        n += 1
    return n


def _sfx_wav_count(run_dir: Path) -> int:
    assets = run_dir / "sound_design" / "assets"
    if not assets.is_dir():
        return 0
    return sum(1 for p in assets.glob("*.wav") if p.is_file())


def audit_run(run_dir: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    run_id = run_dir.name
    has_master = (run_dir / "master" / "master.wav").is_file()
    log_text = _iter_log_text(run_dir)
    meta = _read_json(run_dir / "run_meta.json") or {}
    edl = _read_json(run_dir / "master" / "edl.json") or {}
    gap = _read_json(run_dir / "understanding" / "gap_report.json") or {}
    sdp = _read_json(run_dir / "understanding" / "sound_design_plan.json") or {}
    qa = _read_json(run_dir / "sound_design" / "mmaudio_qa.json")
    transitions = _read_json(run_dir / "master" / "transitions.json") or {}

    if _FROM_PRETRAINED.search(log_text):
        findings.append(
            {
                "severity": HARD,
                "code": "chatterbox_api_mismatch",
                "detail": "from_pretrained device TypeError in logs",
            }
        )
    elif _CHATTERBOX_FAIL.search(log_text) and "fail-open" in log_text.lower():
        findings.append(
            {
                "severity": SOFT,
                "code": "chatterbox_fail_open",
                "detail": "Chatterbox failed; mlx-audio fallback attempted",
            }
        )

    if _S2S_FAIL.search(log_text) and "fail-open" in log_text.lower():
        # Only hard if VO ended empty with master present
        pass

    vo_n = _vo_wav_count(run_dir)
    vo_pickup_edl = int(edl.get("vo_pickup_clip_count") or 0)
    if isinstance(edl.get("clips"), list):
        vo_pickup_edl = sum(1 for c in edl["clips"] if isinstance(c, dict) and c.get("type") == "vo_pickup")

    g1_skipped = bool(meta.get("g1_vo_skipped_optional"))
    synth_lines = 0
    skipped_synth = 0
    for line in gap.get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        if str(line.get("delivery") or "").lower() == "synthesize":
            synth_lines += 1
            if line.get("skipped_optional"):
                skipped_synth += 1

    if has_master and synth_lines > 0 and vo_pickup_edl == 0 and (g1_skipped or skipped_synth == synth_lines):
        findings.append(
            {
                "severity": HARD,
                "code": "g1_skip_cascade_empty_vo",
                "detail": f"g1_skipped={g1_skipped} synth_lines={synth_lines} skipped_synth={skipped_synth} vo_wavs={vo_n} edl_vo={vo_pickup_edl}",
            }
        )
    elif has_master and synth_lines > 0 and vo_pickup_edl == 0 and vo_n == 0:
        findings.append(
            {
                "severity": HARD,
                "code": "missing_gap_vo",
                "detail": f"synth_lines={synth_lines} vo_wavs=0 edl_vo=0",
            }
        )

    # Silent spoken transitions
    silent_tr = 0
    tr_text = 0
    for item in transitions.get("transitions") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        tr_text += 1
    for clip in edl.get("clips") or []:
        if not isinstance(clip, dict) or clip.get("type") != "transition":
            continue
        text = str(clip.get("text") or "").strip()
        if text and int(clip.get("duration_ms") or 0) == 0:
            silent_tr += 1
    if has_master and silent_tr > 0:
        findings.append(
            {
                "severity": HARD,
                "code": "silent_spoken_transitions",
                "detail": f"edl_transitions_with_text_duration_0={silent_tr} transitions_with_text={tr_text}",
            }
        )

    # SFX completeness
    assets = [a for a in (sdp.get("assets") or []) if isinstance(a, dict) and a.get("asset_id")]
    planned = len(assets)
    generated = _sfx_wav_count(run_dir)
    cued_ids: set[str] = set()
    flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    for flow in flow_plans.values():
        if not isinstance(flow, dict):
            continue
        for cue in flow.get("cues") or []:
            if isinstance(cue, dict) and cue.get("asset_id"):
                cued_ids.add(str(cue["asset_id"]))
    if has_master and planned > 0 and generated < planned:
        findings.append(
            {
                "severity": HARD,
                "code": "incomplete_sfx_assets",
                "detail": f"planned={planned} generated={generated} cued={len(cued_ids)}",
            }
        )
    if has_master and planned > 0 and qa is None:
        findings.append(
            {
                "severity": HARD,
                "code": "missing_mmaudio_qa",
                "detail": "sound_design/mmaudio_qa.json missing",
            }
        )
    elif isinstance(qa, dict):
        fails = [
            r
            for r in (qa.get("assets") or [])
            if isinstance(r, dict) and str(r.get("verdict") or "").lower() == "fail"
        ]
        if fails:
            findings.append(
                {
                    "severity": SOFT,
                    "code": "mmaudio_qa_fail",
                    "detail": f"fail_count={len(fails)} ids={[r.get('asset_id') for r in fails[:6]]}",
                }
            )

    if _SOFT_MIX.search(log_text) and has_master and (generated == 0 or planned > generated):
        findings.append(
            {
                "severity": HARD,
                "code": "soft_progression_mix_bypass",
                "detail": "block_mix_without_sfx skipped under soft_progression with incomplete SFX",
            }
        )
    elif _SOFT_MIX.search(log_text):
        findings.append(
            {
                "severity": SOFT,
                "code": "soft_progression_mix_bypass_logged",
                "detail": "block_mix_without_sfx skipped (soft_progression)",
            }
        )

    if _DEEPFILTER.search(log_text) and re.search(r"deepfilter.*(fail|error|unavailable)", log_text, re.I):
        findings.append(
            {
                "severity": SOFT,
                "code": "deepfilter_runtime_error",
                "detail": "DeepFilterNet runtime error in logs",
            }
        )

    if re.search(r"local_llm.*(fail|error|unavailable)|framer.*(fail|error)", log_text, re.I):
        findings.append(
            {
                "severity": SOFT,
                "code": "local_llm_framer_error",
                "detail": "local LLM / framer hard failure signal in logs",
            }
        )

    if _TRUE_PEAK.search(log_text) and re.search(r"true.?peak.*(fail|alert|exceed)", log_text, re.I):
        findings.append(
            {
                "severity": ADVISORY,
                "code": "true_peak_alert",
                "detail": "verify_master true-peak advisory",
            }
        )

    hard = [f for f in findings if f["severity"] == HARD]
    return {
        "run_id": run_id,
        "has_master": has_master,
        "vo_wav_count": vo_n,
        "edl_vo_pickup": vo_pickup_edl,
        "g1_vo_skipped_optional": g1_skipped,
        "sfx_planned": planned,
        "sfx_generated": generated,
        "findings": findings,
        "hard_count": len(hard),
    }


def _recent_runs(exec_root: Path, limit: int) -> list[Path]:
    runs = [p for p in exec_root.glob("exec_*") if p.is_dir()]
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return runs[: max(1, limit)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executions-root", type=Path, default=DEFAULT_EXEC)
    parser.add_argument("--limit", type=int, default=25, help="Most recent runs to scan")
    parser.add_argument("--run-id", type=str, default="", help="Audit a single run id")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    root: Path = args.executions_root
    if not root.is_dir():
        print(f"No executions root: {root}", file=sys.stderr)
        return 2

    if args.run_id:
        targets = [root / args.run_id]
        if not targets[0].is_dir():
            print(f"Missing run: {targets[0]}", file=sys.stderr)
            return 2
    else:
        targets = _recent_runs(root, args.limit)

    reports = [audit_run(p) for p in targets]
    hard_with_master = [r for r in reports if r["has_master"] and r["hard_count"] > 0]

    if args.json:
        print(json.dumps({"runs": reports, "hard_with_master": len(hard_with_master)}, indent=2))
    else:
        print(f"Audited {len(reports)} run(s) under {root}")
        for r in reports:
            flag = "HARD" if r["hard_count"] else ("ok" if r["has_master"] else "no-master")
            print(
                f"  [{flag}] {r['run_id']} master={r['has_master']} "
                f"vo={r['edl_vo_pickup']}/{r['vo_wav_count']} "
                f"sfx={r['sfx_generated']}/{r['sfx_planned']} "
                f"findings={len(r['findings'])}"
            )
            for f in r["findings"]:
                print(f"      - {f['severity']}: {f['code']} — {f['detail']}")
        print(f"Hard breakers on mastered runs: {len(hard_with_master)}")

    return 1 if hard_with_master else 0


if __name__ == "__main__":
    raise SystemExit(main())
